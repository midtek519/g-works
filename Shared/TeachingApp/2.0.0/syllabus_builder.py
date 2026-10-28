"""Editable syllabus drafts and protected course defaults. Live Rutgers lookups are not cached."""
from pathlib import Path
from copy import deepcopy
from datetime import date,timedelta
from html.parser import HTMLParser
from urllib.request import Request,urlopen
from urllib.parse import urljoin
import json,re,hashlib,secrets,html,gzip
from core import save,stamp,term,escape,tex_input
from toolchain import question_bank_path

PERIODS=['8:30–9:50 am','10:20–11:40 am','12:10–1:30 pm','2:00–3:20 pm','3:50–5:10 pm','5:40–7:00 pm','7:30–8:50 pm','9:20–10:40 pm']
COMBOS=[f'{days}{p}' for days,periods in [('MTh',range(1,4)),('TF',range(1,4)),('MW',range(4,9)),('TTh',range(4,9))] for p in periods]+['W1F6','W2F5','W3F4']
DAY_INDEX={'M':0,'T':1,'W':2,'Th':3,'F':4}
SHARED=['SyllabusSASCoreGoals','SyllabusTechnology','SyllabusAcademicIntegrity','SyllabusTestingServices','SyllabusStudentWellness']
TITLES={'SyllabusCourseDescription':'Course Description','SyllabusLearningGoals':'Course Learning Goals','SyllabusPrerequisites':'Prerequisites','SyllabusTextbook':'Textbook & MyLab','SyllabusAbsences':'Absences & Makeups','SyllabusCanvasSites':'Canvas Sites','SyllabusAIPolicy':'AI Policy','SyllabusFinalGrades':'Final Grades'}

def split_name(value):
    value=str(value or '').strip()
    if ',' in value:
        last,first=value.split(',',1)
        return first.strip(),last.strip()
    parts=value.rsplit(None,1)
    return (parts[0],parts[1]) if len(parts)==2 else (value,'')

def normalize_names(b):
    for prefix,key in [('', 'name'),('recitation_', 'recitation_name')]:
        first,last=prefix+'first_name',prefix+'last_name'
        if first not in b and last not in b:b[first],b[last]=split_name(b.get(key,''))
        b.setdefault(first,'');b.setdefault(last,'')
        b[key]=' '.join(x.strip() for x in [b[first],b[last]] if x.strip())
    for key in ['lookup_name','lookup_recitation_name']:
        if b.get(key):b[key]=' '.join(x for x in split_name(b[key]) if x)
    return b

LAYOUT_PARTS={'header','meetings','recitation','canvas-urls','schedule','university'}
def document_layout(content,code=None):
    blocks=content['blocks'];ids=[b['id'] for b in blocks]
    anchor=next((b['id'] for b in reversed(blocks) if b['enabled'] and b['id'] in ('SyllabusCourseDescription','SyllabusLearningGoals','SyllabusPrerequisites')),None)
    default=['header']+([] if anchor else ['meetings','recitation'])
    for item in ids:
        if item=='SyllabusCanvasSites':default.append('canvas-urls')
        if item=='grading' and code=='152':default.append('pagebreak-grading')
        default.append(item)
        if item==anchor:default+=['meetings','recitation']
    if 'canvas-urls' not in default:default.append('canvas-urls')
    default+=['pagebreak-schedule','schedule','pagebreak-university','university']
    if 'layout' not in content:return default
    layout=content['layout']
    if not isinstance(layout,list) or len(layout)>120 or any(not isinstance(x,str) for x in layout) or len(set(layout))!=len(layout):raise ValueError('Check document section order and page breaks.')
    allowed=set(ids)|LAYOUT_PARTS
    if any(x not in allowed and not re.fullmatch(r'pagebreak-[A-Za-z0-9-]+',x) for x in layout):raise ValueError('Unknown document section in syllabus order.')
    # Missing content items are added without restoring intentionally removed breaks.
    result=list(layout)
    for item in default:
        if item not in result and not item.startswith('pagebreak-'):
            index=result.index('schedule') if 'schedule' in result else len(result)
            result.insert(index,item)
    return result

def short_date(value):
    value=str(value or '').strip()
    months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    try:
        day=date.fromisoformat(value)
        return months[day.month-1]+'. '+str(day.day)
    except ValueError:pass
    match=re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?[~\s,]+(\d{1,2})\b',value,re.I)
    if match:
        month=next(i+1 for i,x in enumerate(months) if x.lower()==match[1].lower())
        try:day=date(2000,month,int(match[2]));return months[day.month-1]+'. '+str(day.day)
        except ValueError:pass
    match=re.fullmatch(r'(\d{1,2})/(\d{1,2})/\d{4}',value)
    if match:
        try:day=date(2000,int(match[1]),int(match[2]));return months[day.month-1]+'. '+str(day.day)
        except ValueError:pass
    return escape(value or 'TBA')

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def group(s,i):
    while i<len(s) and s[i].isspace():i+=1
    if i>=len(s) or s[i]!='{':raise ValueError('Check matching braces in syllabus content.')
    start=i+1;depth=1;i+=1
    while i<len(s):
        if s[i]=='\\':i+=2;continue
        if s[i]=='{':depth+=1
        elif s[i]=='}':
            depth-=1
            if not depth:return s[start:i],i+1
        i+=1
    raise ValueError('Check matching braces in syllabus content.')
def strip_comments(s):return re.sub(r'(?<!\\)%[^\n]*','',s)
def macro(s,name):
    match=re.search(r'\\(?:newcommand|renewcommand)\{\\'+re.escape(name)+r'\}(?:\[[^]]*\])?\s*',s)
    return group(s,match.end())[0].strip() if match else ''
def command_args(s,name,count):
    result=[]
    for match in re.finditer(r'\\'+re.escape(name)+r'(?![A-Za-z])',s):
        try:
            args=[];pos=match.end()
            for _ in range(count):value,pos=group(s,pos);args.append(value)
            result.append(args)
        except ValueError:continue
    return result
