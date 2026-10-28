"""Course grade storage and reversible imports. No outbound network access."""
from pathlib import Path
from collections import defaultdict, Counter
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from html.parser import HTMLParser
from contextlib import contextmanager,closing
from decimal import Decimal
import base64, csv, datetime, hashlib, io, json, os, re, secrets, shutil, sqlite3, threading, time, uuid
import analytics
import record_filters
import teacher_links
from backup_archive import create_snapshot,snapshot_database
from school_filter_options import build_filter_options

NOW=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
GRADES={'A','B+','B','C+','C','D','F','XF','W','TZ','TTF','Z','NG','I','IN','P','S','U','NC','NP','PA','T','TN','TD','TB','TC'}
LABELS={'homework':'Homework average','quiz':'Quiz average','recitation':'Recitation average','wrappers':'Exam wrappers and surveys','precalculus':'Precalculus exam','readiness':'Readiness test','final':'Final exam'}
clean=lambda x: str(x).strip() if x is not None else ''
norm=lambda x:re.sub(r'[^a-z0-9]','',clean(x).lower())

def number(x):
    return analytics.finite_number(clean(x).rstrip('%'))
def ruid(x):
    s=clean(x).lstrip("'")
    if re.fullmatch(r'\d{9}\.0',s):s=s[:-2]
    return s if re.fullmatch(r'\d{9}',s) else None
def netid(x):
    s=clean(x).lower()
    return s if re.fullmatch(r'[a-z][a-z0-9._-]{1,24}',s) else None
def grade(x):
    s=analytics.normalize_grade(x)
    if s in ['', '--','-','*','**','***','N/A','NA']:return None
    if s not in GRADES:raise ValueError('Unrecognized letter grade or status.')
    return s
def semester(x):
    s=clean(x)
    m=re.fullmatch(r'(sp|s|fa|f|su)(\d{2})',s,re.I)
    if m:return {'sp':'Sp','s':'Sp','fa':'Fa','f':'Fa','su':'Su'}[m[1].lower()]+m[2]
    m=re.search(r'(?i)(spring|fall|summer)[ _\t-]*(?:20)?(\d{2})(?!\d)',s)
    if m:return {'spring':'Sp','fall':'Fa','summer':'Su'}[m[1].lower()]+m[2]
    m=re.search(r'(20\d{2})(SP|FA|SU)',s,re.I)
    if m:return m[2].title()+m[1][-2:]
    raise ValueError('Choose a semester, such as Fall 2026 or Sp27.')
def term_label(t):return {'Sp':'Spring','Fa':'Fall','Su':'Summer'}.get(t[:2],t)+' '+str(2000+int(t[2:]))
def section(x):
    s=clean(x)
    if re.fullmatch(r'\d{1,3}(?:\.0)?',s):return str(int(float(s))).zfill(3)
    if re.fullmatch(r'[A-Za-z]{1,3}\d{0,3}|\d{1,3}[A-Za-z]',s):return s.upper()
    for pattern in [r'640\s*[:_-]\s*\d{3}\s*[:_-]\s*(\d{1,3})(?!\d)',r'\b\d{3}\s*[:_-]\s*(\d{1,3})(?!\d)',r'(?i)sections?\s*[:#_-]?\s*(\d{1,3})(?!\d)',r'(?i)sec\.?\s*[:#_-]?\s*(\d{1,3})(?!\d)']:
        m=re.search(pattern,s)
        if m:return m[1].zfill(3)
    return ''
def values(params,key):
    v=params.get(key,[])
    if v is None:return []
    return [str(x)for x in (v if isinstance(v,list)else[v])if str(x)!='']
def one(params,key,default=None):
    v=params.get(key,default)
    return v[0]if isinstance(v,list)and v else default if isinstance(v,list)else v
def code(x,width):
    s=clean(x)
    if s.endswith('.0')and s[:-2].isdigit():s=s[:-2]
    return s.zfill(width)if s.isdigit()else s or None
def safe_csv(v):
    s=''if v is None else str(v)
    return "'"+s if s.lstrip().startswith(('=','+','-','@'))and number(s)is None else s
def label(key):
    return LABELS.get(key,re.sub(r'(?i)^midterm(\d+)$',r'Midterm \1',key).replace('_',' ').capitalize())
def column_key(header):
    m=re.search(r'\((\d+)\)\s*$',header)
    return 'id:'+m[1]if m else'name:'+norm(header)

