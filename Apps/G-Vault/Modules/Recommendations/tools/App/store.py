"""Private local recommendation records. No AI connections or automatic sending."""
from pathlib import Path
from datetime import datetime
import json,os,re,secrets,threading,subprocess,tempfile,importlib.util,hashlib,shutil,math,time
import archive,grades
import course_history

# Shared signature path only; no other module records are accessed.
import sys
_shared_ui=(Path(__file__).resolve().parents[5]/'Dependencies/TeachingApp').resolve()/'private_module_ui'
if (_shared_ui/'shared_signature.py').is_file():
    sys.path.insert(0,str(_shared_ui))
    import shared_signature
    import shared_tex
else:shared_signature=None

NOTE_EXTENSIONS={'.pdf','.docx','.png','.jpg','.jpeg','.webp','.note','.ntb','.txt'}

def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def text(value,maximum=200000):
    if not isinstance(value,str)or len(value)>maximum:raise ValueError('Check the text field length.')
    return value.strip()
def read_json(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))if Path(path).exists()else default
def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    # Sync clients can briefly lock the destination on Windows. Keep each write
    # atomic and retry only that transient failure; never remove the saved file.
    delays=(.05,.1,.2,.35,.5,.75,1.0)
    for attempt in range(len(delays)+1):
        try:
            os.replace(temporary,path)
            return
        except PermissionError:
            if attempt==len(delays):raise
            time.sleep(delays[attempt])
def natural_name(name):
    if ','in name:
        last,first=name.split(',',1);return (first.strip()+' '+last.strip()).strip()
    return name

def list_name(person):
    name=person.get('name','').strip()
    if ','in name:return ', '.join(part.strip()for part in name.split(',',1))
    words=lambda value:sorted(re.findall(r'\w+',value.casefold()))
    for alias in person.get('aliases',[]):
        if ','in alias and words(alias)==words(name):
            return ', '.join(part.strip()for part in alias.split(',',1))
    parts=name.rsplit(None,1)
    return parts[1]+', '+parts[0]if len(parts)==2 else name

def publication_filename(person,date,identity,revision='signed-01'):
    return file_label(list_name(person))+'-'+person['id']+'-Letter-'+file_label(date or 'Undated')+'-'+identity+'-Signed-'+revision.split('-')[-1]+'.pdf'
def safe_stem(value):
    value=re.sub(r'[^\w .-]','',value,flags=re.UNICODE).strip(' .')[:70]
    return value if value and value.upper()not in {'CON','PRN','AUX','NUL'}else'Letter'

def file_label(value):
    value=re.sub(r'[^\w -]','',str(value),flags=re.UNICODE)
    return re.sub(r'[\s_-]+','-',value).strip('-')[:65]or'Letter'