def readable(s):
    s=strip_comments(s)
    s=re.sub(r'\\SyllabusItem\{[^}]*\}\s*\{','',s)
    s=re.sub(r'\\(?:href|SyllabusOptionalLink)\{[^}]*\}\s*\{([^}]*)\}',r'\1',s)
    s=re.sub(r'\\(?:begin|end)\{(?:tabular|tabularx|enumerate|itemize|center)\}(?:\[[^]]*\])?','',s)
    s=re.sub(r'\\item(?:\[[^]]*\])?', '\n• ',s)
    s=re.sub(r'\\(?:textbf|textit|emph|underline|fbox)\{([^{}]*)\}',r'\1',s)
    s=s.replace('\\vi','\n\n').replace('\\Vi','\n\n').replace('\\\\','\n').replace('~',' ').replace('\\%','%').replace('\\&','&').replace('\\#','#').replace('\\S','§')
    s=re.sub(r'\\[A-Za-z]+\*?(?:\[[^]]*\])?','',s)
    s=s.replace('{','').replace('}','').replace('&',' | ')
    return re.sub(r'\n\s*\n\s*\n','\n\n',s).strip()
def component_label(s):return re.sub(r'\\([%&#_$])',r'\1',s).strip().rstrip(':')
def clean(value,label,limit=6000):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Check '+label+'.')
    return value.strip()
def latex(value):
    value=tex_input(value)
    depth=0
    for c in re.sub(r'\\[{}%]','',strip_comments(value)):
        if c=='{':depth+=1
        elif c=='}':depth-=1
        if depth<0:raise ValueError('Check matching braces in syllabus wording.')
    if depth:raise ValueError('Check matching braces in syllabus wording.')
    return value
def number(value,label,maximum=1000):
    try:n=float(value)
    except (ValueError,TypeError):raise ValueError('Enter a number for '+label+'.')
    if not 0<=n<=maximum:raise ValueError('Check '+label+'.')
    return int(n) if n.is_integer() else n

class ScheduleParser(HTMLParser):
    def __init__(self):super().__init__();self.heading=False;self.head='';self.course='';self.cell=None;self.row=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='h2':self.heading=True;self.head=''
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell=''
    def handle_data(self,data):
        if self.heading:self.head+=data
        if self.cell is not None:self.cell+=data
    def handle_endtag(self,tag):
        if tag=='h2':
            self.heading=False;m=re.search(r'01:640:(\d{3})',self.head);self.course=m[1] if m else ''
        if tag in ('td','th') and self.cell is not None:self.row.append(re.sub(r'\s+',' ',self.cell).strip());self.cell=None
        if tag=='tr' and len(self.row)>=8 and self.course:self.rows.append((self.course,self.row))

