"""Required Gradescope rosters and local identity checks, outside grading prompts."""
from pathlib import Path
import csv,io,hashlib,importlib.util,json,re,secrets,sqlite3,sys,time,unicodedata
from collections import Counter

def name_key(value):
    return ' '.join(sorted(re.findall(r'[^\W\d_]+',unicodedata.normalize('NFKD',value).casefold())))

def instructor_sections(assignments,profile_name):
    """Match the configured instructor, refusing ambiguous surname matches."""
    def parts(value):
        value=''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if not unicodedata.combining(c)).replace('’',"'")
        def words(text):return [w for w in re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*",text) if w not in ('dr','prof','professor','jr','sr','ii','iii','iv')]
        if ',' in value:
            family,given=value.split(',',1);family=words(family);given=words(given)
            return family+given,(family[-1] if family else ''),(given[0] if given else '')
        tokens=words(value)
        return tokens,(tokens[-1] if tokens else ''),(tokens[0] if len(tokens)>1 else '')
    own,family,first=parts(profile_name)
    if not own:raise ValueError('Set your name in Instructor profile, or choose a lecture-group section.')
    keyed=[(row,*parts(row.get('name',''))) for row in assignments]
    exact=[row for row,tokens,_,_ in keyed if sorted(tokens)==sorted(own)]
    matches=exact or [row for row,tokens,surname,given in keyed if surname==family and (not first or not given or first==given or len(given)==1 and given==first[0] or len(first)==1 and given[0:1]==first)]
    identities={row.get('instructor_id') or name_key(row.get('name','')) for row in matches}
    if len(identities)>1:raise ValueError('More than one instructor matches your profile. Choose a lecture-group section.')
    sections=sorted({row['section'] for row in matches})
    if not sections:raise ValueError('No lecture sections match your instructor profile in this semester. Choose a section or update the saved teaching assignments.')
    return sections

def gradescope_csv(raw):
    """Read the Gradescope export locally. SID is a NetID, never an email alias."""
    try:
        text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
        delimiter=csv.Sniffer().sniff(text[:8192],delimiters=',;\t').delimiter
        reader=csv.DictReader(io.StringIO(text),delimiter=delimiter)
        columns={re.sub(r'\s+',' ',str(h or '').strip()).casefold():h for h in reader.fieldnames or []}
    except (ValueError,UnicodeError,csv.Error):raise ValueError('Export the Gradescope roster as CSV and upload it again.') from None
    if not {'first name','last name','sid','role'}<=columns.keys():
        raise ValueError('Choose a Gradescope CSV with First Name, Last Name, SID and Role columns.')
    students={};skipped=[];staff=0;merged=0;courses=set();terms=set()
    def field(row,key):return str(row.get(columns.get(key,'')) or '').strip()
    for line,row in enumerate(reader,2):
        if line>10002:raise ValueError('Choose a roster with at most 10,000 rows.')
        if not any(str(v or '').strip() for v in row.values()):continue
        role=field(row,'role').casefold()
        if role!='student':
            if role:staff+=1
            else:skipped.append(line)
            continue
        first,last=field(row,'first name'),field(row,'last name');netid=field(row,'sid').lower()
        if not first or not last or not re.fullmatch(r'[a-z][a-z0-9]{0,30}',netid):
            skipped.append(line);continue
        name=first+' '+last
        if len(name)>160 or any(ord(c)<32 for c in name):skipped.append(line);continue
        emails=[]
        email=field(row,'email').lower()
        if email:
            if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(email)>254:skipped.append(line);continue
            emails=[email]
        sections=[];invalid_section=False
        for key in columns:
            if not re.fullmatch(r'section(?: \d+)?',key):continue
            section=field(row,key)
            if not section:continue
            match=re.search(r'\b\d{2}:640:(\d{3}):(\d{1,3})$',section)
            term=re.search(r'\b(20\d{2})(FA|SP|SU|WI)\b',section,re.I)
            if term:terms.add(term[2].lower()+term[1][-2:])
            if match:courses.add(str(int(match[1])));section=str(int(match[2])).zfill(2)
            if len(section)>30:skipped.append(line);invalid_section=True;break
            if section not in sections:sections.append(section)
        if invalid_section:continue
        if not sections:sections=['Unmapped']
        value={'name':name,'netid':netid,'ruid':'','section':next((value for value in sections if re.fullmatch(r'\d{2,3}',value)),sections[0]),'sections':sections,'emails':emails}
        if netid in students:
            old=students[netid]
            if name_key(old['name'])!=name_key(name):raise ValueError('A repeated SID has conflicting student names. Resolve those roster rows before importing.')
            old['emails']=sorted(set(old['emails']+emails));old['sections']=sorted(set(old['sections']+sections))
            if old['section'] in ('Guest','Unmapped') and sections[0] not in ('Guest','Unmapped'):old['section']=sections[0]
            merged+=1
        else:students[netid]=value
    if not students:raise ValueError('No Student rows with a name and valid NetID in SID were found.')
    return {'students':list(students.values()),'skippedLines':skipped,'excludedStaff':staff,'mergedRows':merged,'courses':sorted(courses),'terms':sorted(terms)}

class Rosters:
    def roster_init(self):
        self.roster_previews={}
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS project_rosters(project_id TEXT PRIMARY KEY,data TEXT NOT NULL,source TEXT NOT NULL,sections TEXT NOT NULL,updated TEXT NOT NULL)')

    def _roster_parser(self):
        # Reuse the existing CSV/REGIS/XLSX parser without constructing its Store:
        # constructing Math135.Store would migrate/write the grade database.
        if hasattr(self,'_roster_parser_module'):return self._roster_parser_module
        folder=__import__('integration_paths').spot_root()/'Data/PrivateModules/Math135/App'
        try:
            sys.path.insert(0,str(folder))
            spec=importlib.util.spec_from_file_location('_gscope_regis_parser',folder/'core.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self._roster_parser_module=module;return module
        except (OSError,ImportError):raise ValueError('The existing REGIS parser is unavailable. Restore the Math 135 app files before importing a roster.') from None
        finally:
            if str(folder) in sys.path:sys.path.remove(str(folder))

    def _roster_math_path(self):return __import__('integration_paths').spot_root()/'Data/PrivateModules/Math135/Math_135_Central.sqlite'

    def _roster_math(self,term):
        p=self._roster_parser();semester=p.semester(term)
        try:
            path=self._roster_math_path().resolve(strict=True)
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=4);db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('BEGIN')
            assignments=[dict(r) for r in db.execute("SELECT t.section,t.source_section,p.name,p.instructor_id FROM app_teaching_assignments t JOIN app_teacher_people p USING(instructor_id) WHERE t.semester=? COLLATE NOCASE AND t.role='lecturer'",(semester,))]
            return db,assignments,semester
        except (OSError,sqlite3.Error):
            if 'db' in locals():db.close()
            raise ValueError('The saved Math 135 teaching assignments are unavailable for this semester.') from None

    def roster_get(self,pid):
        project=self.one('projects',pid);rows=self.rows('SELECT * FROM project_rosters WHERE project_id=?',(pid,));r=rows[0] if rows else None
        students,roster_hash=self._roster_students(pid)
        ready=bool(r and r['source']=='Gradescope CSV' and students and all(re.fullmatch(r'[a-z][a-z0-9]{0,30}',row.get('netid','')) and row.get('name') for row in students))
        counts=Counter(i['netid'] for i in self.rows("""SELECT i.netid,m.data FROM scan_identities i JOIN booklets b ON b.id=i.booklet_id JOIN versions v ON v.id=b.version_id JOIN scan_packets p ON p.assigned_booklet_id=b.id JOIN scan_matching m ON m.packet_id=p.id LEFT JOIN scan_removed_files r ON r.file_id=b.file_id WHERE v.project_id=? AND r.file_id IS NULL AND m.status IN ('auto','manual')""",(pid,)) if json.loads(i['data']).get('rosterHash')==roster_hash)
        names=Counter(name_key(s['name']) for s in students)
        duplicate_ids=[s['id'] for s in students if names[name_key(s['name'])]>1]
        visible=[{**{k:s[k] for k in ('id','name','netid','section')},'emails':s.get('emails',[]),'sections':s.get('sections',[s['section']]),'matchedExams':counts[s['netid']]} for s in students]
        return {'projectId':pid,'course':project['course'],'term':project['term'],'configured':bool(r),'required':True,'ready':ready,'count':len(students),'source':r['source'] if r else '', 'sections':json.loads(r['sections']) if r else [],'updated':r['updated'] if r else '', 'students':visible,'rosterHash':roster_hash,'duplicateNameIds':duplicate_ids}

    def roster_sources(self,pid):
        project=self.one('projects',pid);items=[]
        for row in self.rows("""SELECT p.id,p.title,p.created FROM projects p JOIN project_rosters r ON r.project_id=p.id
            WHERE p.course=? AND p.term=? AND p.id!=? AND p.id NOT IN(SELECT project_id FROM project_trash)
            AND r.source='Gradescope CSV' ORDER BY p.created DESC""",(project['course'],project['term'],pid)):
            roster=self.roster_get(row['id'])
            if roster['ready']:items.append({**row,'count':roster['count'],'rosterHash':roster['rosterHash']})
        return {'items':items,'course':project['course'],'term':project['term']}

    def roster_reuse(self,pid,payload):
        with self.lock:
            self._archive_idle()
            if set(payload)!={'sourceProjectId','sourceRosterHash'}:raise ValueError('Choose an existing exam roster.')
            source=next((r for r in self.roster_sources(pid)['items'] if r['id']==payload['sourceProjectId']),None)
            if not source or source['rosterHash']!=payload['sourceRosterHash']:
                raise ValueError('Choose a current roster from this course and semester.')
            people,_=self._roster_students(source['id'])
            result=self._roster_stage(pid,people,'Gradescope CSV',sorted({s for row in people for s in row.get('sections',[row['section']])}))
            result.update(reusedFrom=source['title'],studentPreview=[{k:s[k] for k in ('name','netid','section')} for s in people[:20]])
            return result

    def _roster_student_change(self,pid,payload,remove=False):
        with self.lock:
            self.one('projects',pid);self._archive_idle()
            allowed={'studentId','rosterHash','confirmed'}|({'student'} if not remove else set())
            if set(payload)-allowed or payload.get('confirmed') is not True:raise ValueError('Review and confirm this roster change.')
            students,old_hash=self._roster_students(pid)
            if payload.get('rosterHash')!=old_hash:raise ValueError('The roster changed. Refresh it before editing a student.')
            current=next((s for s in students if s['id']==payload.get('studentId')),None)
            if current is None:raise ValueError('Select a student in this project roster.')
            old_netid=current['netid'];changed_identity=remove
            if remove:updated=[s for s in students if s['id']!=current['id']]
            else:
                value=payload.get('student')
                if not isinstance(value,dict) or set(value)!={'name','netid','section'} or any(not isinstance(v,str) for v in value.values()):
                    raise ValueError('Enter a name, NetID and section.')
                name=value['name'].strip();netid=value['netid'].strip().lower();section=value['section'].strip()
                if not name or len(name)>160 or any(ord(c)<32 for c in name+section) or not re.fullmatch(r'[a-z][a-z0-9]{0,30}',netid) or not section or len(section)>30:
                    raise ValueError('Check the student name, NetID and section.')
                if any(s['netid']==netid and s['id']!=current['id'] for s in students):raise ValueError('Another roster student already has this NetID.')
                changed_identity=name_key(name)!=name_key(current['name']) or netid!=old_netid
                updated=[]
                for s in students:
                    if s['id']!=current['id']:updated.append(s);continue
                    updated.append({**s,'name':name,'netid':netid,'section':section,
                                    'sections':list(dict.fromkeys([section,*[x for x in s.get('sections',[]) if x!=current['section']]]))})
            clean=[{k:v for k,v in s.items() if k!='id'} for s in updated]
            rows=self.rows('SELECT * FROM project_rosters WHERE project_id=?',(pid,));record=rows[0]
            sections=sorted({section for s in clean for section in s.get('sections',[s['section']])})
            from scan_archive import stamp,packed
            affected=0
            with self.connect() as db:
                db.execute('UPDATE project_rosters SET data=?,sections=?,updated=? WHERE project_id=?',(json.dumps(clean),json.dumps(sections),stamp(),pid))
            # Only unchanged, current, reviewed identities are rebound to the new
            # roster hash. Edited/removed identities remain saved but unreviewed.
            new_students,new_hash=self._roster_students(pid);by_netid={s['netid']:s for s in new_students}
            matches=self.rows("""SELECT m.*,p.assigned_booklet_id AS bookletId FROM scan_matching m JOIN scan_packets p ON p.id=m.packet_id JOIN scan_sources s ON s.id=p.source_id JOIN booklets b ON b.id=p.assigned_booklet_id LEFT JOIN scan_removed_files r ON r.file_id=b.file_id WHERE s.project_id=? AND r.file_id IS NULL""",(pid,))
            old_by_id={s['id']:s for s in students}
            with self.connect() as db:
                for match in matches:
                    data=json.loads(match['data']);old=old_by_id.get(data.get('rosterId'))
                    if data.get('rosterHash')!=old_hash or not old:continue
                    if old['netid']==old_netid and changed_identity:
                        db.execute('UPDATE scan_identities SET reviewed=0 WHERE booklet_id=?',(match['bookletId'],))
                        db.execute("UPDATE scan_matching SET status='unmatched',data=?,updated=? WHERE packet_id=?",(packed({'reason':'Roster student edited or removed. Review this exam match.','rosterHash':new_hash}),stamp(),match['packet_id']));affected+=1
                    elif old['netid'] in by_netid:
                        student=by_netid[old['netid']];data.update(rosterId=student['id'],rosterHash=new_hash,section=student['section'])
                        db.execute('UPDATE scan_matching SET data=?,updated=? WHERE packet_id=?',(packed(data),stamp(),match['packet_id']))
                self.event(db,'roster-student-removed' if remove else 'roster-student-edited',pid,{'beforeHash':old_hash,'afterHash':new_hash,'affectedMatches':affected})
            result=self.roster_get(pid);result['affectedMatches']=affected;return result

    def roster_student_save(self,pid,payload):return self._roster_student_change(pid,payload)
    def roster_student_remove(self,pid,payload):return self._roster_student_change(pid,payload,True)

    def _roster_stage(self,pid,students,source,sections,issues=0):
        project=self.one('projects',pid)
        if not students:raise ValueError('No roster students were found for that selection.')
        if len(students)>10000:raise ValueError('Choose a roster of at most 10,000 students.')
        cleaned=[];seen={}
        for row in students:
            name=str(row.get('name') or '').strip();netid=str(row.get('netid') or '').strip().lower();ruid=str(row.get('ruid') or '').strip();section=str(row.get('section') or '').strip()
            if not name or len(name)>160 or len(section)>30 or any(ord(c)<32 for c in name+netid+section) or (netid and not re.fullmatch(r'[a-z][a-z0-9]{0,30}',netid)) or (ruid and not re.fullmatch(r'\d{9}',ruid)):
                issues+=1;continue
            key=ruid or netid or name_key(name)+'|'+section;value={'name':name,'netid':netid,'ruid':ruid,'section':section}
            if row.get('emails') is not None:value['emails']=list(row['emails'])
            if row.get('sections') is not None:value['sections']=list(row['sections'])
            if key in seen:
                if seen[key]!=value:raise ValueError('The roster has conflicting rows for one student. Resolve them before importing.')
                continue
            seen[key]=value;cleaned.append(value)
        if not cleaned:raise ValueError('No valid student names or identifiers were found in the roster.')
        now=time.time();self.roster_previews={k:v for k,v in self.roster_previews.items() if now-v['created']<1800}
        if len(self.roster_previews)>=20:self.roster_previews.pop(next(iter(self.roster_previews)))
        token=secrets.token_hex(16);summary={'id':token,'projectId':pid,'course':project['course'],'term':project['term'],'source':source,'sections':sorted(set(sections)),'count':len(cleaned),'skippedRows':issues}
        self.roster_previews[token]={'created':now,'project':{k:project[k] for k in ('id','course','term')},'students':cleaned,'summary':summary}
        return summary

    def roster_upload(self,pid,name,raw):
        project=self.one('projects',pid);self._archive_idle()
        if not isinstance(raw,bytes) or not 0<len(raw)<=20_000_000 or Path(name).suffix.lower() not in ('.csv','.tsv','.txt'):
            raise ValueError('Upload the raw Gradescope roster CSV, up to 20 MB.')
        parsed=gradescope_csv(raw)
        if parsed['courses'] and any(code!=str(project['course']) for code in parsed['courses']):
            raise ValueError('The roster course differs from this exam project.')
        if parsed['terms'] and any(term!=project['term'].lower() for term in parsed['terms']):
            raise ValueError('The roster semester differs from this exam project.')
        result=self._roster_stage(pid,parsed['students'],'Gradescope CSV',[section for row in parsed['students'] for section in row['sections']],len(parsed['skippedLines']))
        result.update(mergedRows=parsed['mergedRows'],excludedStaff=parsed['excludedStaff'],skippedLines=parsed['skippedLines'],
                      guestStudents=sum(not re.fullmatch(r'\d{2,3}',row['section']) for row in parsed['students']),
                      duplicateNames=sum(n>1 for n in Counter(name_key(row['name']) for row in parsed['students']).values()))
        result['guestPreview']=[{k:row[k] for k in ('name','netid','section')} for row in parsed['students'] if not re.fullmatch(r'\d{2,3}',row['section'])][:20]
        return result

    def require_gradescope_roster(self,pid):
        if not self.roster_get(pid)['ready']:
            raise ValueError('Upload and confirm this exam project\'s Gradescope roster in Exam roster before continuing.')
        rows=self.rows('SELECT data FROM project_rosters WHERE project_id=?',(pid,))
        return json.loads(rows[0]['data'])

    def export_student_identities(self,vid,booklet_ids):
        project=self.one('versions',vid)['project_id'];students=self.require_gradescope_roster(project)
        roster={r['netid']:r for r in students}
        roster_hash=self._roster_students(project)[1];used=set();result={}
        for bid in booklet_ids:
            rows=self.rows('SELECT * FROM scan_identities WHERE booklet_id=?',(bid,))
            identity=rows[0] if rows else {};netid=identity.get('netid','')
            student=roster.get(netid)
            if not identity.get('reviewed') or not student or name_key(identity.get('name',''))!=name_key(student['name']):
                raise ValueError('Review every exam\'s roster student in Student matching before exporting named suggestions.')
            state=self.rows('SELECT m.data FROM scan_matching m JOIN scan_packets p ON p.id=m.packet_id WHERE p.assigned_booklet_id=?',(bid,))
            if state and json.loads(state[0]['data']).get('rosterHash')!=roster_hash:
                raise ValueError('The roster changed. Review student matches again before exporting.')
            if netid in used:raise ValueError('One roster student is linked to multiple exams in this version. Resolve that duplicate before exporting.')
            used.add(netid);result[bid]={k:student[k] for k in ('name','netid','section')}
        name_counts=Counter(name_key(r['name']) for r in students)
        ambiguous=sorted({r['name'] for r in students if name_counts[name_key(r['name'])]>1})
        return result,{'required':True,'rosterHash':roster_hash,'ambiguousNames':ambiguous}

    def roster_pull(self,pid,payload):
        project=self.one('projects',pid);self._archive_idle()
        if str(project['course'])!='135' or set(payload)-{'mode','section'} or payload.get('mode','mine') not in ('mine','section'):raise ValueError('Choose Math 135 own sections or a lecture-group section.')
        instructor_name=''
        if payload.get('mode','mine')=='mine':
            try:instructor_name=json.loads((self.root/'instructor-profile.json').read_text('utf-8-sig')).get('name','')
            except (OSError,ValueError,TypeError,AttributeError):pass
            if not isinstance(instructor_name,str) or not instructor_name.strip():raise ValueError('Set your name in Instructor profile, or choose a lecture-group section.')
        db,assignments,semester=self._roster_math(project['term'])
        try:
            if payload.get('mode','mine')=='mine':
                sections=instructor_sections(assignments,instructor_name)
            else:
                section=self._roster_parser().section(payload.get('section'));matches=[r for r in assignments if r['section']==section]
                groups={r['source_section'] for r in matches if r['source_section']}
                if len(groups)!=1:raise ValueError('No unique lecture group is mapped for that section. Check Math 135 teaching assignments.')
                group=next(iter(groups));sections=sorted({r['section'] for r in assignments if r['source_section']==group})
                if len(sections)!=3:raise ValueError('The saved mapping does not identify exactly three sections for this lecture group. Check Math 135 teaching assignments.')
            marks=','.join('?' for _ in sections)
            students=[dict(r) for r in db.execute("SELECT e.ruid,e.name,e.netid,rs.section FROM enrollments e JOIN app_roster_state rs ON rs.ruid=e.ruid AND rs.semester=e.semester WHERE e.semester=? COLLATE NOCASE AND COALESCE(rs.active,1)=1 AND rs.section IN ("+marks+") ORDER BY rs.section,e.name",(semester,*sections))]
        except sqlite3.Error:raise ValueError('The Math 135 roster format is unavailable. Use a REGIS upload instead.') from None
        finally:db.close()
        return self._roster_stage(pid,students,'Math 135 · my sections' if payload.get('mode','mine')=='mine' else 'Math 135 · selected lecture group',sections)

    def roster_apply(self,pid,payload):
        project=self.one('projects',pid);self._archive_idle();p=self.roster_previews.get(payload.get('previewId'))
        if set(payload)-{'previewId','confirmed','includeGuests'} or type(payload.get('includeGuests',False)) is not bool or payload.get('confirmed') is not True or not p or time.time()-p['created']>=1800 or p['project']!={k:project[k] for k in ('id','course','term')}:raise ValueError('Preview this assignment’s roster again before applying it.')
        if p['summary'].get('skippedRows'):raise ValueError('Correct invalid roster rows before confirming.')
        if p['summary'].get('guestStudents') and 'includeGuests' not in payload:raise ValueError('Choose whether Guest/unmapped students belong to this exam.')
        if p['summary'].get('guestStudents') and not payload.get('includeGuests'):
            p=dict(p);p['students']=[r for r in p['students'] if re.fullmatch(r'\d{2,3}',r.get('section',''))]
            if not p['students']:raise ValueError('No exam students remain. Review the Guest/unmapped selection.')
            p['summary']={**p['summary'],'sections':sorted({x for r in p['students'] for x in r.get('sections',[r['section']])})}
        from scan_archive import stamp
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO project_rosters VALUES(?,?,?,?,?)',(pid,json.dumps(p['students']),p['summary']['source'],json.dumps(p['summary']['sections']),stamp()))
        self.roster_previews.pop(payload['previewId'],None);return self.roster_get(pid)

    def roster_clear(self,pid,payload):
        self.one('projects',pid);self._archive_idle()
        if payload!={'confirmed':True}:raise ValueError('Confirm removal of this assignment’s optional roster.')
        with self.connect() as db:db.execute('DELETE FROM project_rosters WHERE project_id=?',(pid,))
        return self.roster_get(pid)

    def roster_check(self,pid,payload):
        self.one('projects',pid)
        if set(payload)-{'name','netid'} or any(not isinstance(v,str) or len(v)>160 for v in payload.values()):raise ValueError('Check the student name and NetID.')
        rows=self.rows('SELECT data FROM project_rosters WHERE project_id=?',(pid,))
        if not rows:return {'status':'none','message':'No optional roster configured.'}
        students=json.loads(rows[0]['data']);netid=payload.get('netid','').strip().lower();name=payload.get('name','').strip()
        matches=[s for s in students if s['netid'] and s['netid']==netid] if netid else [s for s in students if name_key(s['name'])==name_key(name)] if name else []
        if len(matches)>1:return {'status':'ambiguous','message':'More than one roster student matches. Review manually.'}
        if not matches:return {'status':'missing','message':'No roster match. You can still confirm this exam manually.'}
        s=matches[0]
        if netid and name and name_key(name)!=name_key(s['name']):return {'status':'conflict','message':'NetID matches but the name differs. Check before assigning.','candidate':{k:s[k] for k in ('name','netid','section')}}
        return {'status':'matched','message':'Roster match by '+('NetID.' if netid else 'unique name.'),'candidate':{k:s[k] for k in ('name','netid','section')}}

def identity_name_matches(read,registered):
    if name_key(read)==name_key(registered):return True
    def parts(value):
        if ',' in value:
            last,first=value.split(',',1);value=first+' '+last
        return re.findall(r'[^\W\d_]+',unicodedata.normalize('NFKD',value).casefold())
    a,b=parts(read),parts(registered)
    if min(len(a),len(b))<2 or a[0]!=b[0] or a[-1]!=b[-1]:return False
    # Middle names may be omitted or given as initials; conflicting ones cannot.
    return all(x==y or (min(len(x),len(y))==1 and x[0]==y[0]) for x,y in zip(a[1:-1],b[1:-1]))

def _one_identity_edit(a,b):
    def parts(value):
        if ',' in value:
            last,first=value.split(',',1);value=first+' '+last
        return re.findall(r'[^\W\d_]+',unicodedata.normalize('NFKD',value).casefold())
    left,right=parts(a),parts(b)
    if min(len(left),len(right))>=3 and left[0]==right[0] and left[-1]==right[-1] and left[1:-1]!=right[1:-1]:return False
    a=''.join(name_key(a).split());b=''.join(name_key(b).split())
    if a==b:return True
    if abs(len(a)-len(b))>1:return False
    if len(a)==len(b):return sum(x!=y for x,y in zip(a,b))==1
    if len(a)>len(b):a,b=b,a
    for i in range(len(b)):
        if a==b[:i]+b[i+1:]:return True
    return False

def _same_unclear_netid(a,b):
    a=a.casefold();b=b.casefold()
    if len(a)!=len(b):return False
    groups=(set('1il'),set('0o'))
    differences=[(x,y) for x,y in zip(a,b) if x!=y]
    return len(differences)==1 and all(any({x,y}<=group for group in groups) for x,y in differences)

def resolve_identity_reading(reading,students):
    name=reading.get('name','');netid=reading.get('netid','')
    by_name=[s for s in students if name and identity_name_matches(name,s['name'])]
    by_id=[s for s in students if netid and s.get('netid','').casefold()==netid.casefold()]
    if netid and not re.fullmatch(r'[A-Za-z0-9]{1,31}',netid):raise ValueError('Check the handwritten NetID characters.')
    if len(by_id)==1:
        student=by_id[0];same=bool(name and identity_name_matches(name,student['name']))
        close=bool(name and len(name.split())>=2 and not by_name and _one_identity_edit(name,student['name']))
        if name and not (same or close):raise ValueError('The name and NetID disagree. Review this exam manually.')
        if reading.get('needsReview') and not (same or close):raise ValueError('The field reading is uncertain. Review the suggested roster students.')
        return student
    if len(by_id)>1:raise ValueError('No unique roster NetID match. Review this exam.')
    if netid:
        # Roster association, not an invented transcription: both fields must
        # support the sole candidate. The raw reading is retained for review.
        candidates=[s for s in by_name if s.get('netid') and _same_unclear_netid(netid,s['netid'])]
        if len(candidates)==1:return candidates[0]
        raise ValueError('No exact roster NetID match. Choose a suggested student after checking the handwriting.')
    if reading.get('needsReview'):raise ValueError('The field reading is uncertain. Review the suggested roster students.')
    if len(by_name)==1:return by_name[0]
    raise ValueError('No unique roster match. Choose a student after checking the handwriting.')


def suggest_identity_reading(reading,students,excluded=()):
    """Rank a plausible available roster student for explicit human review only."""
    from difflib import SequenceMatcher
    blocked=set(excluded);name=name_key(reading.get('name',''));netid=reading.get('netid','').casefold().strip()
    if not name and not netid:return None
    def similarity(a,b):
        if not a or not b:return 0
        return SequenceMatcher(None,a,b).ratio()
    scored=[]
    for student in students:
        if student['id'] in blocked:continue
        registered=name_key(student['name']);sid=student.get('netid','').casefold()
        exact_name=bool(name and identity_name_matches(reading.get('name',''),student['name']))
        ns=1.0 if exact_name else similarity(name,registered)
        exact_id=bool(netid and netid==sid)
        ids=similarity(netid,sid)
        # Empty/random readings must not produce a candidate merely because the
        # roster is small. Suggestions never reserve a student or confirm a match.
        supported=exact_id or exact_name or (len(name)>=8 and ns>=.78) or (len(netid)>=3 and ids>=.7 and ns>=.45)
        if not supported:continue
        score=(.58*ids+.42*ns) if name and netid else (ids if netid else ns)
        if exact_id:score+=.18
        if exact_name:score+=.12
        scored.append((score,student))
    scored.sort(key=lambda item:(-item[0],item[1]['id']))
    if not scored or (len(scored)>1 and scored[0][0]-scored[1][0]<.06):return None
    return {k:scored[0][1][k] for k in ('id','name','netid','section')}

def identity_sheet(images):
    """One bounded image of the exact approved fields, with fixed panel labels."""
    import base64
    from PIL import Image,ImageOps,ImageDraw
    panels=[]
    try:
        for name,raw in images:
            with Image.open(io.BytesIO(raw)) as source:im=ImageOps.autocontrast(source.convert('RGB'))
            im.thumbnail((900,150));panels.append((name,im))
        if not panels:raise ValueError('Save the identity fields first.')
        sheet=Image.new('RGB',(max(im.width for _,im in panels)+16,sum(im.height+28 for _,im in panels)+8),'white')
        try:
            draw=ImageDraw.Draw(sheet);y=5
            for name,im in panels:draw.text((8,y),name,fill='black');sheet.paste(im,(8,y+20));y+=im.height+28
            out=io.BytesIO();sheet.save(out,'PNG');return base64.b64encode(out.getvalue()).decode('ascii')
        finally:sheet.close()
    finally:
        for _,im in panels:im.close()