class HTMLTable(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=[];self.cell=None
    def handle_starttag(self,t,a):
        if t=='tr':self.row=[]
        if t in ['td','th']:self.cell=''
    def handle_data(self,s):
        if self.cell is not None:self.cell+=s
    def handle_endtag(self,t):
        if t in ['td','th']and self.cell is not None:self.row.append(self.cell);self.cell=None
        if t=='tr'and self.row:self.rows.append(self.row)

def tables(raw,filename):
    """Read CSV, Excel XML/HTML exports and XLSX without executing formulas."""
    if raw.startswith(b'PK'):
        result=[]
        with ZipFile(io.BytesIO(raw))as z:
            if sum(i.file_size for i in z.infolist())>180_000_000:raise ValueError('This workbook is too large. Please export a CSV instead.')
            strings=[''.join(x.itertext())for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]if 'xl/sharedStrings.xml'in z.namelist()else[]
            percent_styles=set()
            if 'xl/styles.xml'in z.namelist():
                styles=ET.fromstring(z.read('xl/styles.xml'));formats={int(x.attrib['numFmtId']):x.attrib.get('formatCode','')for x in styles.findall('m:numFmts/m:numFmt',NS)}
                xfs=styles.find('m:cellXfs',NS)
                if xfs is not None:
                    for i,xf in enumerate(xfs):
                        fmt=int(xf.attrib.get('numFmtId','0'));pattern=re.sub(r'"[^"]*"|\\.','',formats.get(fmt,''))
                        if fmt in [9,10]or'%'in pattern:percent_styles.add(i)
            rels={x.attrib['Id']:x.attrib['Target']for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
            for sh in ET.fromstring(z.read('xl/workbook.xml')).find('m:sheets',NS):
                target=rels[sh.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']];part=target.lstrip('/')if target.startswith('/')else'xl/'+target
                rows=[]
                for row in ET.fromstring(z.read(part)).findall('m:sheetData/m:row',NS):
                    resultrow={}
                    for c in row:
                        if not c.tag.endswith('}c'):continue
                        m=re.match(r'([A-Z]+)',c.attrib.get('r',''))
                        if not m:continue
                        idx=0
                        for ch in m[1]:idx=idx*26+ord(ch)-64
                        v=c.findtext('m:v',None,NS);typ=c.attrib.get('t','n')
                        if typ=='s':v=strings[int(v)]if v else None
                        elif typ=='inlineStr':v=''.join(c.find('m:is',NS).itertext())
                        elif typ=='e':v=None
                        elif v is not None and int(c.attrib.get('s','0'))in percent_styles:
                            try:v=str(Decimal(v)*100)
                            except Exception:pass
                        resultrow[idx-1]=v
                    rows.append([resultrow.get(i,'')for i in range(max(resultrow,default=-1)+1)])
                result.append((sh.attrib['name'],rows))
        return result
    if raw.startswith(b'\xd0\xcf\x11\xe0'):raise ValueError('Please save this older Excel file as CSV or XLSX, then import it.')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('cp1252')
    if re.search(r'<(?:html|table)\b',text[:1000],re.I):
        parser=HTMLTable();parser.feed(text);return [('Spreadsheet',parser.rows)]
    if '<Workbook'in text or 'urn:schemas-microsoft-com:office:spreadsheet'in text:
        xml=ET.fromstring(text);ss={'s':'urn:schemas-microsoft-com:office:spreadsheet'};out=[]
        for sh in xml.findall('s:Worksheet',ss):
            rows=[]
            for r in sh.findall('s:Table/s:Row',ss):
                row=[]
                for c in r.findall('s:Cell',ss):
                    idx=int(c.attrib.get('{'+ss['s']+'}Index',len(row)+1))
                    row.extend(['']*max(0,idx-1-len(row)));row.append(c.findtext('s:Data','',ss))
                rows.append(row)
            out.append((sh.attrib.get('{'+ss['s']+'}Name','Sheet'),rows))
        return out
    # REGIS preambles mix tabs and commas. Choose the delimiter from its header,
    # rather than the long whitespace-filled preamble.
    lines=text.splitlines();candidate=next((s for s in lines[:30]if 'Student'in s and ('Grade'in s or 'SIS'in s)),None)
    if candidate:delimiter=max([',','\t',';'],key=lambda c:candidate.count(c))
    else:
        try:delimiter=csv.Sniffer().sniff(text[:12000],delimiters=',;\t').delimiter
        except csv.Error:delimiter=','
    return [('CSV',list(csv.reader(io.StringIO(text),delimiter=delimiter)))]

ALIASES={'ruid':['ruid','rutgersid','studentid','id'],'netid':['netid','sisloginid','sisuserid','username'],'name':['student','name','studentname'],'grade':['proposedgrade','proposedlettergrade','grade','finalgrade','lettergrade','coursegrade'],'section':['sec','section','sectionnumber'],'unit':['unit','school','schoolcode'],'class':['class','classyear','gradyear'],'curric':['curric1','curric','curriculum','major'],'instructor':['instructor','instructorname'],'lecturer':['lecturer','lectureinstructor'],'recitation':['recitation','recitationinstructor','ta'],'lecturer_email':['lectureremail','lectureemail'],'recitation_email':['recitationemail','taemail'],'email':['email','instructoremail'],'semester':['semester','term']}
def header_map(h):
    names=[norm(x)for x in h];return {k:next(names.index(a)for a in aliases if a in names)for k,aliases in ALIASES.items()if any(a in names for a in aliases)}

APP_SCHEMA='''
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_roster_state(ruid TEXT NOT NULL,semester TEXT NOT NULL,section TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT1,PRIMARY KEY(ruid,semester),FOREIGN KEY(ruid,semester) REFERENCES enrollments(ruid,semester));
CREATE TABLE IF NOT EXISTS app_instructors(semester TEXT NOT NULL,section TEXT NOT NULL,instructor TEXT NOT NULL,email TEXT,PRIMARY KEY(semester,section));
CREATE TABLE IF NOT EXISTS app_proposals(ruid TEXT NOT NULL,semester TEXT NOT NULL,proposed_grade TEXT,source_import TEXT,PRIMARY KEY(ruid,semester),FOREIGN KEY(ruid,semester) REFERENCES enrollments(ruid,semester));
CREATE TABLE IF NOT EXISTS app_policies(semester TEXT PRIMARY KEY REFERENCES semesters(semester),policy_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_imports(import_id TEXT PRIMARY KEY,kind TEXT NOT NULL,filename TEXT NOT NULL,semester TEXT,created_at TEXT NOT NULL,counts TEXT NOT NULL,status TEXT NOT NULL,backup_path TEXT NOT NULL,source_path TEXT,scope TEXT,sections TEXT);
CREATE TABLE IF NOT EXISTS app_column_maps(semester TEXT NOT NULL,header TEXT NOT NULL,mapping TEXT NOT NULL,PRIMARY KEY(semester,header));
CREATE TABLE IF NOT EXISTS app_assessment_labels(assessment_id TEXT PRIMARY KEY,label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_score_cells(ruid TEXT NOT NULL,semester TEXT NOT NULL,assessment_id TEXT NOT NULL,column_key TEXT NOT NULL,percent REAL,status TEXT NOT NULL,raw_id INTEGER NOT NULL,role TEXT NOT NULL,header TEXT NOT NULL,source_id INTEGER NOT NULL,PRIMARY KEY(ruid,semester,assessment_id,column_key));
CREATE TABLE IF NOT EXISTS app_roster_events(import_id TEXT NOT NULL,ruid TEXT NOT NULL,semester TEXT NOT NULL,action TEXT NOT NULL,section TEXT,PRIMARY KEY(import_id,ruid,semester));
CREATE INDEX IF NOT EXISTS app_roster_active ON app_roster_state(semester,section,active);
'''.replace('DEFAULT1','DEFAULT 1')

class Store:
    def __init__(self,database):
        self.path=Path(database).resolve();self.root=self.path.parent;self.lock=threading.RLock();self.previews={}
        existed=self.path.exists()
        if not self.path.exists():
            self.root.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.initializing')
            try:
                db=sqlite3.connect(temporary)
                try:db.executescript(Path(__file__).with_name('empty_database.sql').read_text('utf-8'));db.commit()
                finally:db.close()
                try:
                    if os.name=='nt':temporary.rename(self.path)
                    else:os.link(temporary,self.path)
                except FileExistsError:pass
            finally:temporary.unlink(missing_ok=True)
        metadata={}
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone():metadata=dict(db.execute("SELECT key,value FROM app_settings WHERE key IN ('course_code','course_name','policy_mode')"))
        self.course_code=metadata.get('course_code') or os.environ.get('GVAULT_COURSE_CODE') or '135'
        if not re.fullmatch(r'\d{3}',self.course_code):raise ValueError('Choose a three-digit Rutgers Mathematics course.')
        self.course_name=metadata.get('course_name') or os.environ.get('GVAULT_COURSE_NAME') or 'Math '+self.course_code
        mode=metadata.get('policy_mode') or os.environ.get('GVAULT_POLICY_MODE') or ('legacy135' if existed and self.path.name=='Math_135_Central.sqlite' else 'custom')
        self.legacy_policy=mode=='legacy135' and self.course_code=='135'
        (self.root/'Backups').mkdir(exist_ok=True);(self.root/'Imports').mkdir(exist_ok=True)
        self.migrate()
    @contextmanager
    def connect(self):
        d=sqlite3.connect(self.path,timeout=15);d.row_factory=sqlite3.Row;d.execute('PRAGMA foreign_keys=ON');d.create_function('app_column_key',1,column_key)
        try:
            with d:yield d
        finally:d.close()
    def revision(self,d):
        r=d.execute("SELECT value FROM app_settings WHERE key='revision'").fetchone();return r[0]if r else''
    def touch(self,d):d.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',('revision',uuid.uuid4().hex))
    def backup(self,d,name):
        return create_snapshot(d,self.root/'Backups',name)
    def migrate(self):
        with self.lock,self.connect()as d:
            exists=d.execute("SELECT1 FROM sqlite_master WHERE name='app_settings'".replace('SELECT1','SELECT 1')).fetchone()
            if not exists:self.backup(d,'Before-App-Install.sqlite')
            d.executescript(APP_SCHEMA)
            teacher_links.ensure_teaching(d,Path(__file__).with_name('schedule-mappings.json') if self.legacy_policy else self.root/'course-schedule-mappings.json')
            d.executemany('INSERT OR IGNORE INTO app_settings VALUES(?,?)',[('course_code',self.course_code),('course_name',self.course_name),('policy_mode','legacy135' if self.legacy_policy else 'custom')])
            if not self.revision(d):self.touch(d)
            d.execute('INSERT OR IGNORE INTO app_roster_state(ruid,semester) SELECT ruid,semester FROM enrollments')
            for row in d.execute('SELECT semester,policy_json FROM semesters').fetchall():
                pol=self.default_policy(row['semester'],json.loads(row['policy_json']))
                d.execute('INSERT OR IGNORE INTO app_policies VALUES(?,?)',(row['semester'],json.dumps(pol)))
            # Once only: recover section labels from existing source snapshots.
            if not d.execute("SELECT value FROM app_settings WHERE key='sections_seeded'").fetchone():
                self.seed_sections(d);d.execute("INSERT INTO app_settings VALUES('sections_seeded','1')")
            for a in d.execute('SELECT assessment_id,assessment_key FROM assessment_definitions').fetchall():d.execute('INSERT OR IGNORE INTO app_assessment_labels VALUES(?,?)',(a[0],label(a[1])))
            if not d.execute("SELECT value FROM app_settings WHERE key='score_cells_seeded'").fetchone():
                d.execute('''INSERT OR REPLACE INTO app_score_cells SELECT ruid,semester,assessment_id,cellkey,percent,status,raw_score_id,role,exact_header,source_id FROM (SELECT c.ruid,c.semester,i.assessment_id,CASE WHEN i.role='aggregate' THEN 'aggregate:'||i.assessment_id ELSE app_column_key(i.exact_header) END AS cellkey,r.percent,r.status,r.raw_score_id,i.role,i.exact_header,i.source_id,ROW_NUMBER() OVER(PARTITION BY c.ruid,c.semester,i.assessment_id,CASE WHEN i.role='aggregate' THEN 'aggregate:'||i.assessment_id ELSE app_column_key(i.exact_header) END ORDER BY i.source_id DESC,r.raw_score_id DESC) AS n FROM raw_scores r JOIN input_columns i USING(input_id) JOIN canvas_observations c USING(canvas_row_id) WHERE c.ruid IS NOT NULL AND i.assessment_id IS NOT NULL AND i.role NOT IN ('component','duplicate_component','unadjusted','ancillary','unclassified') AND (i.role<>'raw_readiness' OR c.semester='Fa19')) WHERE n=1''')
                d.execute("INSERT INTO app_settings VALUES('score_cells_seeded','1')")
            d.commit()
    def seed_sections(self,d):
        # Original files are optional for this one-time enrichment. Once stored,
        # all app queries and imports are independent of the old source folder.
        for source in d.execute("SELECT source_id,kind,semester,original_path FROM sources WHERE kind IN ('regis','canvas') ORDER BY source_id").fetchall():
            p=Path(source['original_path'])
            if not p.exists():continue
            try:
                tabs=tables(p.read_bytes(),p.name)
                for _,rs in tabs:
                    hi=next((i for i,h in enumerate(rs[:30])if 'section'in header_map(h)and'name'in header_map(h)),None)
                    if hi is None:continue
                    h=rs[hi];mp=header_map(h)
                    for row in rs[hi+1:]:
                        raw=self.regis_record(h,mp,row)if source['kind']=='regis'else self.simple_record(h,mp,row,canvas=True)
                        sec=section(raw.get('section'))
                        r=ruid(raw.get('ruid'))
                        if not r:
                            n=netid(raw.get('netid'))
                            candidates=d.execute('SELECT DISTINCT ruid FROM enrollments WHERE netid=? AND semester=?',(n,source['semester'])).fetchall()if n else[]
                            r=candidates[0][0]if len(candidates)==1 else None
                        if r and sec:d.execute("UPDATE app_roster_state SET section=? WHERE ruid=? AND semester=? AND (section='' OR ?='regis')",(sec,r,source['semester'],source['kind']))
            except Exception:continue
    def default_policy(self,t,old=None):
        if not self.legacy_policy:
            p=dict(old or {});p.setdefault('weights',{});p.setdefault('cutoffs',{});p.setdefault('bump_enabled',False);p.setdefault('round_average',False);p.setdefault('round_final',False);p.setdefault('minimum_bump_average',None);return p
        p=analytics.default_policy(t)
        if p:
            p=dict(p);p['cutoffs']=p.pop('thresholds');p['minimum_bump_average']=p.pop('bump_minimum_rounded_average');p['round_average']=p.pop('round_course_average');p['round_final']=p.pop('round_final_score');return p
        p=dict(old or {});p.setdefault('weights',{});p['round_average']=p.get('round_course_average',False);p['round_final']=True;p['bump_enabled']=analytics.semester_order(t)>=analytics.semester_order('Fa24');p['minimum_bump_average']=None
        if analytics.semester_order(t)>=analytics.semester_order('Fa23'):p['cutoffs']=dict(analytics.DEFAULT_THRESHOLDS)
        return p
    def ensure_term(self,d,t):
        if not d.execute('SELECT1 FROM semesters WHERE semester=?'.replace('SELECT1','SELECT 1'),(t,)).fetchone():
            p=self.default_policy(t)
            if self.legacy_policy and not p.get('weights'):raise ValueError('Create the grading policy for this historical semester first.')
            d.execute('INSERT INTO semesters VALUES(?,?,?,?,?)',(t,2000+int(t[2:]),{'Sp':'Spring','Fa':'Fall','Su':'Summer'}[t[:2]],'current',json.dumps(p)))
            d.execute('INSERT INTO app_policies VALUES(?,?)',(t,json.dumps(p)))
    def policy(self,t):
        t=semester(t)
        with self.connect()as d:
            r=d.execute('SELECT policy_json FROM app_policies WHERE semester=?',(t,)).fetchone()
            return {'semester':t,'policy':json.loads(r[0])if r else self.default_policy(t)}
    def history(self,d=None):
        if d is None:
            with self.connect()as conn:return self.history(conn)
        rr=[dict(r)for r in d.execute('SELECT * FROM app_imports ORDER BY created_at DESC')];latest=next((r['import_id']for r in rr if r['status']=='committed'),None)
        for r in rr:r['counts']=json.loads(r['counts']);r['sections']=json.loads(r['sections']or'[]');r['can_undo']=r['status']=='committed'and r['import_id']==latest
        return rr
    def bootstrap(self):
        with self.lock,self.connect()as d:
            lookupfile=Path(__file__).with_name('lookups.json');lookups=json.loads(lookupfile.read_text(encoding='utf-8'))if lookupfile.exists()else{}
            filters,filters_by_semester=build_filter_options(d,lookups)
            teacher_filters,teacher_terms=teacher_links.filter_options(d)
            filters.update(teacher_filters)
            for term,options in teacher_terms.items():filters_by_semester.setdefault(term,{}).update(options)
            semesters=[{'semester':r['semester'],'label':term_label(r['semester']),'status':r['status']}for r in d.execute('SELECT * FROM semesters')];semesters.sort(key=lambda r:analytics.semester_order(r['semester']),reverse=True)
            today=datetime.date.today();calendar_term=('Fa'if today.month>=8 else'Sp')+str(today.year)[-2:];eligible=[r['semester']for r in semesters if analytics.semester_order(r['semester'])<=analytics.semester_order(calendar_term)];current=eligible[0]if eligible else(semesters[0]['semester']if semesters else None)
            for s in semesters:s['status']='current'if s['semester']==current else'historical'if analytics.semester_order(s['semester'])<analytics.semester_order(calendar_term)else'future'
            assessments=[{**dict(r),'label':r['label']or label(r['assessment_key'])}for r in d.execute('SELECT a.assessment_id,a.semester,a.assessment_key,l.label FROM assessment_definitions a LEFT JOIN app_assessment_labels l USING(assessment_id) ORDER BY a.semester,a.assessment_key')]
            return {'course':{'code':self.course_code,'name':self.course_name,'legacy_policy':self.legacy_policy},'semesters':semesters,'filters':filters,'filters_by_semester':filters_by_semester,'assessments':assessments,'policies':[{'semester':r[0],'policy':json.loads(r[1])}for r in d.execute('SELECT * FROM app_policies')],'instructors':[dict(r)for r in d.execute('SELECT * FROM app_instructors ORDER BY semester,section')],'teaching_assignments':teacher_links.assignment_rows(d),'imports':self.history(d),'summary':{'records':d.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0],'students':d.execute('SELECT COUNT(*) FROM students').fetchone()[0]},'lookup_sources':lookups.get('sources',[])}
    def filter_sql(self,params,active=False):
        clauses=[];args=[]
        if active:clauses.append('COALESCE(rs.active,1)=1')
        for key in ['semester','section']:
            vv=values(params,key)
            if vv:
                if key=='semester':vv=[semester(v)for v in vv]
                if key=='section':vv=[section(v)for v in vv]
                field='rs.section'if key=='section'else'e."'+key+'"';clauses.append(field+' IN ('+','.join('?'for _ in vv)+')');args+=vv
        filter_clause,filter_args=record_filters.group_clause(params)
        if filter_clause:clauses.append(filter_clause);args.extend(filter_args)
        q=clean(one(params,'q',''))
        if q:
            q=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_');clauses.append("(e.name LIKE ? ESCAPE '\\' OR e.netid LIKE ? ESCAPE '\\' OR e.ruid LIKE ? ESCAPE '\\')");args+=['%'+q+'%']*3
        return ('WHERE '+' AND '.join(clauses))if clauses else'',args
    def students(self,params):
        where,args=self.filter_sql(params);page=max(1,int(one(params,'page',1)));size=40
        with self.lock,self.connect()as d:
            matches=d.execute('SELECT DISTINCT e.ruid FROM enrollments e LEFT JOIN app_roster_state rs USING(ruid,semester) '+where,args).fetchall();matched={r[0]for r in matches}
            if not matched:return {'rows':[],'total':0,'page':page,'page_size':size}
            # Fetch whole histories for matched students; attempts are never
            # limited to the semester/filter used to locate the student.
            groups=defaultdict(list)
            for r in d.execute('SELECT e.*,COALESCE(rs.active,1) AS active FROM enrollments e LEFT JOIN app_roster_state rs USING(ruid,semester)'):
                if r['ruid']in matched:groups[r['ruid']].append(dict(r))
            result=[]
            for r,rr in groups.items():
                rr.sort(key=lambda x:analytics.semester_order(x['semester']),reverse=True);last=rr[0]
                result.append({'ruid':r,'name':last['name'],'netid':last['netid'],'attempts':sum(x['official_grade']is not None and x['active']for x in rr),'semesters':[x['semester']for x in rr],'latest_grade':last['official_grade'],'latest_semester':last['semester']})
            result.sort(key=lambda r:(r['name'].casefold(),r['ruid']))
            return {'rows':result[(page-1)*size:page*size],'total':len(result),'page':page,'page_size':size}
    def student(self,r):
        if not ruid(r):raise ValueError('Student not found.')
        with self.lock,self.connect()as d:
            rr=[dict(x)for x in d.execute('SELECT e.*,COALESCE(rs.active,1) AS active,rs.section FROM enrollments e LEFT JOIN app_roster_state rs USING(ruid,semester) WHERE e.ruid=?',(r,))]
            if not rr:raise ValueError('Student not found.')
            rr.sort(key=lambda x:analytics.semester_order(x['semester']),reverse=True)
            for rec in rr:
                rec.update(teacher_links.section_names(d,rec['semester'],rec['section']))
                rec['scores']=[{**dict(x),'label':x['label']or label(x['assessment_key'])}for x in d.execute('SELECT s.assessment_id,d.assessment_key,s.percent,s.status,l.label FROM assessment_scores s JOIN assessment_definitions d USING(assessment_id) LEFT JOIN app_assessment_labels l USING(assessment_id) WHERE s.ruid=? AND s.semester=? ORDER BY d.assessment_key',(r,rec['semester']))]
            attempts=[x['semester']for x in rr if x['official_grade']is not None and x['active']]
            return {'ruid':r,'name':rr[0]['name'],'netid':rr[0]['netid'],'attempts':len(attempts),'attempt_semesters':attempts,'records':rr}
    def regis_record(self,h,mp,row):
        split='name'in mp and len(row)>len(h) and ','not in clean(row[mp['name']])
        def get(k):
            if k not in mp:return ''
            i=mp[k]
            if split:
                if k=='name':return ', '.join(clean(v)for v in row[i:i+2])
                if i>mp['name']:
                    i=len(row)-(len(h)-i)if i>=8 else i+1
            return row[i]if i<len(row)else''
        return {k:get(k)for k in mp}
    def simple_record(self,h,mp,row,canvas=False):
        rr={k:row[i]if len(row)>i else''for k,i in mp.items()}
        if canvas:
            rr['ruid']=next((ruid(row[i])for i,x in enumerate(h)if norm(x)in ['ruid','rutgersid','studentid','sisuserid']and len(row)>i and ruid(row[i])),None)
            rr['netid']=next((netid(row[i])for i,x in enumerate(h)if norm(x)in ['netid','sisloginid','sisuserid']and len(row)>i and netid(row[i])),None)
            if not rr.get('name'):
                names={norm(x):i for i,x in enumerate(h)};rr['name']=', '.join(clean(row[names[k]])for k in ['lastname','firstname']if k in names and len(row)>names[k])
        return rr
    def identify(self,d,rec,t):
        r=ruid(rec.get('ruid'));n=netid(rec.get('netid'))
        if r:
            if n:
                ids={v[0]for v in d.execute('SELECT DISTINCT ruid FROM enrollments WHERE netid=? COLLATE NOCASE',(n,))}
                if ids and r not in ids:return None,'RUID and NetID refer to different students.'
            return r,None
        if not n:return None,'No usable RUID or NetID.'
        ids={x[0]for x in d.execute('SELECT ruid FROM enrollments WHERE netid=? AND semester=? COLLATE NOCASE',(n,t))}
        if not ids:ids={x[0]for x in d.execute('SELECT DISTINCT ruid FROM identity_aliases WHERE netid=? COLLATE NOCASE',(n,))}
        if not ids:ids={x[0]for x in d.execute('SELECT DISTINCT ruid FROM enrollments WHERE netid=? COLLATE NOCASE',(n,))}
        return (next(iter(ids)),None)if len(ids)==1 else(None,'NetID is not linked to exactly one student. Import the REGIS roster first.')
    def infer_column(self,t,h,maximum):
        s=re.sub(r'\s*\(\d+\)$','',h).strip();low=s.lower();key=None;role='version';include=True
        if any(x in low for x in ['current score','final score','current grade','final grade','current points','final points','unposted']):
            # Canvas also exports already-calculated category percentages. They
            # are useful when the instructor supplies no separate Average column.
            if low.endswith(' final score')and'unposted'not in low:
                key=next((k for words,k in [(['homework'],'homework'),(['quiz','quizz'],'quiz'),(['wrapper','survey'],'wrappers'),(['recitation'],'recitation')]if any(w in low for w in words)),None)
                if key:return {'header':h,'max_points':100,'assessment_key':key,'assessment_name':label(key),'role':'aggregate','include':False,'category_summary':True}
            return None
        if any(x in low for x in ['practice','onboarding','proctortrack','lockdown','scan-and-upload']):key='';role='ignore';include=False
        elif 'homework'in low or norm(low)in ['hw','hwaverage']:key='homework';role='aggregate'
        elif 'recitation'in low:key='recitation';role='aggregate'
        elif 'quiz'in low or 'quizz'in low:
            m=re.search(r'quiz\s*#?\s*(\d+)',low);key='quiz'+m[1]if m else'quiz';role='version'if m else'aggregate'
        elif 'wrapper'in low or 'survey'in low:
            if any(x in low for x in ['average','avg','combined'])or norm(low)in ['wrappers','examwrappersandsurveys']:key='wrappers';role='aggregate'
            else:key=re.sub(r'[^a-z0-9]+','_',low).strip('_')[:64];role='version'
        elif 'precalc'in low:key='precalculus';role='version'
        elif 'ru ready'in low or 'rurt'in low:key='readiness';role='consolidated'
        elif 'final exam'in low or norm(low)=='final':key='final';role='replacement'if'replacement'in low else'adjusted'if'adjusted'in low else'consolidated'
        elif re.search(r'(?:midterm|mditerm|exam)\s*(?:exam\s*)?#?\s*\d',low):
            m=re.search(r'(?:midterm|mditerm|exam)\s*(?:exam\s*)?#?\s*(\d+)',low);key='midterm'+m[1];role='consolidated'if'score only'in low or (t=='Sp20'and low.startswith('exam'))else'version'
        elif t=='Fa21'and'midterm exam (online)'in low:key='midterm4'
        elif 'worksheet'in low:
            m=re.search(r'worksheet\s*#?\s*(\d+)',low);key='worksheet'+m[1]if m else'worksheet'
        elif maximum is not None or re.search(r'\(\d+\)$',h):key=re.sub(r'[^a-z0-9]+','_',low).strip('_')[:64]or'assignment'
        else:return None
        if t=='Fa20'and any(x in low for x in ['timed responses','uploaded work',' copy']):role='component';include=False
        if t=='Sp20'and key=='midterm2'and any(x in low for x in ['original','makeup']):role='component';include=False
        if t=='Fa19'and key=='final'and'total'not in low:role='component';include=False
        if t=='Fa20'and key=='final'and'total'not in low:role='component';include=False
        if t in ['Fa20','Sp21']and key=='readiness'and'pass/fail'not in low:role='component';include=False
        if t=='Fa24'and key=='final'and'adjusted'not in low:role='component';include=False
        return {'header':h,'max_points':maximum if maximum is not None else 100,'assessment_key':key,'assessment_name':label(key)if key else s,'role':role,'include':include}
    def preview(self,payload):
        with self.lock,self.connect()as d:
            self.previews={k:v for k,v in self.previews.items()if time.time()-v['created']<1800}
            if payload.get('preview_id'):
                old=self.previews.get(payload['preview_id'])
                if not old:raise ValueError('This preview expired. Choose the file again.')
                raw=old['raw'];filename=old['filename'];kind=old['kind'];options={**old['options'],**payload}
            else:
                if len(self.previews)>=20:raise ValueError('Too many import previews. Reload the app to continue.')
                try:raw=base64.b64decode(payload.get('data',''),validate=True)
                except Exception:raise ValueError('The uploaded file could not be read.')
                if not raw or len(raw)>25_000_000:raise ValueError('Choose a file smaller than25MB.')
                filename=Path(clean(payload.get('filename','upload.csv'))).name;kind=payload.get('kind');options=dict(payload)
            if kind not in ['regis','canvas','proposals','instructors']:raise ValueError('Choose an import type.')
            tabs=tables(raw,filename);chosen=None
            for sheet,rs in tabs:
                for i,h in enumerate(rs[:30]):
                    mp=header_map(h)
                    suitable=('section'in mp and any(k in mp for k in ('instructor','lecturer','recitation')))if kind=='instructors'else('grade'in mp and('ruid'in mp or'netid'in mp))if kind in ['regis','proposals']else('netid'in mp or'ruid'in mp)
                    if suitable:chosen=(sheet,rs,i,h,mp);break
                if chosen:break
            if not chosen:raise ValueError('No suitable roster headers found. Use REGIS/Canvas CSV or XLSX, or the templates described in Help.')
            sheet,rs,hi,h,mp=chosen;detected=set()
            preamble=' '.join(' '.join(clean(v)for v in r)for r in rs[:hi]);coursecodes=set(re.findall(r'(?i)\bcourse\s*(?:number|#)?\s*[:=]?\s*(\d{3})\b',preamble))
            if kind=='canvas'and'section'in mp:
                for row in rs[hi+1:]:
                    if len(row)>mp['section']:coursecodes.update(re.findall(r'640\s*[:_-]\s*(\d{3})\s*[:_-]',clean(row[mp['section']])))
            if coursecodes and coursecodes!={self.course_code}:raise ValueError('This file identifies a different course. Choose an export for '+self.course_name+'.')
            for s in [' '.join(' '.join(clean(v)for v in r)for r in rs[:hi]),filename]:
                try:detected.add(semester(s))
                except ValueError:pass
            for row in rs[hi+1:]:
                if'metadata'in mp:continue
                for key in ['semester','section']:
                    if key in mp and len(row)>mp[key]:
                        try:detected.add(semester(row[mp[key]]))
                        except ValueError:pass
            if len(detected)>1:raise ValueError('This file identifies multiple semesters. Export one semester at a time.')
            detected_term=next(iter(detected),None);t=semester(options['semester'])if options.get('semester')else detected_term
            if t and detected_term and t!=detected_term:raise ValueError('The selected semester does not match the semester inside the file.')
            t=t or'';counts={k:0 for k in ['new','updated','removed','unchanged','unmatched','invalid','rows']};issues=[];examples=[];staged=[];seen=set();sections=set();columns=[]
            scope=options.get('scope','semester')
            if scope not in ['semester','sections']:raise ValueError('Choose the whole semester or selected sections.')
            requested={section(v)for v in options.get('sections',[])if section(v)}
            if kind=='canvas':
                pp=next((r for r in rs[hi+1:hi+5]if r and clean(r[0]).lower()=='points possible'),None)
                existing={row[0]:json.loads(row[1])for row in d.execute('SELECT header,mapping FROM app_column_maps WHERE semester=?',(t,))}
                supplied={int(x['column']):x for x in options.get('mappings',[])if'column'in x}
                identifiernames={'id','student','name','studentname','firstname','lastname','sisuserid','sisloginid','ruid','rutgersid','studentid','netid','section','sec','email','notes','unit','class','curric'}
                for i,v in enumerate(h):
                    if norm(v)in identifiernames:continue
                    maximum=number(pp[i])if pp and len(pp)>i else None
                    info=self.infer_column(t,v,maximum)
                    if info is None:continue
                    info={**info,**existing.get(v,{}),**supplied.get(i,{})};info['column']=i;info['header']=v
                    info['max_points']=number(info.get('max_points'));info['include']=bool(info.get('include'))
                    key=clean(info.get('assessment_key',''))
                    if info['include']and(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',key)or not info['max_points']or info['max_points']<=0):raise ValueError('Every selected score column needs an assessment key and positive maximum points.')
                    columns.append(info)
                for c in columns:
                    if c.get('category_summary')and c['column']not in supplied and c['header']not in existing and not any(x['include']and x['assessment_key']==c['assessment_key']for x in columns):c['include']=True
                aggregate_counts=Counter(x['assessment_key']for x in columns if x['include']and x['role']=='aggregate')
                if any(n>1 for n in aggregate_counts.values()):raise ValueError('Choose only one processed average column for each category.')
                if not any(x['include']for x in columns):issues.append({'row':hi+1,'message':'No assessment columns selected. Check the mapping below.'})
            for rowno,row in enumerate(rs[hi+1:],hi+2):
                if not any(clean(x)for x in row):continue
                if row and clean(row[0]).lower()in ['points possible','student, test','test student']:continue
                rec=self.regis_record(h,mp,row)if kind=='regis'else self.simple_record(h,mp,row,canvas=kind=='canvas')
                if kind=='canvas'and not any(rec.get(k)for k in ['ruid','netid']):
                    # Posting/points rows and Canvas test accounts have no SIS key.
                    continue
                try:
                    if kind=='instructors':
                        sec=section(rec.get('section'));name=clean(rec.get('lecturer')or rec.get('recitation')or rec.get('instructor'))
                        if not sec or not name:raise ValueError('Section and at least one instructor name are required.')
                        key=sec;rec={**rec,'section':sec,'instructor':name,'email':clean(rec.get('email'))}
                        before=d.execute('SELECT * FROM app_instructors WHERE semester=? AND section=?',(t,sec)).fetchone()
                    else:
                        r=ruid(rec.get('ruid'))if kind=='regis'else None;why=None
                        if kind!='regis'and t:r,why=self.identify(d,rec,t)
                        if kind=='regis'and not r:
                            # Ignore footer rows; invalid student-like rows block destructive replacement.
                            if not clean(rec.get('name')):continue
                            raise ValueError('A nine-digit RUID is required.')
                        if why:
                            counts['unmatched']+=1;issues.append({'row':rowno,'message':why});rec['ruid']=None
                        else:rec['ruid']=r
                        rec['netid']=netid(rec.get('netid'));rec['name']=clean(rec.get('name'));rec['section']=section(rec.get('section'));sec=rec['section'];key=r or('unmatched',rowno)
                        if kind=='regis':
                            if not rec['name']:raise ValueError('Student name is required.')
                            if not sec:raise ValueError('A section is required for roster replacement.')
                            rec['raw_grade']=clean(rec.get('grade'));rec['grade']=grade(rec.get('grade'));rec['unit']=code(rec.get('unit'),2);rec['class']=code(rec.get('class'),2);rec['curric']=code(rec.get('curric'),3)
                            if rec['netid']:
                                _,problem=self.identify(d,rec,t)
                                if problem:raise ValueError(problem)
                        if kind=='proposals':
                            rec['grade']=grade(rec.get('grade'))
                            if not rec['grade']:raise ValueError('Proposed letter grade is required.')
                        before=d.execute('SELECT * FROM enrollments WHERE ruid=? AND semester=?',(r,t)).fetchone()if r and t else None
                        if kind in ['canvas','proposals']and r and not before:
                            counts['unmatched']+=1;rec['ruid']=None;issues.append({'row':rowno,'message':'Student is not on this semester roster. Import REGIS first.'});before=None
                        if kind=='canvas':
                            rec['scores']=[]
                            for info in columns:
                                if not info['include']:continue
                                rawvalue=clean(row[info['column']])if len(row)>info['column']else'';v=number(rawvalue)
                                status='numeric'if v is not None else'missing'if not rawvalue else'excused'if rawvalue.lower()in ['ex','excused']else'invalid'
                                if status=='invalid':raise ValueError('An included score is not a number, blank, or EX.')
                                if v is not None and v<0:raise ValueError('Negative scores need correction before import.')
                                rec['scores'].append({'column':info['column'],'raw':rawvalue,'points':v,'percent':100*v/info['max_points']if v is not None else None,'status':status})
                            names={str(x):i for i,x in enumerate(h)};rec['canvas_final']=number(row[names['Final Score']])if 'Final Score'in names and len(row)>names['Final Score']else None
                    if key in seen:raise ValueError('Duplicate student or section in this file. Resolve duplicates before applying.')
                    seen.add(key)
                    if sec:sections.add(sec)
                    if kind=='regis'and scope=='sections'and requested and sec not in requested:continue
                    rec['source_row']=rowno;staged.append(rec);counts['rows']+=1
                    action='updated'if before else'new'
                    if before:
                        if kind=='regis':
                            current=d.execute('SELECT section,active FROM app_roster_state WHERE ruid=? AND semester=?',(rec['ruid'],t)).fetchone()
                            samefields=all(before['official_grade'if k=='grade'else k]==rec.get(k)for k in ['name','netid','unit','class','curric','grade'])
                            if samefields and current and current['active']and current['section']==sec:action='unchanged'
                        elif kind=='instructors':
                            if not any(k in rec for k in ('lecturer','recitation'))and all(clean(before[k])==clean(rec[k])for k in ['section','instructor','email']):action='unchanged'
                        elif kind=='proposals':
                            prev=d.execute('SELECT proposed_grade FROM app_proposals WHERE ruid=? AND semester=?',(rec.get('ruid'),t)).fetchone()
                            action='new'if not prev else'unchanged'if prev[0]==rec['grade']else'updated'
                        elif kind=='canvas'and rec.get('ruid'):
                            cc={x['column']:x for x in columns};equal=True
                            for s in rec['scores']:
                                c=cc[s['column']];aid='M'+self.course_code+'-'+t+'-'+c['assessment_key'];ck='aggregate:'+aid if c['role']=='aggregate'else column_key(c['header']);prev=d.execute('SELECT percent,status FROM app_score_cells WHERE ruid=? AND semester=? AND assessment_id=? AND column_key=?',(rec['ruid'],t,aid,ck)).fetchone()
                                if not prev or prev['percent']!=s['percent']or prev['status']!=s['status']:equal=False;break
                            if equal:action='unchanged'
                    if kind=='canvas'and rec.get('ruid')is None:action='unmatched'
                    elif kind=='proposals'and rec.get('ruid')is None:action='unmatched'
                    else:counts[action]+=1
                    if len(examples)<5:examples.append({'name':rec.get('name')or rec.get('instructor'),'netid':rec.get('netid'),'action':action})
                except ValueError as e:counts['invalid']+=1;issues.append({'row':rowno,'message':str(e)})
            if kind=='regis'and t:
                included={r['ruid']for r in staged};scope_sections=requested or sections
                for r in d.execute('SELECT * FROM app_roster_state WHERE semester=? AND active=1',(t,)):
                    if (scope=='semester'or r['section']in scope_sections)and r['ruid']not in included:counts['removed']+=1
            can=bool(t and staged and counts['invalid']==0)
            if kind=='canvas'and not any(x['include']for x in columns):can=False
            if kind in ['canvas','proposals']and not any(r.get('ruid')for r in staged):can=False
            pid=secrets.token_urlsafe(22);record={'raw':raw,'filename':filename,'kind':kind,'options':options,'created':time.time(),'revision':self.revision(d),'semester':t,'staged':staged,'columns':columns,'scope':scope,'sections':sorted(requested or sections),'counts':counts,'can_commit':can}
            self.previews[pid]=record
            return {'preview_id':pid,'kind':kind,'semester':t,'semester_detected':detected_term,'needs_semester':not bool(t),'scope':scope,'sections_detected':sorted(sections),'counts':counts,'issues':issues[:100],'columns':columns,'can_commit':can,'examples':examples}
    def add_source(self,d,p,kind,t):
        cur=d.execute('INSERT INTO sources(kind,semester,file_name,original_path,sha256,source_date,imported_at) VALUES(?,?,?,?,?,?,?)',(kind,t,p.name,str(p),hashlib.sha256(p.read_bytes()).hexdigest(),NOW(),NOW()));return cur.lastrowid
    def assessment(self,d,t,key,name):
        aid='M'+self.course_code+'-'+t+'-'+key;pol=json.loads(d.execute('SELECT policy_json FROM app_policies WHERE semester=?',(t,)).fetchone()[0]);typ='midterm'if key.startswith('midterm')else key if key in ['final','precalculus','readiness','homework','quiz','recitation','wrappers']else'assignment'
        d.execute('INSERT OR IGNORE INTO assessment_definitions VALUES(?,?,?,?,?,?)',(aid,t,key,typ,float(pol.get('weights',{}).get(key,0)),json.dumps(pol)))
        d.execute('INSERT OR REPLACE INTO app_assessment_labels VALUES(?,?)',(aid,clean(name)or label(key)));return aid
    def refresh_average(self,d,r,t):
        rec=d.execute('SELECT official_grade FROM enrollments WHERE ruid=? AND semester=?',(r,t)).fetchone()
        if not rec:return
        pol=json.loads(d.execute('SELECT policy_json FROM app_policies WHERE semester=?',(t,)).fetchone()[0]);scores={x[0]:x[1]for x in d.execute('SELECT a.assessment_key,s.percent FROM assessment_scores s JOIN assessment_definitions a USING(assessment_id) WHERE s.ruid=? AND s.semester=?',(r,t))};result=analytics.calculate_grade(scores,pol,semester=t)
        avg=result.get('weighted_average',result.get('course_average'))
        if rec[0]=='W'or t=='Fa19':avg=None;status='withdrawn'if rec[0]=='W'else'intentionally_blank'
        else:status='current_calculated'if avg is not None else'incomplete_current'
        d.execute('UPDATE enrollments SET course_average=?,calculated_course_average=?,average_status=? WHERE ruid=? AND semester=?',(avg,avg,status,r,t))
    def commit(self,pid):
        with self.lock,self.connect()as d:
            p=self.previews.get(pid)
            if not p or time.time()-p['created']>1800:raise ValueError('Preview expired. Preview the file again.')
            if not p['can_commit']:raise ValueError('Fix the preview issues before applying this file.')
            if p['revision']!=self.revision(d):raise ValueError('The database changed after this preview. Preview the file again.')
            uid=uuid.uuid4().hex;t=p['semester'];kind=p['kind'];backup=self.backup(d,'Import-'+uid+'.sqlite');dest=self.root/'Imports'/(uid+'-'+re.sub(r'[^a-zA-Z0-9._-]','_',p['filename']));dest.write_bytes(p['raw'])
            with d:
                self.ensure_term(d,t);sid=self.add_source(d,dest,kind,t);affected=set()
                if kind=='regis':
                    included={r['ruid']for r in p['staged']};secs=set(p['sections'])
                    for old in d.execute('SELECT * FROM app_roster_state WHERE semester=? AND active=1',(t,)).fetchall():
                        if(p['scope']=='semester'or old['section']in secs)and old['ruid']not in included:
                            d.execute('UPDATE app_roster_state SET active=0 WHERE ruid=? AND semester=?',(old['ruid'],t));d.execute('INSERT INTO app_roster_events VALUES(?,?,?,?,?)',(uid,old['ruid'],t,'removed',old['section']))
                    for r in p['staged']:
                        teacher_links.save_section_observation(d,r,t,sid,'regis')
                        d.execute('INSERT OR IGNORE INTO students VALUES(?)',(r['ruid'],));d.execute("INSERT INTO enrollments(ruid,semester,name,netid,unit,class,curric,official_grade,roster_status,grade_source_id) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ruid,semester) DO UPDATE SET name=excluded.name,netid=excluded.netid,unit=excluded.unit,class=excluded.class,curric=excluded.curric,official_grade=excluded.official_grade,roster_status=excluded.roster_status,grade_source_id=excluded.grade_source_id,course_average=CASE WHEN excluded.official_grade='W' THEN NULL ELSE enrollments.course_average END,saved_course_average=CASE WHEN excluded.official_grade='W' THEN NULL ELSE enrollments.saved_course_average END,calculated_course_average=CASE WHEN excluded.official_grade='W' THEN NULL ELSE enrollments.calculated_course_average END",(r['ruid'],t,r['name'],r['netid'],r['unit'],r['class'],r['curric'],r['grade'],'official_roster',sid))
                        d.execute('INSERT OR REPLACE INTO app_roster_state VALUES(?,?,?,1)',(r['ruid'],t,r['section']));d.execute('INSERT INTO roster_observations(ruid,semester,source_id,source_row,name,netid,unit,class,curric,raw_grade,normalized_grade) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(r['ruid'],t,sid,r['source_row'],r['name'],r['netid'],r['unit'],r['class'],r['curric'],r.get('raw_grade'),r['grade']))
                        if r['netid']:d.execute('INSERT OR IGNORE INTO identity_aliases VALUES(?,?,?,?)',(r['netid'],r['ruid'],t,sid))
                        for f in ['name','netid','unit','class','curric','official_grade']:d.execute('INSERT OR REPLACE INTO field_provenance VALUES(?,?,?,?,?)',(r['ruid'],t,f,sid,r['source_row']))
                        if r['grade']=='W':d.execute("UPDATE enrollments SET course_average=NULL,saved_course_average=NULL,calculated_course_average=NULL,average_status='withdrawn' WHERE ruid=? AND semester=?",(r['ruid'],t))
                        d.execute('INSERT INTO app_roster_events VALUES(?,?,?,?,?)',(uid,r['ruid'],t,'included',r['section']))
                elif kind=='canvas':
                    cols={}
                    for c in p['columns']:
                        d.execute('INSERT OR REPLACE INTO app_column_maps VALUES(?,?,?)',(t,c['header'],json.dumps(c)))
                        if not c['include']:continue
                        aid=self.assessment(d,t,c['assessment_key'],c.get('assessment_name'));cur=d.execute('INSERT INTO input_columns(source_id,column_number,excel_column,exact_header,points_possible,assessment_id,role) VALUES(?,?,?,?,?,?,?)',(sid,c['column']+1,self.excel_col(c['column']+1),c['header'],c['max_points'],aid,c['role']));cols[c['column']]={**c,'input_id':cur.lastrowid,'aid':aid}
                    for r in p['staged']:
                        teacher_links.save_section_observation(d,r,t,sid,'canvas')
                        cur=d.execute('INSERT INTO canvas_observations(source_id,source_row,semester,ruid,name,netid,match_status,final_score) VALUES(?,?,?,?,?,?,?,?)',(sid,r['source_row'],t,r['ruid'],r['name'],r['netid'],'matched'if r['ruid']else'unmatched_identifier',r.get('canvas_final')));crow=cur.lastrowid;groups=defaultdict(list)
                        for s in r['scores']:
                            c=cols[s['column']];cur=d.execute('INSERT INTO raw_scores(canvas_row_id,input_id,raw_value,status,points,percent) VALUES(?,?,?,?,?,?)',(crow,c['input_id'],s['raw']or None,s['status'],s['points'],s['percent']));groups[c['aid']].append({**s,'raw_id':cur.lastrowid,'role':c['role']})
                            if r['ruid']:
                                ck='aggregate:'+c['aid']if c['role']=='aggregate'else column_key(c['header'])
                                d.execute('INSERT OR REPLACE INTO app_score_cells VALUES(?,?,?,?,?,?,?,?,?,?)',(r['ruid'],t,c['aid'],ck,s['percent'],s['status'],cur.lastrowid,c['role'],c['header'],sid))
                        if not r['ruid']:continue
                        for aid,items in groups.items():
                            items=[{**dict(x),'raw_id':x['raw_id']}for x in d.execute('SELECT * FROM app_score_cells WHERE ruid=? AND semester=? AND assessment_id=?',(r['ruid'],t,aid))]
                            if t=='Fa24'and aid.endswith('-final')and any(x['role']=='adjusted'for x in items):items=[x for x in items if x['role']=='adjusted']
                            nums=[s for s in items if s['percent']is not None];best=max(nums,key=lambda x:x['percent'])if nums else None;v=best['percent']if best else None;status='selected'if best else'excused'if any(s['status']=='excused'for s in items)else'missing'
                            d.execute('INSERT OR REPLACE INTO assessment_scores VALUES(?,?,?,?,?,?,?,?,?)',(r['ruid'],t,aid,v,status,'maximum_of_latest_version_cells_omitted_columns_retained',json.dumps([best['raw_id']]if best else[]),best['source_id']if best else sid,0))
                        affected.add(r['ruid'])
                        if r.get('canvas_final')is not None:d.execute('INSERT INTO average_observations(ruid,semester,source_id,source_row,kind,value) VALUES(?,?,?,?,?,?)',(r['ruid'],t,sid,r['source_row'],'canvas_final',r['canvas_final']))
                elif kind=='proposals':
                    for r in p['staged']:
                        if r['ruid']:d.execute('INSERT OR REPLACE INTO app_proposals VALUES(?,?,?,?)',(r['ruid'],t,r['grade'],uid))
                elif kind=='instructors':
                    for r in p['staged']:teacher_links.apply_instructor_row(d,t,r)
                for r in affected:self.refresh_average(d,r,t)
                d.execute('INSERT INTO app_imports VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,kind,p['filename'],t,NOW(),json.dumps(p['counts']),'committed',str(backup),str(dest),p['scope'],json.dumps(p['sections'])))
                self.touch(d)
            self.previews.clear();return {'import_id':uid,'counts':p['counts'],'message':'Import applied. The previous database is backed up and this import can be undone.'}
    def excel_col(self,n):
        s=''
        while n:n,r=divmod(n-1,26);s=chr(65+r)+s
        return s
    def undo(self,uid):
        with self.lock,self.connect()as d:
            rr=[dict(r)for r in d.execute('SELECT * FROM app_imports ORDER BY created_at DESC')];latest=next((r for r in rr if r['status']=='committed'),None)
            if not latest or latest['import_id']!=uid:raise ValueError('Only the latest applied change can be undone. Undo newer changes first.')
            backup=Path(latest['backup_path']);allowed=self.root/'Backups'
            # App/course-folder moves do not rewrite recorded import history.
            # The snapshot reader still enforces this database's backup folder
            # and verifies the compressed snapshot hash before restoring it.
            if backup.parent.resolve()!=allowed.resolve():backup=allowed/backup.name
            with snapshot_database(backup,allowed)as database:
                self.backup(d,'Before-Undo-'+uuid.uuid4().hex+'.sqlite')
                source=sqlite3.connect('file:'+database.as_posix()+'?mode=ro',uri=True)
                try:source.backup(d)
                finally:source.close()
            teacher_links.ensure_teaching(d,Path(__file__).with_name('schedule-mappings.json') if self.legacy_policy else self.root/'course-schedule-mappings.json')
            d.executemany('INSERT OR IGNORE INTO app_settings VALUES(?,?)',[('course_code',self.course_code),('course_name',self.course_name),('policy_mode','legacy135' if self.legacy_policy else 'custom')])
            with d:
                for rec in rr:
                    if rec['status']=='undone'or rec['import_id']==uid:
                        rec['status']='undone';keys=list(rec);d.execute('INSERT OR REPLACE INTO app_imports('+','.join(keys)+') VALUES('+','.join('?'for _ in keys)+')',[rec[k]for k in keys])
                self.touch(d)
            self.previews.clear();return {'message':'The import was undone. Previous records and scores have been restored.'}
    def save_policy(self,payload):
        t=semester(payload.get('semester'));p=dict(payload.get('policy')or{});weights=p.get('weights')
        for canonical,alias in [('cutoffs','thresholds'),('minimum_bump_average','bump_minimum_rounded_average'),('round_average','round_course_average'),('round_final','round_final_score')]:
            if canonical not in p and alias in p:p[canonical]=p[alias]
            p.pop(alias,None)
        if not isinstance(weights,dict)or not weights:raise ValueError('Provide the component weights.')
        if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',k)or number(v)is None or number(v)<0 for k,v in weights.items()):raise ValueError('Weights must be nonnegative numbers with valid component names.')
        weights={k:number(v)for k,v in weights.items()};drop=int(p.get('drop_lowest_midterm',0)or 0);total=sum(weights.values())
        if drop:
            mids=[v for k,v in weights.items()if k.startswith('midterm')]
            if not mids or len(set(mids))!=1 or drop>=len(mids):raise ValueError('Dropped midterms require equal exam weights and at least one retained exam.')
            total-=mids[0]*drop
        if abs(total-100)>.00001:raise ValueError('The retained component weights must total100%.')
        p['weights']=weights
        cut=p.get('cutoffs',p.get('thresholds'))
        if cut is not None:
            letters=['D','C','C+','B','B+','A'];vv=[number(cut.get(k))for k in letters]
            if any(v is None or not 0<=v<=100 for v in vv)or any(a>=b for a,b in zip(vv,vv[1:])):raise ValueError('Grade cutoffs must increase from D through A.')
        floor=p.get('minimum_bump_average',p.get('bump_minimum_rounded_average'))
        if floor is not None and(number(floor)is None or not 0<=number(floor)<=100):raise ValueError('The bump minimum must be between0 and 100, or blank.')
        with self.lock,self.connect()as d:
            uid=uuid.uuid4().hex;backup=self.backup(d,'Import-'+uid+'.sqlite')
            with d:
                if not d.execute('SELECT1 FROM semesters WHERE semester=?'.replace('SELECT1','SELECT 1'),(t,)).fetchone():d.execute('INSERT INTO semesters VALUES(?,?,?,?,?)',(t,2000+int(t[2:]),{'Sp':'Spring','Fa':'Fall','Su':'Summer'}[t[:2]],'current',json.dumps(p)))
                d.execute('INSERT OR REPLACE INTO app_policies VALUES(?,?)',(t,json.dumps(p)))
                for key in weights:
                    aid='M'+self.course_code+'-'+t+'-'+key
                    if not d.execute('SELECT1 FROM assessment_definitions WHERE assessment_id=?'.replace('SELECT1','SELECT 1'),(aid,)).fetchone():aid=self.assessment(d,t,key,label(key))
                    d.execute('UPDATE assessment_definitions SET weight_percent=?,policy=? WHERE assessment_id=?',(weights[key],json.dumps(p),aid))
                for r in d.execute('SELECT ruid FROM enrollments WHERE semester=?',(t,)).fetchall():self.refresh_average(d,r[0],t)
                d.execute('INSERT INTO app_imports VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,'policy','Grading policy',t,NOW(),json.dumps({'updated':1}),'committed',str(backup),None,'semester','[]'));self.touch(d)
            self.previews.clear();return {'message':'Grading policy saved. It can be undone in Import history.'}
    def save_instructors(self,payload):
        t=semester(payload.get('semester'));rr=payload.get('rows',[])
        if not isinstance(rr,list)or not rr:raise ValueError('Add at least one section and instructor.')
        out=[];seen=set()
        for r in rr:
            sec=section(r.get('section'))
            if not sec or sec in seen:raise ValueError('Each row needs a unique section.')
            rec={k:clean(v)for k,v in r.items()if k in ('instructor','email','lecturer','recitation','lecturer_email','recitation_email')}
            if not any(rec.get(k)for k in ('instructor','lecturer','recitation')):raise ValueError('Add a lecturer or recitation instructor.')
            seen.add(sec);out.append({**rec,'section':sec})
        with self.lock,self.connect()as d:
            uid=uuid.uuid4().hex;backup=self.backup(d,'Import-'+uid+'.sqlite')
            with d:
                self.ensure_term(d,t)
                for r in out:teacher_links.apply_instructor_row(d,t,r)
                d.execute('INSERT INTO app_imports VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,'instructors','Section teaching assignments',t,NOW(),json.dumps({'updated':len(out)}),'committed',str(backup),None,'sections',json.dumps(sorted(seen))));self.touch(d)
            self.previews.clear();return {'message':'Lecturer and recitation assignments saved. They can be undone in Import history.'}