class Store:
    def __init__(self,root):
        self.root=Path(root).resolve();self.tools=self.root/'tools'
        self.config_path=self.tools/'settings.json';self.profile_path=self.tools/'author-profile.json'
        self.settings=read_json(self.config_path,{'grade_database':'','mh_git':str(Path(__file__).resolve().parents[5]/'Data/PrivateSource'),'pdflatex':str(Path(__file__).resolve().parents[5]/'Dependencies/texlive/bin/windows/pdflatex.exe'),'academic_year_start_month':9})
        records_name=self.settings.get('records_root')or('Records'if(self.root/'Records').is_dir()else'Students')
        if records_name not in ('Records','Students'):raise ValueError('Choose the standard local records folder.')
        self.students_root=self.root/records_name;self.lock=threading.RLock()
        for p in [self.students_root,self.tools/'Approved Briefs',self.tools/'Build Cache',self.tools/'logs']:p.mkdir(parents=True,exist_ok=True)
        self.archive_path=self.tools/'archive-index.json';self.links_path=self.tools/'archive-links.json'
        self.consolidated_sources=self.settings.get('source_layout')=='consolidated'
        self.archive_root=self.root if self.consolidated_sources else self.root/('Letter Files'if(self.root/'Letter Files').is_dir()else'Legacy Archive')
        self.source_roots=(self.root/'Letters',self.root/'Needs Review')if self.consolidated_sources else(self.archive_root,)
        self.source_identities_path=self.tools/'source-file-identities.json'

    def open_output_folder(self):
        folder=self.root/'Letters'
        if folder.is_symlink()or folder.is_junction()or not folder.is_dir()or not folder.resolve().is_relative_to(self.root):raise ValueError('The local letters output folder is unavailable.')
        if os.name=='nt':os.startfile(str(folder))
        else:
            import sys
            subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'opened':True}

    def student_path(self,identity):
        if not re.fullmatch(r'REC-\d{4,8}',str(identity)):raise ValueError('Choose a student record.')
        return self.students_root/identity/'student.json'
    def letter_path(self,identity):
        if not re.fullmatch(r'L-\d{4,8}',str(identity)):raise ValueError('Choose a letter record.')
        paths=list(self.students_root.glob('REC-*/Letters/'+identity+'.json'))
        if len(paths)!=1:raise ValueError('The letter record was not found.')
        return paths[0]
    def students(self):
        result=[]
        for p in sorted(self.students_root.glob('REC-*/student.json')):
            r=read_json(p);letter_dates=[read_json(lp,{}).get('date','') for lp in (p.parent/'Letters').glob('L-*.json')];latest=max((d for d in letter_dates if isinstance(d,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',d)),default='');result.append({'latest_letter_date':latest,'id':r['id'],'name':r['name'],'list_name':list_name(r),'person_type':r.get('person_type','student'),'netid':r.get('netid',''),'has_grade_link':bool(r.get('ruid'))and r.get('person_type','student')=='student','letters_count':len(list((p.parent/'Letters').glob('L-*.json')))})
        return result
    def archive_data(self):
        result=read_json(self.archive_path,{'files':[],'groups':[],'summary':{'files':0,'groups':0,'signed_pdfs':0,'duplicates':0}})
        links=read_json(self.links_path,{})
        for r in result['files']:r['student_id']=links.get(r['group_id'])
        for r in result['groups']:
            r['student_id']=links.get(r['id']);r['signed']=sum(f['signed']for f in result['files']if f['group_id']==r['id'])
        result['summary']['pending']=sum(not r.get('student_id')for r in result['groups'])
        return result
    def _audit_sources(self):
        if not self.consolidated_sources:return archive.audit_archive(self.archive_root)
        # Deliberately inventory just the two source-document folders. Records,
        # runtime files, private notes and temporary work are never root-audited.
        result={'root':str(self.root),'files':[],'groups':[],'errors':[],'summary':{'excluded_temp':0,'excluded_symlinks':0,'excluded_directories':0}}
        for source_root in self.source_roots:
            if not source_root.exists():continue
            part=archive.audit_archive(source_root);prefix=source_root.name+'/'
            files={item['id']:archive._stable_id(prefix+item['path'])for item in part['files']}
            groups={item['id']:archive._stable_id(prefix+item['id'],'G')for item in part['groups']}
            for item in part['files']:
                item['id']=files[item['id']];item['group_id']=groups[item['group_id']];item['path']=prefix+item['path']
                if item.get('duplicate_of'):item['duplicate_of']=files[item['duplicate_of']]
                result['files'].append(item)
            for group in part['groups']:
                group['id']=groups[group['id']];group['files']=[files[value]for value in group['files']];result['groups'].append(group)
            result['errors'].extend({**error,'path':prefix+error['path']}for error in part['errors'])
            for key in result['summary']:result['summary'][key]+=part['summary'].get(key,0)
        result['files'].sort(key=lambda item:(item['path'].casefold(),item['path']))
        seen={}
        for item in result['files']:
            item['duplicate_of']=seen.get(item['sha256']);item['status']='exact_duplicate'if item['duplicate_of']else'original'
            seen.setdefault(item['sha256'],item['id'])
        result['summary'].update(files=len(result['files']),groups=len(result['groups']),signed_pdfs=sum(item['signed']for item in result['files']),duplicates=sum(bool(item['duplicate_of'])for item in result['files']),bytes=sum(item['bytes']for item in result['files']),errors=len(result['errors']))
        return result
    def refresh_archive(self):
        with self.lock:
            result=self._audit_sources()
            identities=read_json(self.source_identities_path,{})
            if not isinstance(identities,dict):raise ValueError('The local source identity map needs review.')
            previous=read_json(self.archive_path,{'groups':[]})
            previous_groups={group['id']:group for group in previous.get('groups',[])}
            previous_files={item['id']:item for item in previous.get('files',[])}
            audit_groups={group['id']:group for group in result['groups']}
            reserved_files={value.get('id')for value in identities.values()if isinstance(value,dict)and isinstance(value.get('id'),str)}
            reserved_groups={value.get('group_id')for value in identities.values()if isinstance(value,dict)and isinstance(value.get('group_id'),str)}
            identity_counts={identity:sum(isinstance(value,dict)and value.get('id')==identity for value in identities.values())for identity in reserved_files}
            remapped={};grouped={}
            for item in result['files']:
                original_id=item['id'];original_group=item['group_id'];saved=identities.get(item['path'])
                valid=isinstance(saved,dict)and saved.get('sha256')==item['sha256']and re.fullmatch(r'F[a-f0-9]{20}',str(saved.get('id','')))and re.fullmatch(r'G[a-f0-9]{20}',str(saved.get('group_id','')))and identity_counts.get(saved.get('id'))==1
                if valid:
                    item['id']=saved['id'];item['group_id']=saved['group_id']
                    item['original_path']=saved.get('original_path',item['path'])
                    item['identity_status']='preserved'
                    for key in ('classification','signature_verified','signature_verification','source_verification','signed'):
                        value=saved.get(key,previous_files.get(item['id'],{}).get(key))
                        if value is not None and(key not in ('signed','signature_verified')or isinstance(value,bool)):item[key]=value
                else:
                    if saved is not None:
                        result['errors'].append({'path':item['path'],'error':'source_identity_mismatch'})
                        item['identity_status']='needs_review'
                    if item['id']in reserved_files:item['id']='F'+hashlib.sha256(('unmapped-file:'+item['path']+':'+item['sha256']).encode('utf8')).hexdigest()[:20]
                    if item['group_id']in reserved_groups:item['group_id']='G'+hashlib.sha256(('unmapped-group:'+original_group).encode('utf8')).hexdigest()[:20]
                remapped[original_id]=item['id']
                if item['group_id']not in grouped:
                    old=previous_groups.get(item['group_id'])if valid else None
                    template=old or audit_groups[original_group]
                    grouped[item['group_id']]={key:value for key,value in template.items()if key not in ('files','student_id','signed')}
                    grouped[item['group_id']]['id']=item['group_id'];grouped[item['group_id']]['files']=[]
                grouped[item['group_id']]['files'].append(item['id'])
            for item in result['files']:
                if item.get('duplicate_of'):item['duplicate_of']=remapped[item['duplicate_of']]
            result['groups']=sorted(grouped.values(),key=lambda group:(group['label'].casefold(),group['id']))
            result['summary']['groups']=len(result['groups']);result['summary']['errors']=len(result['errors'])
            result['summary']['signed_pdfs']=sum(item.get('signed',False)and item['extension']=='.pdf'for item in result['files'])
            atomic_json(self.archive_path,result);return self.archive_data()
    def grade_databases(self):
        app=Path(os.environ.get('GVAULT_APP_ROOT') or Path(__file__).resolve().parents[5])
        registry=read_json(app/'Data/vault-workspaces.json',{})
        rows=[]
        for row in registry.get('courses',[]):
            path=Path(row['path']);path=path if path.is_absolute() else app/path
            rows.append({'id':row['id'],'name':row['name'],'path':str(path.resolve())})
        return rows

    def grade_database(self,identity=''):
        if not identity:return self.settings.get('grade_database','')
        row=next((r for r in self.grade_databases() if r['id']==identity),None)
        if not row:raise ValueError('Choose a registered course database in G-Vault.')
        return row['path']

    def import_source(self,name,data):
        name=Path(text(name,240)).name
        if Path(name).suffix.lower() not in ('.pdf','.docx','.txt') or not data or len(data)>50*1024*1024:
            raise ValueError('Choose a PDF, DOCX, or text letter no larger than 50 MiB.')
        folder=self.root/'Needs Review' if self.consolidated_sources else self.archive_root
        if folder.is_symlink() or folder.is_junction():raise ValueError('Choose a regular local library folder.')
        folder.mkdir(parents=True,exist_ok=True)
        safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).rstrip(' .')
        path=folder/safe
        if path.exists():
            stem=Path(safe).stem;extension=Path(safe).suffix
            path=folder/(stem+'-'+secrets.token_hex(5)+extension)
        with self.lock:
            with path.open('xb') as stream:stream.write(data)
            self.refresh_archive()
        return {'message':'Letter added to Files to review. Extract its text, review it, then allow it as a writing example if desired.'}

    def bootstrap(self):
        profile=read_json(self.profile_path,{'sender':{'name':'','title':'','department':'Department of Mathematics','contact_lines':[]},'signature_file':''})
        if shared_signature:profile=shared_signature.apply(profile)
        return {'grade_databases':self.grade_databases(),'students':self.students(),'archive':self.archive_data()['summary'],'profile':profile,'settings':self.settings,'style_guide':(self.tools/'writing-preferences.txt').read_text(encoding='utf8')if(self.tools/'writing-preferences.txt').exists()else''}
    def student(self,identity):
        p=self.student_path(identity)
        if not p.exists():raise ValueError('The student record was not found.')
        result=read_json(p)
        result.setdefault('person_type','student');result.setdefault('other_courses',[]);result.setdefault('notes_attachments',[])
        result['letters']=[self._decorate_letter(read_json(p),detail=False)for p in sorted((p.parent/'Letters').glob('L-*.json'))]
        result['archive_files']=[r for r in self.archive_data()['files']if r.get('student_id')==identity]
        result['grades']={'records':[],'attempts':0,'notes':[]}
        if result.get('ruid')and result['person_type']=='student':
            try:result['grades']=grades.student_records(self.grade_database(result.get('grade_course_id','')),result['ruid'],self.settings.get('academic_year_start_month',9))
            except (grades.GradesUnavailableError,ValueError) as exc:result['grades']['notes']=[str(exc)]
        result['grade_course_name']=next((r['name'] for r in self.grade_databases() if r['id']==result.get('grade_course_id')),'Linked course')
        return result
    def person_by_ruid(self,ruid):
        if not re.fullmatch(r'\d{9}',str(ruid)):raise ValueError('Use a nine-digit RUID to find an existing person.')
        matches=[path for path in self.students_root.glob('REC-*/student.json')if read_json(path).get('ruid')==ruid]
        if len(matches)>1:raise ValueError('Multiple local people share this RUID. Review the existing records before creating another.')
        return self.student(matches[0].parent.name)if matches else None
    def save_student(self,payload,identity=None):
        with self.lock:
            if identity:
                p=self.student_path(identity);record=read_json(p)
                if not record:raise ValueError('Student record not found.')
            else:
                ids=[int(p.name[4:])for base in (self.students_root,self.tools/'Deleted People')for p in base.glob('REC-*')if re.fullmatch(r'REC-\d+',p.name)]
                identity='REC-'+str(max(ids,default=0)+1).zfill(4);p=self.student_path(identity)
                record={'id':identity,'created':now(),'notes':{k:''for k in ['relationship','observations','student_statements','interview','plans']},'aliases':[],'name':'','netid':'','ruid':'','pronouns':'they/them','person_type':'student','other_courses':[]}
            record.setdefault('person_type','student');record.setdefault('other_courses',[])
            if payload.get('course_history_reviewed')is True:record['course_history_needs_review']=False
            if 'person_type'in payload:
                if payload['person_type']not in ('student','instructor'):raise ValueError('Choose student or instructor as the person type.')
                record['person_type']=payload['person_type']
            for key in ('name','netid','ruid','pronouns'):
                if key in payload:record[key]=text(payload[key],500)
            if not record['name']:raise ValueError('Add the student name.')
            if record.get('ruid')and not re.fullmatch(r'\d{9}',record['ruid']):raise ValueError('Use a nine-digit RUID or leave it blank.')
            if record.get('ruid')and any(path!=p and read_json(path).get('ruid')==record['ruid']for path in self.students_root.glob('REC-*/student.json')):raise ValueError('A local person already uses this RUID. Select the existing record instead of creating a duplicate.')
            if 'grade_course_id' in payload:
                choice=text(payload['grade_course_id'],80)
                if choice:self.grade_database(choice)
                if choice!=record.get('grade_course_id',''):
                    for letter_path in p.parent.glob('Letters/L-*.json'):
                        letter=read_json(letter_path);letter['selected_facts']=[value for value in letter.get('selected_facts',[]) if isinstance(value,str) and value.startswith('other-course:')];letter['updated']=now();atomic_json(letter_path,letter)
                record['grade_course_id']=choice
            if 'aliases'in payload:
                if not isinstance(payload['aliases'],list):raise ValueError('Aliases must be a list of names.')
                record['aliases']=[text(a,500)for a in payload['aliases']if a]
            if 'notes'in payload:
                if not isinstance(payload['notes'],dict):raise ValueError('Check the interview notes.')
                for k in record['notes']:
                    if k in payload['notes']:record['notes'][k]=text(payload['notes'][k])
            if 'other_courses'in payload:
                rows=payload['other_courses']
                if not isinstance(rows,list)or len(rows)>100:raise ValueError('Other courses must be a list of up to 100 course records.')
                cleaned=[]
                for row in rows:
                    if not isinstance(row,dict):raise ValueError('Check the other course record.')
                    course=text(row.get('course',''),200)
                    if not course:raise ValueError('Add the course name or number.')
                    average=row.get('average')
                    if average is not None:
                        if isinstance(average,bool)or not isinstance(average,(int,float))or not math.isfinite(average)or not 0<=average<=100:raise ValueError('Use a course average from 0 to 100, or leave it blank.')
                        average=float(average)
                    cleaned.append({'course':course,'semester':text(row.get('semester',''),100),'grade':text(row.get('grade',''),30),'average':average})
                if cleaned!=record.get('other_courses',[]):
                    # Course rows can be added/reordered/removed. Remove selected
                    # index tokens before changing rows, so an interrupted save
                    # cannot cause an old selection to cite a different course.
                    for letter_path in p.parent.glob('Letters/L-*.json'):
                        letter=read_json(letter_path)
                        selected=letter.get('selected_facts',[])
                        remaining=[value for value in selected if not re.fullmatch(r'other-course:\d+',value)]
                        if selected!=remaining:
                            letter['selected_facts']=remaining;letter['updated']=now();atomic_json(letter_path,letter)
                record['other_courses']=cleaned
            record['updated']=now();atomic_json(p,record);return self.student(identity)
    def delete_person(self,identity,payload):
        with self.lock:
            if payload.get('confirm')!=identity:raise ValueError('Confirm the exact REC number before deleting this person.')
            person=self.student(identity);path=self.student_path(identity)
            if person.get('letters')or person.get('archive_files')or person.get('notes_attachments'):raise ValueError('This person still has letters or files. Transfer those to the correct person before deleting this record.')
            archive_root=self.tools/'Deleted People';archive_root.mkdir(exist_ok=True)
            target=archive_root/identity
            if target.exists()or not target.resolve().is_relative_to(self.root):raise ValueError('The deleted-person archive path needs review.')
            path.parent.rename(target)
            return {'message':'Person removed. The record is recoverable locally; course grades were not changed.','id':identity}
    def course_suggestions(self,identity):
        person=self.student(identity);rows={}
        for path in self.student_path(identity).parent.glob('Letters/L-*.json'):
            letter=read_json(path)
            for source in [letter.get('body',''),*(v.get('text','')for v in letter.get('source_text_versions',[]))]:
                for row in course_history.suggestions(source):rows.setdefault((row['course'],row['semester']),{**row,'source_letter_id':letter['id']})
        return {'suggestions':list(rows.values()),'requires_review':True}
    def save_note_attachment(self,student_id,filename,data):
        filename=text(filename,500)
        if not filename or Path(filename).name!=filename or '/'in filename or '\\'in filename or any(ord(c)<32 for c in filename):raise ValueError('Choose a file with a simple filename.')
        extension=Path(filename).suffix.lower()
        if extension not in NOTE_EXTENSIONS:raise ValueError('Upload a PDF, DOCX, image, Notability note, or text file.')
        if not isinstance(data,bytes)or not 0<len(data)<=50*1024*1024:raise ValueError('Upload a nonempty file no larger than 50 MiB.')
        with self.lock:
            person_path=self.student_path(student_id);record=read_json(person_path)
            if not record:raise ValueError('Choose a person record first.')
            folder=person_path.parent/'Notes'
            if folder.is_symlink()or getattr(folder,'is_junction',lambda:False)():raise ValueError('The local notes folder must be a regular folder.')
            folder.mkdir(exist_ok=True)
            if not folder.resolve().is_relative_to(self.students_root.resolve()):raise ValueError('The local notes folder is unavailable.')
            identity='N-'+secrets.token_hex(8);destination=folder/(identity+extension)
            with destination.open('xb')as stream:stream.write(data)
            metadata={'id':identity,'display_name':filename,'extension':extension,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'created':now(),'url':'/api/notes/'+student_id+'/'+identity}
            record.setdefault('notes_attachments',[]).append(metadata);record['updated']=now();atomic_json(person_path,record)
            return self.student(student_id)
    def note_attachment_path(self,student_id,identity):
        if not re.fullmatch(r'N-[a-f0-9]{16}',str(identity)):raise ValueError('The local note was not found.')
        person_path=self.student_path(student_id);record=read_json(person_path,{})
        item=next((r for r in record.get('notes_attachments',[])if r.get('id')==identity),None)
        if not item or item.get('extension')not in NOTE_EXTENSIONS:raise ValueError('The local note was not found.')
        path=(person_path.parent/'Notes'/(identity+item['extension'])).resolve()
        if not path.is_relative_to(self.students_root.resolve())or not path.is_file():raise ValueError('The local note is unavailable.')
        return path
    def extract_note_text(self,student_id,identity):
        path=self.note_attachment_path(student_id,identity);warnings=['Review the extracted text before adding it to interview notes. Nothing has been saved or included in a drafting brief.']
        if path.suffix.lower()=='.txt':
            with path.open('r',encoding='utf-8-sig',errors='replace')as stream:value=stream.read(200001)
            if '\ufffd'in value:warnings.append('Some characters could not be read as UTF-8 and were replaced; compare the original.')
        elif path.suffix.lower()in('.pdf','.docx'):
            result=archive.extract_editable_letter(path);value=result.get('text','');warnings.extend(result.get('flags',[]))
            if not value.strip():warnings.append('This document has no readable text. Automatic handwriting recognition or OCR is not enabled; transcribe it locally or upload a text export.')
        else:
            value='';warnings.append('Text extraction is available for PDF files with a readable text layer, DOCX files, and UTF-8 text files. Images and Notability files stay preserved locally; automatic handwriting recognition or OCR is not enabled.')
        truncated=len(value)>200000
        if truncated:warnings.append('Only the first 200,000 characters are shown. Review or divide a longer text export before adding it to interview notes.')
        return {'text':value[:200000],'requires_review':True,'warnings':warnings,'truncated':truncated}
    def _source_ids(self,record):
        return list(dict.fromkeys([value for value in [record.get('source_file_id'),*record.get('source_file_ids',[])]if value]))
    def _decorate_letter(self,record,detail=True):
        record=dict(record);record.setdefault('historical',bool(self._source_ids(record)or record.get('source_text_versions')))
        for key in ('application_type','deadline','requirements','style_notes'):record.setdefault(key,'')
        record.setdefault('supporting_attachment_ids',[])
        record['source_file_ids']=self._source_ids(record)
        files={item['id']:item for item in self.archive_data()['files']}
        record['source_originals']=[{key:item[key]for key in ('id','display_name','extension','signed','sha256','signature_verified','signature_verification','source_verification')if key in item}|{'url':'/api/files/'+identity,'classification':item.get('classification')or('review'if item.get('signed')else'unsigned')}for identity in record['source_file_ids']if(item:=files.get(identity))]
        versions=record.get('source_text_versions',[])
        record['source_text_versions']=versions if detail else[{key:value for key,value in version.items()if key!='text'}for version in versions]
        return record
    def letter(self,identity):return self._decorate_letter(read_json(self.letter_path(identity)))
    def letters(self):
        people={r['id']:r for r in self.students()}
        return [self._decorate_letter(read_json(p),detail=False)|{'person_name':people.get(p.parent.parent.name,{}).get('name',''),'person_type':people.get(p.parent.parent.name,{}).get('person_type','student')}for p in sorted(self.students_root.glob('REC-*/Letters/L-*.json'))]
    def delete_letter(self,identity,payload):
        with self.lock:
            if payload.get('confirm')!=identity:raise ValueError('Confirm the exact letter ID before deleting this letter.')
            path=self.letter_path(identity)
            folder=self.tools/'Deleted Letters'
            if folder.is_symlink()or getattr(folder,'is_junction',lambda:False)():raise ValueError('The deleted-letter folder must be a regular folder.')
            folder.mkdir(exist_ok=True)
            target=folder/(identity+'.json')
            if target.exists()or not target.resolve().is_relative_to(self.root):raise ValueError('The deleted-letter archive path needs review.')
            path.rename(target)
            return {'id':identity,'message':'Letter removed from the library. Its record is recoverable locally; PDFs and person records are preserved.'}
    def save_letter(self,payload,identity=None):
        with self.lock:
            if identity:
                p=self.letter_path(identity);record=read_json(p)
                if payload.get('student_id',record['student_id'])!=record['student_id']:raise ValueError('A saved letter cannot be moved to another student.')
            else:
                student_id=payload.get('student_id');student=self.student_path(student_id)
                if not student.exists():raise ValueError('Choose a student first.')
                ids=[int(p.stem[2:])for p in [*self.students_root.glob('REC-*/Letters/L-*.json'),*(self.tools/'Deleted Letters').glob('L-*.json')]]
                identity='L-'+str(max(ids,default=0)+1).zfill(4);p=student.parent/'Letters'/(identity+'.json')
                record={'schema_version':1,'id':identity,'student_id':student_id,'created':now(),'title':'New application','purpose':'','recipient_lines':[],'salutation':'Dear Members of the Selection Committee:','date':''if payload.get('historical')is True else datetime.now().astimezone().date().isoformat(),'strength':'','body':'','selected_facts':[],'notes':'','revisions':[],'approved_style_example':False,'needs_review':False,'historical':False,'source_file_ids':[]}
            if 'historical'in payload:
                if not isinstance(payload['historical'],bool):raise ValueError('Check whether this is a historical letter.')
                record['historical']=payload['historical']
            for key in ['title','purpose','salutation','date','strength','body','notes']:
                if key in payload:record[key]=text(payload[key])
            if 'application_type'in payload:
                if payload['application_type']not in ('','program','graduate_school','general','employment','other'):raise ValueError('Choose the application type.')
                record['application_type']=payload['application_type']
            if 'deadline'in payload:
                deadline=text(payload['deadline'],10)
                if deadline:
                    try:valid=re.fullmatch(r'\d{4}-\d{2}-\d{2}',deadline)and datetime.strptime(deadline,'%Y-%m-%d').date().isoformat()==deadline
                    except ValueError:valid=False
                    if not valid:raise ValueError('Use YYYY-MM-DD for the deadline, or leave it blank.')
                record['deadline']=deadline
            for key in ('requirements','style_notes'):
                if key in payload:record[key]=text(payload[key])
            if 'supporting_attachment_ids'in payload:
                ids=payload['supporting_attachment_ids']
                if not isinstance(ids,list)or len(ids)>100 or any(not isinstance(value,str)or not re.fullmatch(r'N-[a-f0-9]{16}',value)for value in ids):raise ValueError('Choose the supporting files saved for this person.')
                person=read_json(self.student_path(record['student_id']))
                allowed={item['id']for item in person.get('notes_attachments',[])}
                if not set(ids)<=allowed:raise ValueError('Supporting files must belong to this person.')
                record['supporting_attachment_ids']=list(dict.fromkeys(ids))
            for key in ['recipient_lines','selected_facts']:
                if key in payload:
                    if not isinstance(payload[key],list):raise ValueError('Check recipient lines and selected facts.')
                    record[key]=[text(x,10000)for x in payload[key]if x]
            if 'needs_review'in payload:
                if not isinstance(payload['needs_review'],bool):raise ValueError('Confirm whether the imported body has been reviewed.')
                record['needs_review']=payload['needs_review']
            if 'approved_style_example'in payload:
                if payload['approved_style_example']is True and record.get('needs_review'):raise ValueError('Review the imported body before approving it as a writing example.')
                record['approved_style_example']=payload['approved_style_example']is True
            if 'source_file_id'in payload or 'source_file_ids'in payload:
                source_ids=payload.get('source_file_ids',record.get('source_file_ids',[]))
                if not isinstance(source_ids,list)or len(source_ids)>200 or any(not isinstance(x,str)for x in source_ids):raise ValueError('Check the source originals.')
                primary=payload.get('source_file_id',record.get('source_file_id'))
                if primary is not None and not isinstance(primary,str):raise ValueError('Check the primary source original.')
                source_ids=list(dict.fromkeys([x for x in [primary,*source_ids]if x]))
                files={item['id']:item for item in self.archive_data()['files']}
                for source_id in source_ids:
                    item=files.get(source_id)
                    if not item:raise ValueError('One of the source originals was not found.')
                    if item.get('student_id')!=record['student_id']:raise ValueError('Link each source original to this person before attaching it.')
                record['source_file_ids']=source_ids
                if primary:record['source_file_id']=primary
                elif 'source_file_id'in payload:record.pop('source_file_id',None)
            if 'source_text_versions'in payload:
                versions=payload['source_text_versions']
                if not isinstance(versions,list)or len(versions)>200:raise ValueError('Check the preserved source text versions.')
                existing={row['source_file_id']:row for row in record.get('source_text_versions',[])}
                current={item['id']:item for item in self.archive_data()['files']}
                for row in versions:
                    if not isinstance(row,dict):raise ValueError('Check the preserved source text version.')
                    clean={key:text(row.get(key,''),maximum)for key,maximum in [('source_file_id',100),('original_name',1000),('sha256',64),('source_format',30),('classification',100)]}
                    value=row.get('text')
                    if not isinstance(value,str)or len(value)>200000:raise ValueError('Keep the extracted source text within 200,000 characters.')
                    clean['text']=value
                    if not re.fullmatch(r'F[a-f0-9]{20}',clean['source_file_id'])or not re.fullmatch(r'[a-f0-9]{64}',clean['sha256'])or not clean['original_name']or not clean['text'].strip()or clean['source_format']not in ('pdf','docx','txt'):raise ValueError('Keep the original source identity, name, format, SHA-256, and nonempty extracted text.')
                    old=existing.get(clean['source_file_id'])
                    if old:
                        if clean!=old:raise ValueError('A preserved source text version cannot be overwritten. Keep the original extraction and edit the letter body instead.')
                        continue
                    original=current.get(clean['source_file_id'])
                    if not original or original.get('student_id')!=record['student_id']or original.get('sha256')!=clean['sha256']:raise ValueError('Verify and link the original source before preserving its extracted text.')
                    if original['extension'].lstrip('.')!=clean['source_format']:raise ValueError('The preserved text format must match the original source.')
                    existing[clean['source_file_id']]=clean
                if sum(len(row['text'])for row in existing.values())>2_000_000:raise ValueError('This letter has too much source text to store in one record.')
                record['source_text_versions']=list(existing.values())
            record.pop('source_originals',None)
            record['updated']=now();atomic_json(p,record);return self._decorate_letter(record)
    def link_archive(self,payload):
        student_id=payload.get('student_id');self.student(student_id)
        group_id=payload.get('group_id')
        if not any(r['id']==group_id for r in self.archive_data()['groups']):raise ValueError('Choose an archive group.')
        with self.lock:
            links=read_json(self.links_path,{});existing=links.get(group_id)
            if 'expected_student_id'in payload and existing!=payload['expected_student_id']:raise ValueError('The archive link changed. Refresh it before making changes.')
            if existing and existing!=student_id:raise ValueError('This archive group is already linked to another person. Review the existing link before changing it.')
            links[group_id]=student_id;atomic_json(self.links_path,links)
        return {'message':'Archive group linked. Originals remain preserved.'}
    def archive_file(self,identity):
        item=next((r for r in self.archive_data()['files']if r['id']==identity),None)
        if not item:raise ValueError('Archive file not found.')
        p=(self.archive_root/item['path']).resolve()
        allowed=any(not root.is_symlink()and not getattr(root,'is_junction',lambda:False)()and root.resolve().is_relative_to(self.root)and p.is_relative_to(root.resolve())for root in self.source_roots)
        if not allowed or not p.is_file():raise ValueError('Archive file is unavailable.')
        return p,item
    def import_letter(self,payload):
        # The running server owns this lock. Repeated local imports return the
        # existing editable record rather than creating duplicate applications.
        with self.lock:
            student=self.student(payload.get('student_id'));p,item=self.archive_file(payload.get('file_id'))
            linked=item.get('student_id')
            if linked and linked!=student['id']:raise ValueError('This original is linked to another person. Review that link before importing.')
            source_ids=payload.get('source_file_ids',[item['id']])
            if not isinstance(source_ids,list)or len(source_ids)>200 or any(not isinstance(x,str)for x in source_ids):raise ValueError('Check the source originals.')
            source_ids=list(dict.fromkeys([item['id'],*source_ids]));items=[]
            for source_id in source_ids:
                _,source=self.archive_file(source_id)
                if source.get('student_id')and source['student_id']!=student['id']:raise ValueError('One of these originals is linked to another person.')
                items.append(source)
            existing=[]
            for path in self.students_root.glob('REC-*/Letters/L-*.json'):
                candidate=read_json(path)
                if set(source_ids)&set(self._source_ids(candidate)):existing.append(candidate)
            if existing:
                if len(existing)!=1 or existing[0]['student_id']!=student['id']:raise ValueError('These originals already belong to another letter or person. Review the existing records.')
                record=existing[0]
                for source in items:self.link_archive({'student_id':student['id'],'group_id':source['group_id']})
                return self.save_letter({'source_file_ids':list(dict.fromkeys([*self._source_ids(record),*source_ids]))},record['id'])
            result=archive.extract_editable_letter(p)
            if not result.get('text','').strip():raise ValueError('No editable text was found. This file may need local OCR or manual transcription.')
            body=result['text'];flags=result.get('flags',[])[:]
            salutation='';header='';recipient_lines=[];date=''
            opening=re.search(r'(?m)^\s*((?:Dear\b[^\n]*|To Whom It May Concern[^\n]*)[,:])\s*$',body,re.I)
            if opening:
                header=body[:opening.start()];salutation=opening.group(1).strip();body=body[opening.end():].strip()
                flags.append('Opening/header removed at the detected salutation; review the extracted body.')
            else:flags.append('No clear salutation was found; retained the extracted text for review.')
            # Only an unambiguous full English month/day/year line establishes
            # a historical date. Never replace an unknown old date with today.
            months={name.casefold():i for i,name in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
            date_matches=list(re.finditer(r'(?m)^\s*('+'|'.join(months)+r')\s+(\d{1,2}),?\s+(\d{4})\s*$',header,re.I))
            dates=[]
            for match in date_matches:
                try:dates.append(datetime(int(match[3]),months[match[1].casefold()],int(match[2])).date().isoformat())
                except ValueError:pass
            if len(set(dates))==1:date=dates[0]
            if not date:flags.append('The original date was not unambiguously recognized; add or verify it before making a PDF preview.')
            if date and len(date_matches)==1:
                block=header[date_matches[0].end():].strip();lines=[line.strip()for line in block.splitlines()if line.strip()]
                if 0<len(lines)<=8 and all(len(line)<=200 for line in lines)and re.search(r'\b(?:Admissions?|Selection Committee|Scholarship Committee|Fellowship Committee|Hiring Committee|Search Committee|Graduate Program|Graduate School)\b|^To:',block,re.I):recipient_lines=lines
            if not recipient_lines:flags.append('Recipient address was not unambiguously recognized; compare the original before reuse.')
            ending=re.search(r'(?m)^\s*(?:Sincerely|Yours sincerely|Yours truly|Best regards|Respectfully)[,\s]*$',body,re.I)
            if ending:body=body[:ending.start()].strip()
            body=self.anonymize(body,student)[0]
            for source in items:self.link_archive({'student_id':student['id'],'group_id':source['group_id']})
            letter=self.save_letter({'student_id':student['id'],'title':p.stem,'body':body,'purpose':'Historical letter; review recipient and purpose before adapting.','date':date,'salutation':salutation,'recipient_lines':recipient_lines,'historical':True,'source_file_id':item['id'],'source_file_ids':source_ids,'needs_review':True,'approved_style_example':False})
            record=read_json(self.letter_path(letter['id']));record['source_extraction_flags']=flags
            atomic_json(self.letter_path(letter['id']),record)
            return self._decorate_letter(record)
    def anonymize(self,value,student):
        value=str(value)
        name_placeholder='[PERSON]'if student.get('person_type')=='instructor'else'[STUDENT]'
        names=set(student.get('aliases',[])+[student.get('name',''),natural_name(student.get('name',''))])
        natural=natural_name(student.get('name',''));parts=natural.split()
        if parts:names.update([parts[0],parts[-1]])
        for name in sorted((n for n in names if len(n.strip())>=2),key=len,reverse=True):
            value=re.sub(r'(?<!\w)'+re.escape(name)+r'(?!\w)',name_placeholder,value,flags=re.I)
        for key,placeholder in [('ruid','[STUDENT_ID]'),('netid','[NETID]')]:
            if student.get(key):value=re.sub(r'(?<!\w)'+re.escape(student[key])+r'(?!\w)',placeholder,value,flags=re.I)
        value=re.sub(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b','[EMAIL]',value,flags=re.I)
        value=re.sub(r'(?<!\d)\d{9}(?!\d)','[STUDENT_ID]',value)
        value=re.sub(r'(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)','[PHONE]',value)
        return value,['Review distinctive interview details, organizations, achievements, and third-party names for indirect identification.']
    def brief(self,identity,payload):
        letter=self.letter(identity);student=self.student(letter['student_id'])
        instructor=student.get('person_type')=='instructor'
        lines=['RECOMMENDATION LETTER DRAFTING BRIEF',f"Local record: {student['id']} / {letter['id']}",f"Recommendation subject: {'instructor'if instructor else'student'}",'','Write a tailored letter in my voice. Do not use a fixed recommendation form.',f"Use only supported observations and supplied facts. Keep {'instructor'if instructor else'student'} statements distinct from my observations. Do not invent achievements, rankings, character traits, or endorsement strength.",'Return the letter body using [PERSON] (or [STUDENT] for a student), [FIRST_NAME], [LAST_NAME], [PRONOUN_SUBJECT], [PRONOUN_OBJECT], and [PRONOUN_POSSESSIVE] as needed. Identifying details will be inserted locally.','',f"Application purpose: {letter.get('purpose','')}",f"Desired strength of endorsement: {letter.get('strength','')}",f"Application-specific directions: {letter.get('notes','')}",'']
        for key,label in [('application_type','Application type'),('deadline','Application deadline'),('requirements','Application requirements'),('style_notes','Application writing guidance')]:
            if letter.get(key):lines.extend([label+':',letter[key],''])
        if letter.get('supporting_attachment_ids'):lines.extend(['Supporting files are saved locally. Their contents are not included here unless explicitly reviewed and added to the notes.',''])
        for key,label in [('relationship','Relationship/context'),('observations','My observations'),('student_statements','Instructor-reported information'if instructor else'Student-reported information'),('interview','Interview notes'),('plans','Plans and educational outlook')]:
            if student['notes'].get(key):lines.extend([label+':',student['notes'][key],''])
        selected=letter.get('selected_facts',[])
        selected_terms={fact for fact in selected if re.fullmatch(r'(Sp|Fa)\d{2}',fact)}
        for fact in selected:
            if fact not in selected_terms and not re.fullmatch(r'other-course:\d+',fact):lines.append('Selected fact: '+fact)
        if payload.get('include_grades')and not instructor:
            lines.append('\nSaved course facts for '+student.get('grade_course_name','linked course')+':')
            for record in student['grades'].get('records',[]):
                if record['semester']not in selected_terms:continue
                value=f"{record['semester']}: official grade {record.get('grade')or 'pending'}"
                if record.get('average')is not None:value+=f"; saved course average {record['average']:.2f}/100"
                lines.append(value)
                if payload.get('include_ranks'):
                    for key,label in [('semester_rank','Semester'),('year_rank','Academic-year'),('overall_rank','All-history')]:
                        rank=record.get(key)
                        if rank:lines.append(f"  {label}: rank {rank['rank']} of {rank['total']} course attempts; midpoint percentile {rank['percentile']:.2f}.")
            lines.extend(student['grades'].get('notes',[]))
        if payload.get('include_grades'):
            for i,record in enumerate(student.get('other_courses',[])):
                if 'other-course:'+str(i)not in selected:continue
                value=f"{record['course']} ({record['semester']or 'semester not recorded'}): locally saved grade {record['grade']or 'not recorded'}"
                if record.get('average')is not None:value+=f"; saved course average {record['average']:.2f}/100"
                lines.append(value)
        preferences=(self.tools/'writing-preferences.txt').read_text(encoding='utf8')if(self.tools/'writing-preferences.txt').exists()else''
        if preferences:lines.extend(['','Writing preferences:',preferences])
        if letter.get('body'):lines.extend(['','Current body to adapt, if useful:',letter['body']])
        for p in self.students_root.glob('REC-*/Letters/L-*.json'):
            example=read_json(p)
            if example.get('approved_style_example')and not example.get('needs_review')and example['id']!=letter['id']:
                example_student=read_json(self.student_path(example['student_id']))
                sample=self.anonymize(example.get('body',''),example_student)[0]
                lines.extend(['','Reviewed anonymized writing example (voice only; do not reuse its factual claims):',sample])
                if len(lines)>200:break
        result,flags=self.anonymize('\n'.join(lines),student)
        path=None;url=None;receipt_path=None;handoff=None
        if payload.get('reviewed')is True:
            reviewed=payload.get('text',payload.get('reviewed_text'))
            if not isinstance(reviewed,str):raise ValueError('Preview and review the exact brief text before exporting it.')
            if reviewed is not None:
                if not isinstance(reviewed,str)or not reviewed.strip()or len(reviewed)>1_000_000:raise ValueError('Review the brief text before exporting it.')
                scrubbed,_=self.anonymize(reviewed,student)
                if scrubbed!=reviewed:raise ValueError('Known student identifiers remain in the reviewed brief. Replace them with placeholders before exporting.')
                result=reviewed
            stamp=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(2)
            p=self.tools/'Approved Briefs'/(student['id']+'-'+identity+'-'+stamp+'.txt')
            p.write_bytes(result.encode('utf8'));path=str(p);url='/api/briefs/'+p.name
            receipt_path=str(p.with_suffix('.json'))
            approved_attachments=[]
            if payload.get('authorize_attachments')is True:
                for attachment_id in letter.get('supporting_attachment_ids',[]):
                    attachment=self.note_attachment_path(student['id'],attachment_id)
                    approved_attachments.append({'id':attachment_id,'path':str(attachment),'sha256':hashlib.sha256(attachment.read_bytes()).hexdigest()})
            atomic_json(p.with_suffix('.json'),{'authorized_attachments':approved_attachments,'student_id':student['id'],'letter_id':identity,'approved_at':now(),'brief_sha256':hashlib.sha256(result.encode('utf8')).hexdigest(),'body_sha256':hashlib.sha256(letter.get('body','').encode('utf8')).hexdigest()})
            handoff='Use only the approved local drafting brief at '+path+'. Write a tailored letter body with the supplied identity placeholders. Do not open private person records, grade files, supporting files, or original letters. Return the draft for local review; do not sign or send it.'
        return {'text':result,'flagged_terms':flags,'path':path,'download_url':url,'receipt_path':receipt_path,'handoff':handoff,'authorized_attachments':approved_attachments if payload.get('reviewed')is True else []}
    def apply_draft(self,identity,body,brief_path):
        p=Path(brief_path).resolve();allowed=(self.tools/'Approved Briefs').resolve()
        if p.parent!=allowed or not p.is_file():raise ValueError('Choose an approved brief saved by this app.')
        receipt=read_json(p.with_suffix('.json'),{})
        letter=self.letter(identity)
        if receipt.get('letter_id')!=identity or receipt.get('student_id')!=letter['student_id']:raise ValueError('This brief belongs to a different letter.')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=receipt.get('brief_sha256'):raise ValueError('The approved brief changed after review. Review and export it again.')
        if hashlib.sha256(letter.get('body','').encode('utf8')).hexdigest()!=receipt.get('body_sha256'):raise ValueError('The saved letter changed after the brief was exported. Review the new draft in the app before replacing it.')
        student=self.student(letter['student_id']);body=text(body)
        if self.anonymize(body,student)[0]!=body:raise ValueError('Use placeholders for student identities in the draft body.')
        return self.save_letter({'body':body,'needs_review':True,'approved_style_example':False},identity)
    def substitutions(self,student):
        name=natural_name(student['name']);parts=name.split()
        pronouns={'he/him':('he','him','his'),'she/her':('she','her','her')}.get(student.get('pronouns','').casefold(),('they','them','their'))
        return {'[PERSON]':name,'[STUDENT]':name,'[FIRST_NAME]':parts[0]if parts else name,'[LAST_NAME]':student['name'].split(',')[0].strip()if ','in student['name']else(parts[-1]if parts else name),'[PRONOUN_SUBJECT]':pronouns[0],'[PRONOUN_OBJECT]':pronouns[1],'[PRONOUN_POSSESSIVE]':pronouns[2]}
    def _register_generated_source(self,student,letter,destination,pdf_sha,revision,profile):
        relative=destination.relative_to(self.root).as_posix()
        if not destination.resolve().is_relative_to((self.root/'Letters').resolve()):raise ValueError('The generated signed PDF is outside the letters folder.')
        index=read_json(self.archive_path,{'root':str(self.root),'files':[],'groups':[],'errors':[],'summary':{}})
        identities=read_json(self.source_identities_path,{})
        if relative in identities or any(item['path']==relative for item in index['files']):raise ValueError('This signed source is already indexed. Review the existing copy before generating another.')
        reserved={item['id']for item in index['files']}|{item['id']for item in identities.values()}
        identity=archive._stable_id(relative)
        if identity in reserved:identity=archive._stable_id('generated-signed:'+relative+':'+pdf_sha)
        if identity in reserved:raise ValueError('The new signed source identity needs review.')
        group_id=archive._stable_id('generated-signed-letter:'+letter['id'],'G')
        links=read_json(self.links_path,{})
        if links.get(group_id)not in(None,student['id']):raise ValueError('The signed-letter group belongs to another person.')
        signature=Path(profile['signature_file'])
        if not signature.is_absolute():signature=self.profile_path.parent/signature
        verification={'method':'canonical_renderer_after_author_approval','revision':revision,'signature_sha256':hashlib.sha256(signature.read_bytes()).hexdigest(),'body_sha256':hashlib.sha256(letter['body'].encode('utf8')).hexdigest()}
        item={'id':identity,'path':relative,'display_name':destination.name,'extension':'.pdf','sha256':pdf_sha,'bytes':destination.stat().st_size,'signed':True,'group_id':group_id,'duplicate_of':None,'status':'original','tentative_label':student['name'],'group_reason':'approved_generated_letter','original_path':relative,'classification':'signed','signature_verified':True,'signature_verification':verification,'identity_status':'preserved'}
        index['files'].append(item)
        group=next((row for row in index['groups']if row['id']==group_id),None)
        if group:group['files'].append(identity)
        else:index['groups'].append({'id':group_id,'label':student['name']+' — '+letter.get('title','Recommendation'),'tentative':False,'files':[identity],'match_reason':'approved_generated_letter'})
        seen={}
        for row in sorted(index['files'],key=lambda row:row['path'].casefold()):
            row['duplicate_of']=seen.get(row['sha256']);seen.setdefault(row['sha256'],row['id']);row['status']='exact_duplicate'if row['duplicate_of']else'original'
        index['summary'].update(files=len(index['files']),groups=len(index['groups']),signed_pdfs=sum(bool(row.get('signed'))and row['extension']=='.pdf'for row in index['files']),duplicates=sum(bool(row.get('duplicate_of'))for row in index['files']),bytes=sum(row['bytes']for row in index['files']),errors=len(index.get('errors',[])))
        identities[relative]={key:item[key]for key in ('id','group_id','sha256','original_path','classification','signed','signature_verified','signature_verification')};links[group_id]=student['id']
        atomic_json(self.source_identities_path,identities);atomic_json(self.links_path,links);atomic_json(self.archive_path,index)
        return identity
    def build(self,identity,payload):
        with self.lock:
            letter=self.letter(identity);student=self.student(letter['student_id']);final=payload.get('final')is True
            if final and letter.get('historical'):raise ValueError('Historical letters keep their original signed files. Copy this letter for a new application before signing a new version.')
            if final and payload.get('approved')is not True:raise ValueError('Approve the complete letter before signing it.')
            if final and letter.get('needs_review'):raise ValueError('Review the imported body, confirm that review, and save the letter before signing it.')
            if not letter.get('body','').strip():raise ValueError('Add the letter body first.')
            if not letter.get('date','').strip():raise ValueError('Add or verify the letter date before making a PDF.')
            profile=read_json(self.profile_path,{})
            if shared_signature:profile=shared_signature.apply(profile)
            if final and not profile.get('signature_file'):raise ValueError('Choose the local signature file in Writing Preferences before signing.')
            def fill(value):
                for key,replacement in self.substitutions(student).items():value=value.replace(key,replacement)
                return value
            body=fill(letter['body'])
            if final and re.search(r'\[[A-Z][A-Z0-9 _-]{1,60}\]',body):raise ValueError('Replace the remaining placeholders before signing.')
            data={'schema_version':1,'date':fill(letter['date']),'recipient_lines':[fill(x)for x in letter['recipient_lines']],'subject':'','salutation':fill(letter['salutation']),'running_label':'Letter of recommendation','layout':'standard','closing':'Sincerely,','paragraphs':[p.strip()for p in re.split(r'\n\s*\n',body)if p.strip()]}
            if final and any(re.search(r'\[[A-Z][A-Z0-9 _-]{1,60}\]',v)for v in [*data['recipient_lines'],data['date'],data['salutation']]):raise ValueError('Complete recipient and date placeholders before signing.')
            repo=Path(self.settings.get('mh_git',''));renderer=repo/'professional-correspondence/recommendations/render_letter.py'
            if not renderer.is_file():raise ValueError('The mh-git recommendation renderer is unavailable. Check Writing Preferences.')
            executable=Path(shared_tex.executable(Path(__file__).resolve().parents[5],'pdflatex',self.settings.get('pdflatex','')))
            if not executable.is_file():raise ValueError('The local PDF compiler is unavailable. Check Writing Preferences.')
            spec=importlib.util.spec_from_file_location('mh_recommendation_renderer',renderer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            source=module.render(data,profile,self.profile_path.parent,final=final)
            with tempfile.TemporaryDirectory(prefix='letter-',dir=self.tools/'Build Cache')as directory:
                directory=Path(directory);tex=directory/'letter.tex';tex.write_text(source,encoding='utf8')
                env=os.environ.copy();env['TEXINPUTS']=(repo/'lib').as_posix()+';'+(repo/'img').as_posix()+';'+env.get('TEXINPUTS','')+';'
                for _ in range(2):
                    result=subprocess.run([str(executable),'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error','letter.tex'],cwd=directory,env=env,capture_output=True,timeout=90)
                    if result.returncode:
                        (self.tools/'logs'/'last-build-private.log').write_bytes(result.stdout+b'\n'+result.stderr)
                        raise ValueError('The PDF could not compile. Details are in the local build log; your saved letter is unchanged.')
                pdf=directory/'letter.pdf'
                if not pdf.is_file():raise ValueError('The compiler did not produce a PDF.')
                if final:
                    numbers=[int(row['id'].split('-')[1])for row in letter['revisions']if re.fullmatch(r'signed-\d+',str(row.get('id','')))]
                    revision='signed-'+str(max(numbers,default=0)+1).zfill(2)
                    if self.consolidated_sources:
                        folder=self.root/'Letters';folder.mkdir(exist_ok=True)
                        if folder.is_symlink()or getattr(folder,'is_junction',lambda:False)()or not folder.resolve().is_relative_to(self.root):raise ValueError('The letters folder must be a regular local project folder.')
                        destination=folder/publication_filename(student,letter['date'],identity,revision)
                    else:
                        folder=self.student_path(student['id']).parent/'Letters'/identity;folder.mkdir(exist_ok=True)
                        destination=folder/(safe_stem(letter['date'])+'-'+safe_stem(letter['title'])+'-'+revision+'.pdf')
                    if destination.exists():raise ValueError('That signed version already exists.')
                    # On Windows rename refuses to overwrite an existing PDF.
                    # Source and destination are on the same project drive.
                    for attempt,delay in enumerate((.05,.1,.2,.35,.5,.75,1.0,0)):
                        try:pdf.rename(destination);break
                        except PermissionError:
                            if attempt==7:raise
                            time.sleep(delay)
                    pdf_sha=hashlib.sha256(destination.read_bytes()).hexdigest()
                    if self.consolidated_sources:
                        source_id=self._register_generated_source(student,letter,destination,pdf_sha,revision,profile)
                        letter['source_file_ids']=list(dict.fromkeys([*self._source_ids(letter),source_id]));letter['source_file_id']=source_id
                    record={'id':revision,'date':now(),'kind':'signed','path':destination.relative_to(self.root).as_posix(),'pdf_url':'/api/pdfs/'+identity+'/'+revision,'body':letter['body'],'recipient_lines':letter['recipient_lines'][:],'letter_date':letter['date'],'title':letter['title'],'resolved_letter':data,'author_profile':profile,'student_name_at_signing':student['name'],'purpose':letter['purpose'],'strength':letter['strength'],'sha256':pdf_sha}
                    letter['revisions'].append(record);letter['needs_review']=False;letter.pop('source_originals',None);atomic_json(self.letter_path(identity),letter)
                else:
                    destination=self.tools/'Build Cache'/(identity+'-draft.pdf');shutil.copy2(pdf,destination);revision='draft'
            return {'pdf_url':'/api/pdfs/'+identity+'/'+revision,'revision':revision}
    def pdf_path(self,identity,revision):
        if revision=='draft':p=self.tools/'Build Cache'/(self.letter(identity)['id']+'-draft.pdf')
        else:
            letter=self.letter(identity);r=next((r for r in letter['revisions']if r['id']==revision),None)
            if not r:raise ValueError('Signed version not found.')
            p=self.root/r['path']
        p=p.resolve()
        if not p.is_relative_to(self.root)or not p.is_file():raise ValueError('PDF unavailable.')
        return p
    def save_profile(self,payload):
        profile=payload.get('profile',payload)
        if shared_signature and isinstance(profile,dict) and profile.get('signature_changed') is False:profile={**profile,'signature_file':shared_signature.current()}
        if not isinstance(profile,dict)or not isinstance(profile.get('sender'),dict):raise ValueError('Check the author profile.')
        clean={'sender':{k:text(profile['sender'].get(k,''),2000)for k in ('name','title','department')}}
        contacts=profile['sender'].get('contact_lines',[])
        if not isinstance(contacts,list):raise ValueError('Contact lines must be a list.')
        clean['sender']['contact_lines']=[text(v,2000)for v in contacts]
        for key in ('signature_file','letterhead_file'):
            value=profile.get(key)or None
            if value:
                p=Path(text(value,2000))
                if not p.is_absolute()or not p.is_file():raise ValueError('Choose an existing local signature or letterhead file.')
                value=str(p)
            clean[key]=value
        if shared_signature:
            clean['signature_file']=shared_signature.validate(clean.get('signature_file')) if profile.get('signature_changed',True) else shared_signature.current()
        if 'unit_lines'in profile:clean['unit_lines']=[text(x,2000)for x in profile['unit_lines']]
        with self.lock:
            atomic_json(self.profile_path,clean)
            if isinstance(payload.get('settings'),dict):
                for key in ('grade_database','mh_git','pdflatex'):
                    if key in payload['settings']:self.settings[key]=text(payload['settings'][key],2000)
                atomic_json(self.config_path,self.settings)
        if shared_signature and profile.get('signature_changed',True):shared_signature.save(clean['signature_file'])
        return {'message':'Writing preferences saved locally.','profile':clean,'settings':self.settings}