class SyllabusBuilder:
    def __init__(self,desk):self.desk=desk;self.root=desk.data/'Syllabuses'
    def context(self,code,tag):
        code=str(code);self.desk.module(code);term(tag)
        if code=='136':raise ValueError('Choose an active course.')
        return code,tag
    def seed(self,code):
        path=self.desk.repo/'lib'/('mh-'+code)/('mh-'+code+'-syllabus.sty')
        text=strip_comments(path.read_text(encoding='utf8')) if path.is_file() else ''
        blocks=[]
        for name,title in TITLES.items():
            body=macro(text,name)
            if body:
                items=command_args(body,'SyllabusItem',2)
                body=items[0][1].strip() if items else body
                if name=='SyllabusFinalGrades':body=body.replace('36\\%',r'\SyllabusFinalExamWeight\%')
                blocks.append({'id':name,'title':title,'body':body,'enabled':True})
        if not blocks:
            blocks=[{'id':name,'title':title,'body':'','enabled':name in ('SyllabusCourseDescription','SyllabusLearningGoals','SyllabusTextbook','SyllabusAbsences')} for name,title in TITLES.items()]
        topics=[{'label':a,'sections':b,'title':t} for a,b,t,_ in command_args(text,'mhsyllabus_add_topic:nnnn',4)]
        if not topics:
            cat=json.loads((question_bank_path(self.desk.root,self.desk.repo)/'catalog.json').read_text(encoding='utf8'))
            ts=[t for t in cat['topics'] if code in t.get('course_labels',{}) and t['course_labels'][code].get('lecture')]
            topics=[{'label':str(t['course_labels'][code]['lecture']),'sections':t['course_labels'][code].get('section',''),'title':t['course_labels'][code].get('title',t['label'])} for t in sorted(ts,key=lambda t:t['course_labels'][code].get('chapter_order',999))]
        grading_position=next((i for i,b in enumerate(blocks) if b['id']=='SyllabusFinalGrades'),len(blocks))
        blocks.insert(grading_position,{'id':'grading','title':'Grading','body':'','enabled':True,'kind':'grading'})
        grading=[];table=macro(text,'SyllabusGradingTable')
        table_items=command_args(table,'SyllabusItem',2)
        if table_items:table=table_items[0][1]
        for label,w,count,drops in re.findall(r'([^\n]+?)\s*\n\s*&\s*(\d+)\\%\s*&\s*(\d+)\s*&\s*(\d+)',table):
            grading.append({'name':component_label(label),'weight':int(w),'count':int(count),'dropped':int(drops)})
        details=macro(text,'SyllabusGradingItems');descriptions={component_label(a):b.strip() for a,b in re.findall(r'\\item\s*\\textbf\{([^}]+)\}:?\s*(.*?)(?=\\item|\\end\{itemize\})',details,re.S)}
        for row in grading:row['description']=descriptions.get(row['name'],'')
        thresholds=[{'letter':a,'minimum':int(n)} for a,n in re.findall(r'&\s*(A|B\+|B|C\+|C|D)(?:\\phantom\{\+\})?\s*&\s*(\d+)\\%',table)]
        grading_note=table.split('\\end{center}',1)[1].strip() if '\\end{center}' in table else ''
        exams=[]
        for n,i in command_args(text,'SetMidtermTopic',2):
            title=topics[int(i)-1]['title'];bold=command_args(title,'textbf',1)
            coverage=re.split(r'covers[~\s]*',bold[0][0] if bold else title,maxsplit=1,flags=re.I)[-1]
            exams.append({'name':'Midterm Exam #'+n,'topic':int(i),'weight':18 if code=='135' else 16,'coverage':coverage})
        source_path=self.desk.repo/('mh-'+code+'-course-documents')/'syllabuses/syllabus.tex'
        if source_path.is_file():
            document=strip_comments(source_path.read_text(encoding='utf8'))
            def position(block):
                marker='SyllabusGradeComponents' if block['id']=='grading' else block['id']
                match=re.search(r'\\'+re.escape(marker)+r'\b',document)
                return match.start() if match else len(document)
            blocks.sort(key=position)
        return {'blocks':blocks,'grading':grading,'thresholds':thresholds,'grading_note':grading_note,'topics':topics,'exams':exams,'recitation_intro':readable(macro(text,'RecitationIntroduction')) or 'Introduction','schema':1}
    def defaults(self,code):
        p=self.root/'Course defaults'/(code+'.json')
        data=json.loads(p.read_text(encoding='utf8')) if p.is_file() else self.seed(code)
        revision=digest(data)
        data.setdefault('layout',document_layout(data,code))
        return data,revision
    def basic(self,code,tag):
        p=self.desk.repo/('mh-'+code+'-course-documents')/'syllabuses/semesters'/(tag+'.tex')
        text=strip_comments(p.read_text(encoding='utf8')) if p.is_file() else ''
        names={'name':'SetInstructorName','email':'SetInstructorEmail','office':'SetInstructorOffice','office_hours':'SetInstructorOfficeHours','recitation_name':'SetRecitationInstructorName','recitation_email':'SetRecitationInstructorEmail','recitation_office':'SetRecitationInstructorOffice','recitation_hours':'SetRecitationInstructorOfficeHours','canvas':'SetInstructorCanvasSite','all_canvas':'SetAllSectionsCanvasSite','final_date':'SetFinalExamDate','final_time':'SetFinalExamTime'}
        result={k:re.sub(r'\\[,;!]',' ',(command_args(text,v,1) or [['']])[0][0]).replace('``','“').replace("''",'”') for k,v in names.items()}
        from instructor_profile import read as read_profile
        profile=read_profile(self.desk.root)
        if profile.get('configured'):
            for key in ('name','email','office'):result[key]=profile.get(key,'')
        lectures=command_args(text,'SetLecture',4);recits=command_args(text,'AddRecitation',4)
        result['sections']=lectures[0][0].replace('--','-') if lectures else ''
        result['meetings']=([{'kind':'Lecture','section':result['sections'],'days':a[1],'period':a[2],'room':a[3]} for a in lectures]+[{'kind':'Recitation','section':a[0],'days':a[1],'period':a[2],'room':a[3]} for a in recits])
        result['combo']=(lectures[0][1]+lectures[0][2]) if lectures else ''
        result['final_coverage']='All course topics'
        result['final_room']='Announced through Canvas'
        result['lookup_section']='';result['calendar']=tag
        return normalize_names(result)
    def draft_path(self,code,tag,draft_id=None):
        code,tag=self.context(code,tag)
        if draft_id in (None,'','legacy'):return self.root/'Drafts'/(code+'-'+tag+'.json')
        if not isinstance(draft_id,str) or not re.fullmatch(r'S[a-f0-9]{16}',draft_id):raise ValueError('Choose a saved syllabus or create a new one.')
        return self.root/'Drafts'/(code+'-'+tag+'-'+draft_id+'.json')
    def list_drafts(self,code,tag):
        code,tag=self.context(code,tag);items=[];folder=self.root/'Drafts';legacy=self.draft_path(code,tag)
        paths=[legacy,*sorted(folder.glob(code+'-'+tag+'-S*.json'))] if folder.is_dir() else []
        for path in paths:
            if not path.is_file():continue
            ident='legacy' if path==legacy else path.stem[len(code+'-'+tag+'-'):]
            if ident!='legacy' and not re.fullmatch(r'S[a-f0-9]{16}',ident):continue
            draft=json.loads(path.read_text(encoding='utf-8'));basic=draft.get('basic',{})
            if str(draft.get('course'))!=code or draft.get('semester')!=tag:continue
            items.append({'id':ident,'sections':basic.get('sections',''),'instructor':basic.get('name',''),'updated':draft.get('updated',''),'saved':True})
        source=self.desk.repo/('mh-'+code+'-course-documents')/'syllabuses/semesters'/(tag+'.tex')
        if not legacy.is_file() and source.is_file():
            basic=self.basic(code,tag);items.insert(0,{'id':'legacy','sections':basic.get('sections',''),'instructor':basic.get('name',''),'updated':'','saved':False,'source':True})
        return {'course':code,'semester':tag,'items':items}
    def model(self,code,tag,draft_id=None):
        code,tag=self.context(code,tag);defaults,revision=self.defaults(code)
        new_draft=draft_id=='new'
        if new_draft:draft_id='S'+secrets.token_hex(8)
        p=self.draft_path(code,tag,draft_id)
        stored_revision=digest(json.loads(p.read_text(encoding='utf8'))) if p.is_file() else None
        draft=json.loads(p.read_text(encoding='utf8')) if p.is_file() else {'basic':self.basic(code,tag),'content':deepcopy(defaults),'course':code,'semester':tag,'based_on':revision}
        if draft_id not in (None,'','legacy'):draft['id']=draft_id
        if new_draft:
            basic=draft['basic']
            for key in ['sections','combo','lookup_section','recitation_first_name','recitation_last_name','recitation_name','recitation_email','recitation_office','recitation_hours','canvas','final_date','final_time','final_exam_code']:basic[key]=''
            basic['meetings']=[];basic['final_room']='Announced through Canvas'
        draft['basic'].setdefault('final_room','Announced through Canvas')
        normalize_names(draft['basic'])
        draft['content'].setdefault('layout',document_layout(draft['content'],code))
        shared=(self.desk.repo/'lib/mh-syllabus.sty').read_text(encoding='utf8')
        calendars=[]
        for x in (self.desk.repo/'semesters').glob('*.tex'):
            if re.fullmatch(r'(fa|sp|su)\d{2}',x.stem):calendars.append({'value':x.stem,'label':term(x.stem)})
        calendar=self.calendar(draft) if (self.desk.repo/'semesters'/(draft['basic'].get('calendar',tag)+'.tex')).is_file() else None
        return {'draft_id':draft_id or 'legacy','draft':draft,'draft_revision':stored_revision,'defaults':defaults,'defaults_revision':revision,'shared':[{'title':title,'body':(command_args(macro(shared,name),'SyllabusItem',2) or [['',macro(shared,name)]])[0][1]} for name,title in zip(SHARED,['SAS Core Learning Goals','Technology','Academic Integrity','Testing Services','Student Wellness'])],'calendars':sorted(calendars,key=lambda x:(int(x['value'][2:]),{'sp':0,'su':1,'fa':2}[x['value'][:2]])),'calendar':calendar,'periods':PERIODS,'combos':COMBOS,'destination':str(self.desk.publish_folder(code,tag,'Syllabus')),'has_profile':code in ('135','152'),'grading_intro':self.grade_intro(code)}
    def validate_content(self,data,code=None):
        if not isinstance(data,dict):raise ValueError('Check the syllabus content.')
        result=deepcopy(data)
        for key,limit in [('blocks',40),('topics',100),('grading',20),('thresholds',12),('exams',10)]:
            if not isinstance(result.get(key),list) or len(result[key])>limit:raise ValueError('Check '+key+'.')
        seen=set()
        for b in result['blocks']:
            if not isinstance(b,dict):raise ValueError('Check syllabus items.')
            b['id']=clean(b.get('id'),'item ID',100)
            if not re.fullmatch(r'[A-Za-z0-9-]+',b['id']) or b['id'] in seen:raise ValueError('Each syllabus item must have a unique ID.')
            if b['id'] in LAYOUT_PARTS or b['id'].startswith('pagebreak-'):raise ValueError('That item ID is reserved for document layout.')
            seen.add(b['id']);b['title']=clean(b.get('title'),'item heading',150);b['body']=latex(clean(b.get('body'),'item wording',40000));b['enabled']=bool(b.get('enabled'))
        for t in result['topics']:
            for k in ('label','sections','title'):t[k]=latex(clean(t.get(k,''),'topic or activity',3000))
        for row in result['grading']:
            row['name']=clean(row.get('name'),'grading component',150)
            for k in ('weight','count','dropped'):row[k]=number(row.get(k,0),k,100 if k=='weight' else 1000)
            if row['dropped']>row['count']:raise ValueError('Dropped assignments cannot exceed the assignment count.')
            row['description']=latex(clean(row.get('description',''),'grading explanation',10000))
        for row in result['thresholds']:row['letter']=clean(row.get('letter'),'letter grade',10);row['minimum']=number(row.get('minimum'),'grade threshold',100)
        for ex in result['exams']:
            ex['name']=clean(ex.get('name'),'exam name',150);ex['topic']=int(number(ex.get('topic'),'exam schedule position',100));ex['weight']=number(ex.get('weight'),'exam weight',100);ex['coverage']=latex(clean(ex.get('coverage',''),'exam coverage',3000))
        result['grading_note']=latex(clean(result.get('grading_note',''),'grading note',10000))
        result['layout']=document_layout(result,code)
        result['recitation_intro']=clean(result.get('recitation_intro','Introduction'),'recitation introduction',300)
        return result
    def validate_draft(self,payload):
        code,tag=self.context(payload.get('course'),payload.get('semester'));data=payload.get('draft')
        if not isinstance(data,dict) or not isinstance(data.get('basic'),dict):raise ValueError('Check the syllabus fields.')
        d=deepcopy(data);d['course']=code;d['semester']=tag;d['content']=self.validate_content(d.get('content'),code)
        ident=payload.get('draft_id') or d.get('id')
        self.draft_path(code,tag,ident)
        if payload.get('draft_id') and d.get('id') and payload['draft_id']!=d['id']:raise ValueError('The syllabus identity changed. Reopen it before saving.')
        if ident not in (None,'','legacy'):d['id']=ident
        b=d['basic'];self.context(code,b.get('calendar',tag))
        if b.get('calendar',tag)!=tag:raise ValueError('The selected calendar must match the syllabus semester.')
        for k,v in list(b.items()):
            if k!='meetings':b[k]=clean(v,k,3000)
        if not isinstance(b.get('meetings'),list) or len(b['meetings'])>50:raise ValueError('Check class meetings.')
        for mt in b['meetings']:
            for k in ('kind','section','days','period','room'):mt[k]=clean(str(mt.get(k,'')),k,150)
            if mt['kind'] not in ('Lecture','Recitation'):raise ValueError('Choose Lecture or Recitation.')
            days=re.findall('Th|M|T|W|F',mt['days'])
            if ''.join(days)!=mt['days'] or not days or (mt['kind']=='Recitation' and len(days)!=1):raise ValueError('Use weekday codes M, T, W, Th, F. Each recitation uses one day.')
            if mt['period'] not in [str(i) for i in range(1,9)]:raise ValueError('Choose a class period from 1 to 8.')
        normalize_names(b)
        return code,tag,d
    def save_draft(self,payload):
        with self.desk.lock:
            code,tag,d=self.validate_draft(payload);ident=payload.get('draft_id') or d.get('id')
            p=self.draft_path(code,tag,ident)
            if ident not in (None,'','legacy'):d['id']=ident
            current=json.loads(p.read_text(encoding='utf8')) if p.is_file() else None
            if (digest(current) if current else None)!=payload.get('expected_revision'):raise ValueError('This syllabus changed. Reload it before saving.')
            if p.is_file():self.desk._history({p:p.read_bytes()},'Syllabus draft revised')
            d['updated']=stamp();save(p,d)
            return {'draft_id':ident or 'legacy','draft':d,'draft_revision':digest(d)}
    def save_defaults(self,payload):
        with self.desk.lock:
            code,tag=self.context(payload.get('course'),payload.get('semester'));old,rev=self.defaults(code)
            if payload.get('confirmed') is not True:raise ValueError('Explicitly unlock course defaults before saving.')
            if payload.get('expected_revision')!=rev:raise ValueError('Course defaults changed. Reload before saving.')
            data=self.validate_content(payload.get('content'),code);p=self.root/'Course defaults'/(code+'.json')
            if p.is_file():self.desk._history({p:p.read_bytes()},'Syllabus course defaults revised')
            save(p,data);return {'defaults':data,'defaults_revision':digest(data)}
    def calendar(self,d):
        b=d['basic'];tag=b.get('calendar',d['semester']);path=self.desk.repo/'semesters'/(tag+'.tex')
        if not path.is_file():raise ValueError('Select a semester with a local calendar before generating dates.')
        text=strip_comments(path.read_text(encoding='utf8'))
        ranges=command_args(text,'SetSemesterDates',2) or command_args(text,'SetSemesterDateRange',2)
        if not ranges:raise ValueError('The selected local calendar has no class dates.')
        start,end=map(date.fromisoformat,ranges[0]);excluded={x[0] for x in command_args(text,'AddNoClassDate',1)}
        for a,z in command_args(text,'AddNoClassRange',2):
            day,last=date.fromisoformat(a),date.fromisoformat(z)
            while day<=last:excluded.add(day.isoformat());day+=timedelta(days=1)
        overrides=dict(command_args(text,'AddClassDayOverride',2));rows=[];lecture=0;counts={};topics=[{**t,'topic_position':i+1} for i,t in enumerate(d['content']['topics'])];warnings=[]
        # Preserve the explicit Friday pacing adjustment in the existing 135 Fall 2026 profile.
        if d['course']=='135' and tag=='fa26' and any('F' in mt['days'] for mt in b['meetings'] if mt['kind']=='Lecture') and len(topics)>=26:topics[24],topics[25]=topics[25],topics[24]
        day=start
        while day<=end:
            iso=day.isoformat();weekday=DAY_INDEX.get(overrides.get(iso),day.weekday())
            if iso not in excluded:
                meetings=[mt for mt in b['meetings'] if weekday in [DAY_INDEX[x] for x in re.findall('Th|M|T|W|F',mt['days'])]]
                if any(mt['kind']=='Lecture' for mt in meetings):
                    t=topics[lecture] if lecture<len(topics) else {'label':'—','sections':'—','title':'Topic not assigned; review pacing'};lecture+=1
                    rows.append({'date':iso,'kind':'Lecture','position':lecture,**t})
                if any(mt['kind']=='Recitation' for mt in meetings):
                    counts[weekday]=counts.get(weekday,0)+1;n=counts[weekday]
                    rows.append({'date':iso,'kind':'Recitation','label':'Rec.','sections':'—','title':d['content'].get('recitation_intro','Introduction') if n==1 else 'Quiz '+str(n-1)})
            day+=timedelta(days=1)
        if lecture!=len(topics):warnings.append(f'{lecture} lecture meetings and {len(topics)} topics/activities. Review pacing before publishing.')
        return {'rows':rows,'warnings':warnings,'lecture_count':lecture}
    def _department_lookup(self,payload):
        code,tag=self.context(payload.get('course'),payload.get('semester'));section=clean(payload.get('section',''),'section',30)
        if not re.fullmatch(r'[A-Za-z0-9-]+',section):raise ValueError('Enter a section number, for example 10.')
        def fetch(url):
            req=Request(url,headers={'User-Agent':'G-Whiz-Syllabus-Builder/1.0','Cache-Control':'no-cache','Pragma':'no-cache'})
            with urlopen(req,timeout=20) as response:
                if response.geturl().split('/')[2] not in ('www.math.rutgers.edu','iw3.math.rutgers.edu'):raise ValueError('Rutgers returned an unexpected schedule address.')
                data=response.read(2_000_001)
                if len(data)>2_000_000:raise ValueError('The Rutgers schedule is too large to read.')
                return data.decode('utf8',errors='replace')
        try:
            index=fetch('https://www.math.rutgers.edu/resources/teaching-schedules');season={'fa':'fall','sp':'spring','su':'summer'}[tag[:2]];year='20'+tag[2:]
            match=re.search(r'https://iw3\.math\.rutgers\.edu/schedule/undergraduate-'+year+'-'+season+r'\.html',html.unescape(index))
            if not match:raise ValueError('Rutgers has not listed that semester schedule. Enter meetings manually.')
            url=match[0];parser=ScheduleParser();parser.feed(fetch(url));course=[row for c,row in parser.rows if c==code]
            groups=[];current=None
            for row in course:
                if row[3].lower()=='lecture':current=[];groups.append(current)
                if current is not None:current.append(row)
            def includes(label):
                if section==label:return True
                if section.isdigit() and re.fullmatch(r'\d+\s*-\s*\d+',label):a,z=map(int,label.split('-'));return a<=int(section)<=z
                return False
            matches=[g for g in groups if any(includes(row[0]) for row in g)]
            if len(matches)!=1:raise ValueError('No unique lecture group matched that section. Check it or enter meetings manually.')
            rows=matches[0];meetings=[]
            for row in rows:
                pieces=re.findall(r'(Th|M|T|W|F|MW|MTh|TF|TTh)([1-8])',row[4])
                # Ordinary combined days use one period; split-period WF combinations use two rows.
                ordinary=re.fullmatch(r'(MTh|TTh|MW|TF|M|T|W|Th|F)([1-8])',row[4])
                if ordinary:pieces=[ordinary.groups()]
                if not pieces:raise ValueError('That meeting uses a nonstandard time. Enter it manually.')
                for days,period in pieces:meetings.append({'kind':row[3],'section':row[0],'days':days,'period':period,'room':row[6]})
            lecture=rows[0];recit=next((row for row in rows if row[3]=='Recitation'),None)
            return {'source':url,'checked':stamp(),'sections':lecture[0],'name':lecture[2],'recitation_name':recit[2] if recit else '', 'combo':lecture[4],'meetings':meetings,'recitation_instructors':[{'section':row[0],'name':row[2]} for row in rows if row[3]=='Recitation']}
        except ValueError:raise
        except Exception:raise ValueError('The live Rutgers schedule could not be reached. Retry or enter meetings manually.')
    def lookup(self,payload):
        code,tag=self.context(payload.get('course'),payload.get('semester'))
        section=clean(payload.get('section',''),'section',30).upper()
        if not re.fullmatch(r'[A-Z0-9-]+',section):raise ValueError('Enter a section number, for example 10.')
        warnings=[];department=None
        try:department=self._department_lookup(payload)
        except ValueError as ex:warnings.append('Math department names could not be confirmed: '+str(ex))
        url='https://classes.rutgers.edu/soc/api/courses.json?year=20'+tag[2:]+'&term='+{'fa':'9','sp':'1','su':'7'}[tag[:2]]+'&campus=NB'
        try:
            with urlopen(Request(url,headers={'User-Agent':'G-Whiz-Syllabus-Builder/1.0','Cache-Control':'no-cache','Pragma':'no-cache'}),timeout=25) as response:
                raw=response.read(30_000_001)
            if len(raw)>30_000_000:raise ValueError('The SOC response is too large.')
            if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
            data=json.loads(raw)
            course=next((c for c in data if c.get('subject')=='640' and c.get('offeringUnitCode')=='01' and c.get('courseNumber')==code),None)
            if not course:raise ValueError('SOC has not listed this course for the selected semester. Enter meetings manually.')
            normalize=lambda x:str(int(x)) if str(x).isdigit() else str(x).upper()
            first=section.split('-')[0]
            selected=next((x for x in course['sections'] if normalize(x['number'])==normalize(first)),None)
            if not selected:raise ValueError('SOC has not listed that section for this semester.')
            def lecture_signature(x):
                return sorted((m.get('meetingDay'),m.get('startTimeMilitary'),m.get('endTimeMilitary'),m.get('buildingCode'),m.get('roomNumber')) for m in x.get('meetingTimes',[]) if m.get('meetingModeDesc')=='LEC')
            signature=lecture_signature(selected)
            group=[x for x in course['sections'] if signature and lecture_signature(x)==signature] or [selected]
            if department:
                allowed={normalize(mt['section']) for mt in department['meetings'] if mt['kind']=='Recitation'}
                if allowed:group=[x for x in group if normalize(x['number']) in allowed] or [selected]
            sections=department['sections'] if department else ', '.join(x['number'] for x in group)
            starts={'0830':'1','1020':'2','1210':'3','1400':'4','1550':'5','1740':'6','1930':'7','2120':'8'}
            meetings=[];seen={}
            for entry in group:
                for mt in entry.get('meetingTimes',[]):
                    kind='Lecture' if mt.get('meetingModeDesc')=='LEC' else 'Recitation' if mt.get('meetingModeDesc')=='RECIT' else None
                    if not kind:continue
                    period=starts.get(mt.get('startTimeMilitary',''))
                    if not period:raise ValueError('SOC lists a nonstandard meeting time. Enter this meeting manually.')
                    room='-'.join(x for x in [mt.get('buildingCode',''),mt.get('roomNumber','')] if x)
                    key=(kind,sections if kind=='Lecture' else entry['number'],period,room)
                    day={'H':'Th','TH':'Th'}.get(mt.get('meetingDay'),mt.get('meetingDay',''))
                    if key not in seen:
                        seen[key]={'kind':kind,'section':key[1],'days':'','period':period,'room':room};meetings.append(seen[key])
                    if day not in re.findall('Th|M|T|W|F',seen[key]['days']):seen[key]['days']+=day
            lectures=[mt for mt in meetings if mt['kind']=='Lecture']
            combo=lectures[0]['days']+lectures[0]['period'] if len(lectures)==1 else ''.join(mt['days']+mt['period'] for mt in lectures)
            exam=selected.get('finalExam') or '';exam_code=selected.get('examCode') or '';final_date='';final_time=''
            match=re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{4})\s*-\s*(\d{4})\s*(AM|PM)',exam.strip(),re.I)
            if match:
                month,day,year,start,end,am_pm=match.groups();actual=date(int(year),int(month),int(day))
                final_date=actual.strftime('%A, %B ')+str(actual.day)+', '+str(actual.year)
                final_time=str(int(start[:2]))+':'+start[2:]+'–'+str(int(end[:2]))+':'+end[2:]+' '+am_pm.lower()
            else:warnings.append('SOC has not supplied a resolved final-exam date/time'+(' (code '+exam_code+')' if exam_code else '')+'. Existing entries will be retained.')
            if any((x.get('examCode'),x.get('finalExam'))!=(selected.get('examCode'),selected.get('finalExam')) for x in group):warnings.append('Associated sections have different final-exam information. These exam details apply to the selected section '+selected['number']+'.')
            result={'source':department['source'] if department else 'https://www.math.rutgers.edu/resources/teaching-schedules','soc_source':url,'finals_source':'https://scheduling.rutgers.edu/exam-scheduling/final-exams/','checked':stamp(),'sections':sections,'name':department['name'] if department else '', 'recitation_name':department['recitation_name'] if department else '', 'recitation_instructors':department.get('recitation_instructors',[]) if department else [],'combo':combo,'meetings':meetings,'final_date':final_date,'final_time':final_time,'final_exam_code':exam_code,'warnings':warnings}
            result['first_name'],result['last_name']=split_name(result['name'])
            result['recitation_first_name'],result['recitation_last_name']=split_name(result['recitation_name'])
            result['name']=' '.join(x for x in [result['first_name'],result['last_name']] if x)
            result['recitation_name']=' '.join(x for x in [result['recitation_first_name'],result['recitation_last_name']] if x)
            return result
        except ValueError:raise
        except Exception:raise ValueError('The live SOC details could not be reached. Retry or enter meetings and final details manually.')

    def source(self,d,kind):
        b=normalize_names(deepcopy(d['basic']));code=d['course'];calendar=self.calendar(d);content=d['content'];e=escape
        basics={'SetInstructorName':'name','SetInstructorEmail':'email','SetInstructorOffice':'office','SetInstructorOfficeHours':'office_hours','SetRecitationInstructorName':'recitation_name','SetRecitationInstructorEmail':'recitation_email','SetRecitationInstructorOffice':'recitation_office','SetRecitationInstructorOfficeHours':'recitation_hours','SetInstructorCanvasSite':'canvas','SetAllSectionsCanvasSite':'all_canvas','SetFinalExamDate':'final_date','SetFinalExamTime':'final_time'}
        out=['\\documentclass[document,student]{mhdocument}','\\usepackage{mh-syllabus}',r'\usepackage{needspace}',r'\UseSemester{'+b.get('calendar',d['semester'])+'}']
        out.append(r'\ExplSyntaxOn\RenewDocumentCommand{\SyllabusOptionalLink}{mm}{\tl_if_blank:eTF{#1}{#2\nobreakspace(Link~forthcoming)}{\href{#1}{#2}}}\ExplSyntaxOff')
        for command,key in basics.items():
            value=e(b.get(key,''))
            if key in ('name','recitation_name'):value=re.sub(r'"([^"]+)"',r"``\1''",value)
            out.append('\\'+command+'{'+value+'}')
        out.append(r'\renewcommand{\LectureSections}{'+e(b.get('sections',''))+'}')
        dates={ex['name']:next((row['date'] for row in calendar['rows'] if row.get('topic_position')==ex['topic']), 'TBA') for ex in content['exams']}
        final_weight=next((row['weight'] for row in content['grading'] if re.search('final',row['name'],re.I)),0)
        out.append(r'\newcommand{\SyllabusFinalExamWeight}{'+str(final_weight)+'}')
        for i in range(1,4):out.append(r'\providecommand{\Midterm'+['One','Two','Three'][i-1]+'Date}{'+e(dates.get('Midterm Exam #'+str(i),'TBA'))+'}')
        meeting=r'\begin{tabularx}{\linewidth}{@{}p{.19\linewidth}p{.15\linewidth}p{.10\linewidth}p{.21\linewidth}X@{}}'+'\n'
        for mt in b['meetings']:
            cells=[r'Sec.~'+e(mt['section']),e(mt['kind']),e(mt['days']+mt['period']),e(PERIODS[int(mt['period'])-1].replace('–','--')),e(mt['room'])]
            if mt['kind']=='Lecture':cells=[r'\textbf{'+v+'}' for v in cells]
            meeting+=' & '.join(cells)+r'\\'+'\n'
        meeting+=r'\end{tabularx}'
        out.append(r'\RenewDocumentCommand{\SyllabusMeetingTimes}{}{'+meeting+'}')
        lectures=[mt for mt in b['meetings'] if mt['kind']=='Lecture']
        lecture_info=r'\newline '.join(e(mt['days']+mt['period'])+', '+e(PERIODS[int(mt['period'])-1].replace('–','--'))+', '+e(mt['room']) for mt in lectures)
        info=r'\begin{tabularx}{\linewidth}{@{}>{\bfseries}lX@{}}Instructor:&\InstructorName\\[2pt]Email:&\SyllabusEmail{\InstructorEmail}\\[2pt]Lecture:&Sec.~'+e(b.get('sections',''))+r': '+lecture_info+r'\\[2pt]Office Hours:&\InstructorOfficeHours, \InstructorOffice\end{tabularx}'
        out.append(r'\renewcommand{\SyllabusCourseInfo}{'+info+'}')
        out+=['\\begin{document}',r'\SetMathLeftHeader{Math '+code+' (01:640:'+code+')}',r'\SetMathCenterHeader{Course '+('Syllabus' if kind=='Syllabus' else 'Schedule')+'}',r'\SetMathRightHeader{'+e(term(d['semester']))+'}']
        if kind=='Schedule':out.append(r'\small')
        if kind=='Schedule':out.append(r'\vspace*{-16pt}\SyllabusHeader')
        schedule=r'\begin{longtable}{@{}p{.09\linewidth}p{.08\linewidth}p{.15\linewidth}p{.60\linewidth}@{}}\toprule\textbf{Date}&\textbf{Mtg.}&\textbf{Text \S}&\textbf{Topic or Activity}\\\midrule\endfirsthead\toprule\textbf{Date}&\textbf{Mtg.}&\textbf{Text \S}&\textbf{Topic or Activity}\\\midrule\endhead'+'\n'
        for row in calendar['rows']:
            day=date.fromisoformat(row['date']);schedule+=day.strftime('%b. ')+str(day.day)+' & '+row['label'].replace('—','--')+' & '+row['sections'].replace('—','--')+' & '+row['title']+r'\\'+'\n'
            if row.get('kind')=='Lecture' and (any(ex['topic']==row.get('topic_position') for ex in content['exams']) or (re.search(r'midterm[~\s]+exam',row['title'],re.I) and not re.search(r'review',row['title'],re.I))):schedule+=r'\midrule'+'\n'
        schedule+=short_date(b.get('final_date'))+r' & -- & -- & \textbf{Final Exam}, '+e(b.get('final_time') or 'TBA')+'; '+e(b.get('final_room') or 'Announced through Canvas')+r'\\\bottomrule\end{longtable}'
        if kind=='Syllabus':
            blocks={x['id']:x for x in content['blocks']}
            headings={'SyllabusCourseDescription':r'Course\\Description','SyllabusLearningGoals':r'Course\\Learning\\Goals','SyllabusCanvasSites':r'Canvas\\Sites','SyllabusFinalGrades':r'Final\\Grades','SyllabusTextbook':r'Textbook \&\\MyLab','SyllabusAbsences':r'Absences \&\\Makeups','SyllabusAIPolicy':r'AI Policy'}
            printed=False
            for item in document_layout(content,code):
                if item.startswith('pagebreak-'):out.append(r'\clearpage');continue
                if item=='canvas-urls':continue
                if item=='header':out.append((r'\vspace*{-16pt}' if not printed else '')+r'\SyllabusHeader')
                elif item=='meetings':out.append(r'\SyllabusMeetings')
                elif item=='recitation':
                    if not b.get('recitation_name'):continue
                    out.append(r'\SyllabusRecitationInstructor')
                elif item=='schedule':out.extend([r'\begin{center}\bfseries\large Course Schedule\end{center}',schedule])
                elif item=='university':out.extend([r'\begin{center}\bfseries\large University Information \& Resources\end{center}']+['\\'+name for name in SHARED])
                else:
                    block=blocks[item]
                    if not block['enabled']:continue
                    if item=='grading':out.extend(self.grading_source(content,dates,block['title'],b,code))
                    elif block['body']:out.append(r'\SyllabusItem{'+(headings.get(item,e(block['title'])) if block['title']==TITLES.get(item) else e(block['title']))+'}{'+block['body']+'}')
                printed=True
        else:out.extend([r'\SyllabusMeetings\setlength{\LTpre}{3pt}\renewcommand{\arraystretch}{.95}',schedule])
        out.append('\\end{document}')
        return '\n'.join(out),calendar
    def grade_intro(self,code):
        path=self.desk.repo/'lib'/('mh-'+code)/('mh-'+code+'-syllabus.sty')
        text=path.read_text(encoding='utf8') if path.is_file() else ''
        args=command_args(macro(strip_comments(text),'SyllabusGradeComponents'),'SyllabusItem',2)
        return args[0][1].strip() if args else 'The tables below list the grade components and letter-grade minimums.'
    def grading_source(self,content,dates,title,b,code):
        e=escape
        heading=r'Grade\\Components' if title in ('Grading','Grade Components') else e(title)
        out=[r'\SyllabusItem{'+heading+'}{'+self.grade_intro(code)+'}',r'\SyllabusItem{\phantom{Grading}}{\begin{center}\begin{tabular}[t]{lrrr@{\hspace{1.5em}}cc}',r'\textbf{Component}&\textbf{Wt.}&\textbf{Assn.}&\textbf{Dropped}&\textbf{Letter}&\textbf{Minimum Score}\\\cmidrule(r{1.2em}){1-4}\cmidrule(l{-.3em}){5-6}']
        rows=content['grading'];letters=content['thresholds']
        for i in range(max(len(rows)+1,len(letters))):
            if i<len(rows):
                row=rows[i];left=e(row['name'])+' & '+str(row['weight'])+r'\% & '+str(row['count'])+' & '+str(row['dropped'])
            elif i==len(rows):left=r'TOTAL: & '+str(sum(x['weight'] for x in rows))+r'\% & & '
            else:left=' & & & '
            right=e(letters[i]['letter'])+' & '+str(letters[i]['minimum'])+r'\%' if i<len(letters) else ' & '
            out.append(left+' & '+right+r'\\')
        out.append(r'\end{tabular}\end{center}'+content['grading_note']+'}')
        out.append(r'\SyllabusItem{\phantom{Grading}}{\begin{itemize}[topsep=4pt,itemsep=-1ex,partopsep=-1ex,parsep=1ex]')
        for row in rows:
            if row.get('description'):out.append(r'\item \textbf{'+e(row['name'])+':} '+row['description'])
        out.append(r'\end{itemize}\begin{center}\small\begin{tabularx}{\linewidth}{@{}lrllX@{}}\textbf{Exam}&\textbf{Wt.}&\textbf{Date}&\textbf{Time}&\textbf{Coverage (Textbook Sections)}\\\toprule')
        for ex in content['exams']:out.append(r'\textit{'+e(ex['name'])+'} & '+str(ex['weight'])+r'\% & '+short_date(dates[ex['name']])+r' & in class & '+ex['coverage']+r'\\')
        final=next((r['weight'] for r in rows if re.search('final',r['name'],re.I)),0)
        out.append(r'\textit{Final Exam} & '+str(final)+r'\% & '+short_date(b.get('final_date',''))+' & '+e(b.get('final_time') or 'TBA')+' & '+e(b.get('final_coverage') or 'All course topics')+r'\\\end{tabularx}\end{center}')
        room=b.get('final_room') or 'Announced through Canvas'
        described=room.strip().lower()=='announced through canvas' and any(re.search('final',r['name'],re.I) and re.search(r'location.*canvas',r.get('description',''),re.I|re.S) for r in rows)
        out.append('}' if described else r'\noindent Final exam location: '+e(room)+'.}')
        return out
    def compile(self,payload):
        with self.desk.lock:
            if self.desk.active:raise ValueError('Let the current compilation finish first.')
            code,tag,d=self.validate_draft(payload)
            if payload.get('output') not in ('syllabus','schedule','both'):raise ValueError('Choose Syllabus only, Schedule only, or Both.')
            if not any(x['kind']=='Lecture' for x in d['basic']['meetings']):raise ValueError('Add or look up the lecture meetings before compiling.')
            if payload['output']!='schedule' and abs(sum(row['weight'] for row in d['content']['grading'])-100)>.001:raise ValueError('Grading weights must total 100% before compiling the syllabus.')
            midterm=next((r for r in d['content']['grading'] if re.search('midterm',r['name'],re.I)),None)
            if payload['output']!='schedule' and midterm and abs(midterm['weight']-sum(ex['weight'] for ex in d['content']['exams']))>.001:raise ValueError('Individual midterm weights must add up to the Midterm Exams component weight.')
            folder=self.desk.temp/'Drafts'/('syllabus-builder-'+secrets.token_hex(8));folder.mkdir(parents=True)
            jobs=[];warnings=[]
            for kind in (['Syllabus','Schedule'] if payload['output']=='both' else [payload['output'].title()]):
                source,calendar=self.source(d,kind);warnings=calendar['warnings'];p=folder/(kind+'.tex');p.write_text(source,encoding='utf8')
                name=kind+'-'+tag[:2].title()+tag[2:]
                if d.get('id'):
                    sections=re.sub(r'[^A-Za-z0-9]+','-',d['basic'].get('sections','')).strip('-')[:60]
                    name+='-'+(sections+'-' if sections else '')+d['id']
                jobs.append({'source':p,'name':name,'prefix':'','folder':self.desk.publish_folder(code,tag,kind),'kind':kind,'mode':'student','version':'A','syllabus_builder':True})
            if payload.get('publish') and warnings:raise ValueError(warnings[0]+' Preview and adjust the topic list before publishing.')
            result=self.desk.start(code,tag,[],custom=jobs,publish_when_ready=payload.get('publish') is True)
            result['syllabus_warnings']=warnings
            return result

