"""Local course compiler and authoring desk. No network, cloud, or CMD menus."""
from pathlib import Path
import sys,csv,hashlib,importlib.util,io,json,os,re,secrets,shutil,subprocess,threading,time,zipfile
from datetime import datetime,timezone
from toolchain import executable,repository_path,question_bank_path
import temporary_files
from material_folders import folder_kind,folder_patterns,ordered

CODES=['103','111','130','135','136','151','152','250','251']
def stamp():return datetime.now(timezone.utc).isoformat()
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace_file(source,destination):
 # Windows readers/antivirus can briefly hold a destination without delete sharing.
 for attempt in range(20):
  try:os.replace(source,destination);return
  except PermissionError:
   if attempt==19:raise
   time.sleep(.05)
def save(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf8');replace_file(tmp,p)
def term(tag):
 if not re.fullmatch(r'(fa|sp|su|wi)\d{2}',tag):raise ValueError('Select a valid semester.')
 return {'fa':'Fall','sp':'Spring','su':'Summer','wi':'Winter'}[tag[:2]]+' 20'+tag[2:]
def escape(s):return ''.join({'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}'}.get(c,c)for c in s)
def tex_input(value):
 if not isinstance(value,str)or len(value)>100000:raise ValueError('Keep question text under 100,000 characters.')
 if re.search(r'\\(?:documentclass|usepackage|input|include(?!graphics)|openout|openin|write|read|catcode|directlua|immediate|special|csname)\b|\\(?:begin|end)\{(?:document|exercise|solution)\}',value,re.I):raise ValueError('Enter question or solution content only, without document commands or file operations.')
 return value.strip()

class Desk:
 def __init__(self,root,repo=None):
  self.root=Path(root).resolve();self.temp=self.root/'Temp';self.data=self.root/'Data';self.repo=None;self.lock=threading.RLock();self.active=None;self.modules={}
  for folder in [self.temp/'Builds',self.temp/'Drafts',self.temp/'PreviewCache',self.data/'History']:folder.mkdir(parents=True,exist_ok=True)
  profile=self.data/'edition.json'
  self.edition=json.loads(profile.read_text(encoding='utf-8')) if profile.is_file() else {'edition':'authoring','label':'Personal Version','display_name':'G-Vault','theme':'blue','courses':CODES,'coordination':True}
  self.materials_enabled=self.edition.get('materials',self.edition.get('edition') not in ('records',))
  self.repo=repository_path(self.root,repo) if self.materials_enabled else self.root/'Data'
  instructor=self.edition.get('edition') in ('materials',)
  self.branding={'name':self.edition.get('display_name') or ('G-Whiz' if instructor else 'G-Vault'),'subtitle':self.edition.get('subtitle',''),'theme':'rutgers' if self.edition.get('theme','rutgers' if instructor else 'blue')=='rutgers' else 'blue'}
  for code in (CODES if self.materials_enabled else []):
   if code not in self.edition.get('courses',CODES):continue
   p=Path(__file__).resolve().parent/'course_adapters'/code/('compile_'+code+'.py')
   if not p.is_file() or not (self.repo/('mh-'+code+'-course-documents')).is_dir():continue
   spec=importlib.util.spec_from_file_location('course_adapter_'+code,p);m=importlib.util.module_from_spec(spec);m.MATERIALS_ROOT=self.repo;m.GWORKS_ROOT=self.root;spec.loader.exec_module(m);
   if self.settings().get('portable_output'):m.OUTPUT=(self.root/'Published'/str(m.CONFIG['course_directory']).replace('\\','/').rstrip('/').rsplit('/',1)[-1]).resolve()
   self.modules[code]=m
  if self.materials_enabled:
   import course_workspaces
   course_workspaces.load(self)
 def tool(self,name):return executable(self.root,name)
 def system_check(self):
  from private_module_ui import shared_tex
  engine='pdflatex' if self.edition.get('edition') in ('materials',) and shared_tex.selection(self.root)['tex_distribution']=='miktex' else 'latexmk'
  return {'app':self.branding['name'],'repository':str(self.repo),'tools':{name:self.tool(name) for name in [engine,'pdfinfo','pdftoppm']},'courses':len(self.modules)}
 def temp_files(self):
  return {**temporary_files.summary(self.root),'active':bool(self.active)}
 def clear_temp(self):
  with self.lock:
   if self.active:raise ValueError('Let the current compilation finish before clearing temporary files.')
   return {**temporary_files.clear(self.root),'active':False}
 def module(self,code):
  if code not in self.modules:raise ValueError('Select an installed course.')
  return self.modules[code]
 def default_root_pattern(self,code):
  return str(self.module(code).OUTPUT.parent/'[course]')
 def resolve_base(self,code,pattern):
  values={'course':self.module(code).OUTPUT.name,'course-code':str(code)}
  value=str(pattern).strip()
  if not value or len(value)>1000:raise ValueError('Enter a course base folder.')
  def replace(match):
   if match[1] not in values:raise ValueError('Course base folders support [course] and [course-code]. Use other placeholders in material patterns.')
   return values[match[1]]
  expanded=re.sub(r'\[([^\]]+)\]',replace,value)
  if '[' in expanded or ']' in expanded:raise ValueError('Check the brackets in the course base folder.')
  path=Path(expanded)
  if not path.is_absolute() or path.anchor==str(path):raise ValueError('Choose an absolute folder inside a drive.')
  if '..' in path.parts:raise ValueError('Use folder names rather than parent-directory steps.')
  if path.exists() and not path.is_dir():raise ValueError('Choose a folder, not a file.')
  return path.resolve()
 def output_root(self,code):
  values=self.settings()
  return self.resolve_base(code,values.get('publish_folders',{}).get(code) or self.default_root_pattern(code))
 def settings(self):
  path=self.data/'settings.json'
  return json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
 def material_category(self,kind):
  kind=str(kind).lower()
  if kind in ('exam','final','final exam','quiz','worksheet','groupwork'):return 'Handout'
  if kind in ('manual','assessment manual'):return 'Manual'
  if kind=='coordination':return 'Coordination'
  return 'Support'
 def material_defaults(self,code):
  if not hasattr(self,'_publish_defaults'):self._publish_defaults={}
  if code in self._publish_defaults:return self._publish_defaults[code]
  m=self.module(code);tag=m.CONFIG['default_semester']
  kinds=list(dict.fromkeys(['Exam','Final Exam','Quiz','Worksheet','Manual','Syllabus & Schedule','Support','Coordination']+[item['kind'] for item in m.discover(tag) if item['kind'] not in ('Syllabus','Schedule')]))
  if str(code)!='135' and (m.COURSE/'assessment-manual/assessment-manual.tex').is_file():kinds.append('Assessment manual')
  if str(code)=='135':kinds=[kind for kind in kinds if kind.lower()!='assessment manual']
  kinds=list(dict.fromkeys(folder_kind(code,kind) for kind in kinds if folder_kind(code,kind) is not None))
  rules={}
  for kind in kinds:
   category=self.material_category(kind)
   pattern='[root]' if category=='Manual' else '[root]/[semester]' if category=='Handout' or kind in ('Schedule','Syllabus','Syllabus & Schedule') else '[root]/Coordination' if category=='Coordination' else '[root]/Support'
   rules[kind]={'kind':kind,'category':category,'pattern':pattern.replace('/',os.sep)}
  rules=ordered(rules);self._publish_defaults[code]=rules
  return rules
 def publish_folder(self,code,tag,kind,number='',mode='student',version='A',patterns=None,root=None):
  term(tag);kind='Final Exam' if str(kind).lower()=='final' else kind;kind='Syllabus & Schedule' if str(kind).lower() in ('syllabus','schedule') else kind
  kind=folder_kind(code,kind)
  if kind is None:raise ValueError('This material type is not available for Math '+str(code)+'.')
  defaults=self.material_defaults(code);kind=next((k for k in defaults if k.lower()==str(kind).lower()),kind)
  values=self.settings();patterns=patterns if patterns is not None else values.get('publish_patterns',{}).get(code,{})
  patterns=folder_patterns(code,patterns)
  pattern=patterns.get(kind,patterns.get('Syllabus',patterns.get('Schedule',defaults.get(kind,{'pattern':'[root]/[semester]'})['pattern'])) if kind=='Syllabus & Schedule' else defaults.get(kind,{'pattern':'[root]/[semester]'})['pattern'])
  substitutions={'root':str(self.resolve_base(code,root) if root else self.output_root(code)),'course':self.module(code).OUTPUT.name,'course-code':str(code),'semester':self.module(code).semester_info(tag)[0],'semester-code':tag,'season':term(tag).split()[0],'year':term(tag).split()[-1],'type':str(kind),'number':str(number or ''),'mode':{'student':'Student','solutions':'Solutions','developer':'Developer'}.get(mode,mode),'version':str(version)}
  tokens=re.findall(r'\[([^\]]+)\]',pattern)
  if any(t not in substitutions for t in tokens):raise ValueError('Unknown folder placeholder. Use the placeholders listed in Configuration.')
  expanded=re.sub(r'\[([^\]]+)\]',lambda m:substitutions[m[1]],pattern)
  if '[' in expanded or ']' in expanded:raise ValueError('Check the brackets in the folder pattern.')
  path=Path(expanded)
  if not path.is_absolute() or path.anchor==str(path):raise ValueError('A publish pattern must resolve to an absolute folder inside a drive.')
  if '..' in path.parts:raise ValueError('Use folder names rather than parent-directory steps in a publish pattern.')
  if path.exists() and not path.is_dir():raise ValueError('The publish pattern points to a file, not a folder.')
  return path.resolve()
 def configuration(self):
  self._publish_defaults={}
  settings=self.settings();courses=[]
  for code in self.modules:
   if code=='136':continue
   defaults=self.material_defaults(code);custom=settings.get('publish_patterns',{}).get(code,{})
   custom=folder_patterns(code,custom)
   if 'Syllabus & Schedule' not in custom and ('Syllabus' in custom or 'Schedule' in custom):custom['Syllabus & Schedule']=custom.get('Syllabus',custom.get('Schedule'))
   rules=[{'kind':kind,'category':row['category'],'pattern':custom.get(kind,row['pattern']),'default_pattern':row['pattern'],'example':str(self.publish_folder(code,self.module(code).CONFIG['default_semester'],kind,1))} for kind,row in defaults.items()]
   courses.append({'code':code,'course_folder':self.module(code).OUTPUT.name,'folder':settings.get('publish_folders',{}).get(code) or self.default_root_pattern(code),'resolved_folder':str(self.output_root(code)),'default_folder':self.default_root_pattern(code),'rules':rules,'example_semester':self.module(code).CONFIG['default_semester'],'example_semester_label':self.module(code).semester_info(self.module(code).CONFIG['default_semester'])[0]})
  return {'courses':courses}
 def save_configuration(self,payload):
  with self.lock:
   if self.active:raise ValueError('Let the current compilation finish before changing publish folders.')
   values=payload.get('publish_folders');patterns=payload.get('publish_patterns',{})
   if not isinstance(values,dict) or not isinstance(patterns,dict):raise ValueError('Enter course publish folders and patterns.')
   folders={};validated={}
   for code,value in values.items():
    self.module(code)
    if not isinstance(value,str) or not value.strip():raise ValueError('Enter an absolute folder path for Math '+code+'.')
    self.resolve_base(code,value)
    folders[code]=value.strip()
   for code,rules in patterns.items():
    defaults=self.material_defaults(code)
    if not isinstance(rules,dict):raise ValueError('Check the material folder patterns.')
    rules=folder_patterns(code,rules)
    if 'Syllabus & Schedule' not in rules and ('Syllabus' in rules or 'Schedule' in rules):rules['Syllabus & Schedule']=rules.get('Syllabus',rules.get('Schedule'))
    rules.pop('Syllabus',None);rules.pop('Schedule',None)
    validated[code]={}
    for kind,pattern in rules.items():
     if kind not in defaults or not isinstance(pattern,str) or not pattern.strip() or len(pattern)>1000:raise ValueError('Enter a folder pattern for an available material type.')
     pattern=pattern.strip();self.publish_folder(code,self.module(code).CONFIG['default_semester'],kind,1,patterns={kind:pattern},root=folders.get(code) or self.output_root(code));validated[code][kind]=pattern
   path=self.data/'settings.json';old=self.settings()
   if path.is_file():self._history({path:path.read_bytes()},'Publish folder configuration changed')
   old['publish_folders']={**old.get('publish_folders',{}),**folders}
   old['publish_patterns']={**old.get('publish_patterns',{}),**validated};save(path,old)
   return self.configuration()
 def publish_locations(self,code,tag):
  contexts=[(kind,'',1) for kind in self.material_defaults(code)]
  contexts.extend((x['kind'],x.get('number',''),x.get('versions',1)) for x in self.module(code).discover(tag))
  for path in (question_bank_path(self.root,self.repo)/'assignments').glob('*.json'):
   a=json.loads(path.read_text(encoding='utf8'))
   if a.get('course')==code and a.get('semester')==tag:contexts.append((a['kind'].title(),a.get('number',''),a.get('versions',1)))
  return {self.publish_folder(code,tag,kind,n,mode,chr(65+i)) for kind,n,count in contexts for mode in ['student','solutions','developer'] for i in range(min(26,max(1,count)))}
 def source_path(self,code,relative):
  base=self.module(code).COURSE.resolve();p=(self.repo/relative).resolve()
  if not p.is_relative_to(base)or not p.is_file()or p.suffix.lower()!='.tex':raise ValueError('Choose a course source file.')
  for q in [p,*p.parents]:
   if q==self.repo:break
   if q.is_symlink()or getattr(q,'is_junction',lambda:False)():raise ValueError('Source files must not be external links.')
  return p
 def courses(self):
  return [{'code':code,'name':getattr(self.modules[code],'display_name',self.modules[code].OUTPUT.name),'default_semester':self.modules[code].CONFIG['default_semester']}for code in self.modules if code!='136']
 def catalog(self,code,tag=None):
  m=self.module(code);tag=tag or m.CONFIG['default_semester'];term(tag);items=m.discover(tag)
  secondary=m.COURSE/'assessment-manual/assessment-manual.tex'
  if str(code)!='135' and secondary.exists():items.append({'key':'assessment-manual','kind':'Assessment manual','source':secondary,'versions':1})
  if str(code)=='135':items=[item for item in items if item['key']!='assessment-manual' and item['kind'].lower()!='assessment manual']
  entries=[]
  for item in items:
   if not self.edition.get('coordination',True) and item['kind']=='Coordination':continue
   try:jobs=self.plan(code,tag,[item['key']],items=items)
   except (ValueError,FileNotFoundError):continue
   if not jobs:continue
   entries.append({'key':item['key'],'kind':item['kind'],'category':self.material_category(item['kind']),'label':item.get('label')or(item['kind']+' '+str(item['number'])if'number'in item else item['kind']),'versions':item['versions'],'source_files':sorted({j['source'].relative_to(self.repo).as_posix()for j in jobs}),'outputs':[{'name':j['name']+'.pdf','mode':j['mode'],'version':j['version'],'published':(j['folder']/(j['name']+'.pdf')).is_file()}for j in jobs]})
  tags={tag,m.CONFIG['default_semester']}
  for p in m.COURSE.rglob('*.tex'):tags.update(re.findall(r'(?:^|[-/])((?:fa|sp|su|wi)\d{2})(?=[-.]|$)',p.name.lower()))
  return {'course':code,'semester':tag,'semester_label':term(tag),'semesters':[{'value':t,'label':term(t)}for t in sorted(tags,key=lambda t:(t[2:],{'wi':0,'sp':1,'su':2,'fa':3}[t[:2]]),reverse=True)],'documents':entries,'output_folder':str(self.output_root(code)),'source_folder':str(m.COURSE)}
 def plan(self,code,tag,keys,mode='all',version='all',items=None):
  m=self.module(code);term(tag)
  if mode not in ('all','student','solutions')or version not in ['all']+list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):raise ValueError('Choose an output and version.')
  items=items if items is not None else m.discover(tag)
  if str(code)!='135' and (m.COURSE/'assessment-manual/assessment-manual.tex').is_file()and not any(x['key']=='assessment-manual'for x in items):items.append({'key':'assessment-manual','kind':'Assessment manual','source':m.COURSE/'assessment-manual/assessment-manual.tex','versions':1})
  if str(code)=='135':items=[item for item in items if item['key']!='assessment-manual' and item['kind'].lower()!='assessment manual']
  by={x['key']:x for x in items};jobs=[]
  if not isinstance(keys,list)or not keys or len(keys)>100:raise ValueError('Select documents to compile.')
  for key in dict.fromkeys(keys):
   if key not in by:raise ValueError('Refresh the library; a selected document is unavailable.')
   item=by[key]
   if not self.edition.get('coordination',True) and item['kind']=='Coordination':raise ValueError('Coordination materials are not included in this edition.')
   if key=='assessment-manual':
    for md in ['student','solutions']:
     if mode!='all'and mode!=md:continue
     jobs.append({'name':'Assessment-Manual-'+code+('-Sols'if md=='solutions'else''),'source':item['source'],'prefix':'\\def\\AssessmentStudent{1}\n'if md=='student'else'','folder':m.OUTPUT,'kind':'Assessment manual','mode':md,'version':'A'})
   else:
    selected_version=version if item.get('versions',1)>1 else'all'
    planned=m.plan([item],tag,mode,selected_version)
    for job in planned:job['publish_number']=item.get('number','')
    jobs.extend(planned)
  for j in jobs:
   self.source_path(code,j['source'].relative_to(self.repo).as_posix())
   if not j['folder'].resolve().is_relative_to(m.OUTPUT.resolve()):raise ValueError('The output folder is outside this course.')
   j['folder']=self.publish_folder(code,tag,j['kind'],j.get('publish_number',''),j['mode'],j['version'])
  if len({str(j['folder']/j['name'])for j in jobs})!=len(jobs):raise ValueError('Two selected outputs have the same filename.')
  return jobs
 def fingerprint(self,code):
  h=hashlib.sha256();folders=[self.module(code).COURSE,self.repo/'lib',self.repo/'img',self.repo/'semesters',self.repo/'standards',question_bank_path(self.root,self.repo)]
  for folder in folders:
   for p in sorted(folder.rglob('*')):
    if p.is_file()and p.suffix.lower()in('.tex','.sty','.cls','.pdf','.png','.jpg','.jpeg','.eps','.json'):
     relative=p.relative_to(self.repo).as_posix() if p.is_relative_to(self.repo) else 'exercise-bank/'+p.relative_to(question_bank_path(self.root,self.repo)).as_posix()
     h.update(relative.encode());h.update(p.read_bytes())
  return h.hexdigest()
 def _job_fingerprint(self,code,jobs,version=1):
  if version!=1:return self._legacy_job_fingerprint(code,jobs)

  snapshots=bool(jobs) and all(j.get('universal') or j.get('syllabus_builder') or j.get('preview_only') for j in jobs)
  if not snapshots:return self.fingerprint(code)
  # Generated TeX is an immutable copy of the selected question revisions.
  # Unrelated revisions/assignments in the full bank are not build inputs.
  h=hashlib.sha256();paths=set()
  folders=[self.repo/'lib',self.repo/'img',self.repo/'semesters',self.repo/'standards',self.module(code).COURSE]
  for folder in folders:
   if folder.exists():
    paths.update(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.tex','.sty','.cls','.pdf','.png','.jpg','.jpeg','.eps'))
  bank=question_bank_path(self.root,self.repo)
  if bank.exists():
   for p in bank.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(bank);ext=p.suffix.lower()
    if ext in ('.pdf','.png','.jpg','.jpeg','.eps','.csv','.tsv','.dat','.bib','.sty','.cls') or (ext in ('.tex','.json') and rel.parts[0] not in ('questions','revisions','assignments','Build History','Backups') and p.name!='catalog.json'):paths.add(p)
  paths.add(self.repo/'latexmkrc')
  for j in jobs:
   source=Path(j['source']);paths.add(source)
   paths.update(p for p in source.parent.glob('*.tex') if p.is_file())
  for p in sorted(paths):
   h.update(str(p).encode());h.update(p.read_bytes() if p.exists() else b'<missing>')
  return h.hexdigest()
 def _legacy_job_fingerprint(self,code,jobs):
  if not jobs or not all(j.get('syllabus_builder')for j in jobs):return self.fingerprint(code)
  # Builder sources are self-contained snapshots; unrelated bank revisions are not inputs.
  h=hashlib.sha256()
  for folder in [self.repo/'lib',self.repo/'img',self.repo/'semesters']:
   for p in sorted(folder.rglob('*')):
    if p.is_file()and p.suffix.lower()in('.tex','.sty','.cls','.pdf','.png','.jpg','.jpeg','.eps'):
     h.update(str(p).encode());h.update(p.read_bytes())
  for j in jobs:
   p=Path(j['source']);h.update(str(p).encode());h.update(p.read_bytes())
  return h.hexdigest()
 def _batch_path(self,identity):
  if not re.fullmatch('[a-f0-9]{16}',identity):raise ValueError('Choose a saved build.')
  p=self.temp/'Builds'/identity/'result.json'
  if not p.is_file():raise ValueError('That build is unavailable.')
  return p
 def batch(self,identity):return json.loads(self._batch_path(identity).read_text(encoding='utf8'))
 def history(self):
  rows=[]
  for p in (self.temp/'Builds').glob('*/result.json'):
   b=json.loads(p.read_text(encoding='utf8'));rows.append({k:b.get(k)for k in ['id','course','semester','created','status','published','title']})
  return sorted(rows,key=lambda x:x['created'],reverse=True)[:60]
 def start(self,code,tag,keys,mode='all',version='all',custom=None,publish_when_ready=False):
  with self.lock:
   if self.active:raise ValueError('A compile is already running. Let it finish before starting another.')
   jobs=custom if custom is not None else self.plan(code,tag,keys,mode,version)
   if not jobs:raise ValueError('No outputs match that selection.')
   identity=secrets.token_hex(8);folder=self.temp/'Builds'/identity;folder.mkdir();fingerprint=None
   b={'fingerprintVersion':1,'publish_when_ready':publish_when_ready,'id':identity,'course':code,'semester':tag,'created':stamp(),'status':'queued','published':False,'title':'Support document preview'if custom and all(j.get('support_preview')for j in jobs) else 'Question preview'if custom and all(j.get('preview_only')for j in jobs) else str(len(jobs))+' PDF'+('s'if len(jobs)!=1 else''),'source_fingerprint':fingerprint,'jobs':[{**j,'source':str(j['source']),'folder':str(j['folder']),'status':'queued'}for j in jobs]};save(folder/'result.json',b);self.active=identity
   threading.Thread(target=self._work,args=(identity,),daemon=True).start();return b
 def _work(self,identity):
  b=None
  try:
   b=self.batch(identity)
   b['status']='running';b['phase']='fingerprint';b['message']='Checking selected build inputs…';save(self._batch_path(identity),b)
   began=time.monotonic();b['source_fingerprint']=self._job_fingerprint(b['course'],b['jobs'],version=b.get('fingerprintVersion'));b.setdefault('timings',{})['input_check_seconds']=round(time.monotonic()-began,3)
   b['phase']='compile';b['message']='Compiling selected PDFs…';save(self._batch_path(identity),b)
   from private_module_ui import shared_tex
   miktex=self.edition.get('edition') in ('materials',) and shared_tex.selection(self.root)['tex_distribution']=='miktex'
   latexmk=executable(self.root,'pdflatex' if miktex else 'latexmk')
   if not Path(latexmk).is_file():raise ValueError('The TeX compiler is unavailable.')
   env=os.environ.copy();env['PATH']=str(Path(latexmk).parent)+os.pathsep+env.get('PATH','');env['TEXINPUTS']=(self.repo/'lib').as_posix()+'//'+os.pathsep+env.get('TEXINPUTS','')+os.pathsep;cache=self.temp/'Builds/tex-cache';cache.mkdir(exist_ok=True);env['TEXMFVAR']=str(cache);env['TEXMFCACHE']=str(cache)
   for i,j in enumerate(b['jobs']):
    j['status']='running';save(self._batch_path(identity),b);work=self.temp/'Builds'/identity/str(i);work.mkdir();source=Path(j['source']);wrapper=work/'document.tex';body=source.read_text(encoding='utf8')
    if j['mode']=='solutions'and re.search(r'\\documentclass\[[^\]]*\bstudent\b',body)and 'CourseOutputMode'not in body and 'Solutions'not in body.split('\\documentclass',1)[0]:
     body=re.sub(r'(\\documentclass\[[^\]]*)\bstudent\b',r'\1solutions',body,count=1);wrapper.write_text(j['prefix']+body,encoding='utf8')
    else:wrapper.write_text(j['prefix']+'\\input{'+(source.relative_to(self.repo).as_posix()if source.is_relative_to(self.repo)else source.as_posix())+'}\n',encoding='utf8')
    cmd=([sys.executable,'-I','-B',str(Path(__file__).with_name('tex_compile.py')),'--compiler',latexmk,'--source',str(wrapper),'--output',str(work)] if miktex else [latexmk,'-norc','-r','latexmkrc','-pdf','-interaction=nonstopmode','-halt-on-error','-file-line-error','-latexoption=-no-shell-escape','-outdir='+str(work),str(wrapper)]);began=time.monotonic()
    try:
     result=subprocess.run(cmd,cwd=self.repo,env=env,capture_output=True,text=True,errors='replace',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));console=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as exc:console='Compilation exceeded five minutes. Review this document separately.';code=124
    (work/'console.txt').write_text(console,encoding='utf8');log=(work/'document.log').read_text(encoding='utf8',errors='replace')if(work/'document.log').is_file()else'';pdf=work/'document.pdf';unresolved=bool(re.search('There were undefined references|There were undefined citations',log));ok=code==0 and pdf.is_file()and not unresolved
    j.update(status='ready'if ok else'failed',seconds=round(time.monotonic()-began,1),message='PDF ready to review'if ok else'Unresolved references'if unresolved else self._error(console),warnings=re.findall(r'(?:LaTeX|Package [^\n]+) Warning:[^\n]*',log)[:12],pages=self._pages(pdf)if ok else 0)
    if ok:j['pdf_sha256']=hash_file(pdf)
    save(self._batch_path(identity),b)
   b['phase']='verify';b['message']='Verifying compiled inputs…';save(self._batch_path(identity),b)
   b['status']='ready'if all(j['status']=='ready'for j in b['jobs'])else'failed'
   if self._job_fingerprint(b['course'],b['jobs'],version=b.get('fingerprintVersion'))!=b['source_fingerprint']:b['status']='stale';b['message']='Course sources changed during compilation. Compile again before publishing.'
   b['phase']='complete';b['message']='PDFs ready to review.' if b['status']=='ready' else b.get('message','Compilation needs review.')
   if b['status']=='ready' and b.get('publish_when_ready'):
    save(self._batch_path(identity),b);b=self.publish(identity)
  except Exception as exc:
   if b is None:raise
   b.update(status='failed',message=str(exc)[:500])
  finally:
   try:
    if b is not None:save(self._batch_path(identity),b)
   finally:
    with self.lock:self.active=None
 def _error(self,text):
  lines=[l for l in text.splitlines()if re.search(r'^!|LaTeX Error|Package .+ Error|Fatal error|\.tex:\d+:',l)]
  return '\n'.join(lines[-5:])or'Compilation did not finish. Open the build log for details.'
 def _pages(self,pdf):
  exe=executable(self.root,'pdfinfo')
  try:
   r=subprocess.run([exe,str(pdf)],capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));m=re.search(r'Pages:\s+(\d+)',r.stdout);return int(m[1])if m else 1
  except Exception:return 1
 def artifact(self,identity,index,kind='pdf',page=1):
  b=self.batch(identity);index=int(index)
  if not 0<=index<len(b['jobs']):raise ValueError('Choose an output in this build.')
  work=self.temp/'Builds'/identity/str(index);j=b['jobs'][index]
  if kind=='log':return work/'console.txt'
  if j['status']!='ready':raise ValueError('This PDF is not ready.')
  if kind=='pdf':return work/'document.pdf'
  page=int(page)
  if not 1<=page<=j.get('pages',1):raise ValueError('Choose a valid preview page.')
  target=work/('page-'+str(page)+'.png')
  if not target.is_file():
   exe=executable(self.root,'pdftoppm');subprocess.run([exe,'-f',str(page),'-l',str(page),'-scale-to','1500','-singlefile','-png',str(work/'document.pdf'),str(target.with_suffix(''))],check=True,capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  return target
 def publish(self,identity):
  with self.lock:
   b=self.batch(identity)
   if b['status']!='ready':raise ValueError('All selected PDFs must compile successfully before publishing.')
   if any(j.get('preview_only')for j in b['jobs']):raise ValueError('Question previews are not course documents.')
   if self._job_fingerprint(b['course'],b['jobs'],version=b.get('fingerprintVersion'))!=b['source_fingerprint']:raise ValueError('The sources changed. Compile again before publishing.')
   backups={};prepared=[]
   for i,j in enumerate(b['jobs']):
    source=self.artifact(identity,i);destination=Path(j['folder'])/(j['name']+'.pdf');base=self.publish_folder(b['course'],b['semester'],j['kind'],j.get('publish_number',''),j['mode'],j['version'])
    if destination.parent.resolve()!=base:raise ValueError('Publish settings changed. Compile again to use the current destination.')
    if hash_file(source)!=j['pdf_sha256']:raise ValueError('The preview changed. Compile again.')
    if destination.exists()and hash_file(destination)!=hash_file(source):backups[destination]=destination.read_bytes()
    prepared.append((source,destination))
   if backups:self._history(backups,'Published PDFs replaced after preview')
   originals={destination:destination.read_bytes()if destination.exists()else None for source,destination in prepared}
   try:
    for source,destination in prepared:
     destination.parent.mkdir(parents=True,exist_ok=True);tmp=destination.with_suffix('.pdf.partial');shutil.copy2(source,tmp);replace_file(tmp,destination)
   except Exception:
    for destination,content in originals.items():
     if content is None:destination.unlink(missing_ok=True)
     else:destination.write_bytes(content)
    raise
   b.update(published=True,published_at=stamp());save(self._batch_path(identity),b);return b
 def _history(self,files,reason):
  identity=secrets.token_hex(8);p=self.data/'History'/(identity+'.zip')
  with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED)as z:
   manifest=[]
   for n,(path,data)in enumerate(files.items()):
    name=str(n)+'-'+Path(path).name;z.writestr(name,data);manifest.append({'original_path':str(path),'entry':name,'sha256':hashlib.sha256(data).hexdigest()})
   z.writestr('Manifest.json',json.dumps({'reason':reason,'at':stamp(),'files':manifest},indent=2))
  return p
 def banks(self,code):
  m=self.module(code);result=[]
  for collection,folder in [('manual',m.COURSE/'manual/exercises'),('assessment',m.COURSE/('assessment-bank' if str(code)=='135' else 'assessment-manual')/'exercises')]:
   for p in sorted(folder.glob('*.tex')):
    text=p.read_text(encoding='utf8');questions=self._questions(text);relative=p.relative_to(self.repo).as_posix();result.append({'path':relative,'name':p.stem.replace('-',' ').title(),'collection':collection,'count':len(questions),'sha256':hash_file(p),'next_id':self._next_id(code,p,questions),'questions':[{**q,'bank':relative,'collection':collection}for q in questions]})
  return result
 def _questions(self,text):
  result=[]
  for m in re.finditer(r'\\begin\{exercise\}\s*(?:\[([\s\S]*?)\])?([\s\S]*?)\\end\{exercise\}(?:\s*\\begin\{solution\}([\s\S]*?)\\end\{solution\})?',text):
   meta=m[1]or'';ident=re.search(r'\bID\s*=\s*\{?([A-Za-z0-9-]+)',meta)
   if not ident:continue
   topic=re.search(r'topics\s*=\s*\{([^}]*)\}',meta);body=m[2].strip();result.append({'id':ident[1],'question':body,'solution':(m[3]or'').strip(),'topics':topic[1]if topic else'','excerpt':re.sub(r'\s+',' ',body)[:180]})
  return result
 def _next_id(self,code,path,questions):
  assessment='assessment-bank' if str(code)=='135' else 'assessment-manual'
  allids={q['id']for folder in ['manual/exercises',assessment+'/exercises']for p in (self.module(code).COURSE/folder).glob('*.tex')for q in self._questions(p.read_text(encoding='utf8'))}
  if assessment in path.parts:
   p=self.repo/'_local/metadata'/('mh-'+code+'-course-documents')/assessment/'assessment-index.json';index=json.loads(p.read_text())if p.is_file()else{};n=max([int(q.split('-')[-1])for q in allids if re.fullmatch('A'+code+r'-\d+',q)]+[0])+1;n=max(n,int(index.get('next_ID','A'+code+'-0001').split('-')[-1]));return 'A'+code+'-'+str(n).zfill(4)
  width=2
  if questions:
   ident=questions[0]['id'];standard=re.fullmatch(r'(M'+code+r'-\d{2})(\d{2})',ident);m=standard or re.match(r'(.+?)(\d+)$',ident)
   if m:
    prefix=m[1];width=len(m[2]);numbers=[int(q[len(prefix):])for q in allids if q.startswith(prefix)and q[len(prefix):].isdigit()];n=max(numbers+[0])+1
   else:prefix='M'+code+'-NEW';n=1
  else:
   group=re.search(r'(\d{2})$',path.stem);prefix='M'+code+'-'+(group[1]if group else'NEW');n=1
  while prefix+str(n).zfill(width)in allids:n+=1
  if width==2 and re.fullmatch(r'M'+code+r'-\d{2}',prefix)and n>99:return None
  return prefix+str(n).zfill(width)
 def add_question(self,code,payload):
  with self.lock:
   if self.active:raise ValueError('Let the current compile finish before editing a question bank.')
   banks=self.banks(code);bank=next((b for b in banks if b['path']==payload.get('bank')),None)
   if not bank:raise ValueError('Choose an existing exercise group.')
   p=self.source_path(code,bank['path'])
   if payload.get('sha256')!=bank['sha256']:raise ValueError('The exercise group changed. Refresh it before saving.')
   ident=bank['next_id'];question=tex_input(payload.get('question',''));solution=tex_input(payload.get('solution',''));topics=payload.get('topics','').strip()
   if ident is None:raise ValueError('This exercise group has no unused two-digit IDs. Choose another group.')
   if not question:raise ValueError('Enter the question.')
   if topics and not re.fullmatch(r'[a-z0-9-]+(?:\s*,\s*[a-z0-9-]+)*',topics):raise ValueError('Use topic codes separated by commas.')
   block='\n\n% Added through G-Whiz; permanent ID '+ident+'\n\\begin{exercise}[ID={'+ident+'},status=draft'+(',topics={'+topics+'}'if topics else'')+']\n'+question+'\n\\end{exercise}\n'+('\\begin{solution}\n'+solution+'\n\\end{solution}\n'if solution else'')
   changes={p:p.read_bytes()+block.encode()}
   if bank['collection']=='assessment':
    if str(code)!='135':
     wrapper=self.module(code).COURSE/'assessment-manual/assessment-manual.tex';body=wrapper.read_text(encoding='utf8');addition='\n\\par\\medskip\\noindent\\textbf{Permanent ID: \\texttt{'+ident+'}}\\par\n\\UseAssessmentExercise{'+ident+'}\n';changes[wrapper]=body.replace('\\end{document}',addition+'\\end{document}').encode()
    idx=self.repo/'_local/metadata'/('mh-'+code+'-course-documents')/('assessment-bank' if str(code)=='135' else 'assessment-manual')/'assessment-index.json'
    if idx.is_file():
     data=json.loads(idx.read_text());data['exercises'].append({'permanent_ID':ident,'original_assessment':'G-Whiz addition','question_number':None,'previous_local_ID':'','question_and_solution_sha256':hashlib.sha256(block.encode()).hexdigest(),'has_solution':bool(solution),'has_variants':False});data['next_ID']='A'+code+'-'+str(int(ident.split('-')[-1])+1).zfill(4);changes[idx]=json.dumps(data,indent=2).encode()
     csvpath=idx.with_suffix('.csv')
     if csvpath.exists():
      stream=io.StringIO(newline='');fields=['permanent_ID','original_assessment','question_number','previous_local_ID','question_and_solution_sha256','has_solution','has_variants'];writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(data['exercises']);changes[csvpath]=stream.getvalue().encode()
   old={path:path.read_bytes()for path in changes};history=self._history(old,'Question '+ident+' added')
   try:
    for path,content in changes.items():tmp=path.with_suffix(path.suffix+'.partial');tmp.write_bytes(content);os.replace(tmp,path)
   except Exception:
    for path,content in old.items():path.write_bytes(content)
    raise
   return {'id':ident,'bank':bank['path'],'history':history.name}
 def assembly(self,code,tag,kind,number,ids,instructions='',versions=1):
  m=self.module(code);term(tag)
  if kind not in ('Quiz','Worksheet')or not isinstance(number,int)or not 1<=number<=99:raise ValueError('Choose a quiz or worksheet number from 1 to 99.')
  if not isinstance(versions,int)or not 1<=versions<=26:raise ValueError('Choose between 1 and 26 student versions.')
  if not isinstance(ids,list)or len(ids)>100:raise ValueError('Choose up to 100 questions.')
  library=[q for bank in self.banks(code)for q in bank['questions']];selected=[]
  for ident in ids:
   found=[q for q in library if q['id']==ident]
   if len(found)!=1:raise ValueError('Question '+str(ident)+' is missing or has a duplicate ID.')
   selected.append(found[0])
  files=list(dict.fromkeys(q['bank']for q in selected));title=kind+' '+str(number);text=r'''% Created with G-Whiz. Questions remain linked to their banks.
% This single source contains all student versions. Solutions always use A.
\PassOptionsToPackage{use-files}{xsim}
\ifdefined\AssessmentSolutions\def\CourseOutputMode{solutions}\fi
\providecommand{\CourseOutputMode}{student}
\providecommand{\AssessmentBuildVersion}{A}
\def\CompilerSolutions{solutions}
\ifx\CourseOutputMode\CompilerSolutions
  \def\AssessmentBuildVersion{A}
  \documentclass[assessment,solutions]{mhdocument}
\else
  \documentclass[assessment,student]{mhdocument}
\fi
'''
  text+='\\usepackage{mh-'+code+'-objectives}\n\\usepackage{needspace,framed}\n\\usetikzlibrary{patterns}\n\\usepgfplotslibrary{fillbetween}\n\\SetCourseworkNumber{'+str(number)+'}\n\\SetExamVersions{'+str(versions)+'}\n\\expandafter\\SetExamVersion\\expandafter{\\AssessmentBuildVersion}\n\\SetMathLeftHeader{Math '+code+' (01:640:'+code+')}\n\\SetMathCenterHeader{'+title+(r' (Version \ExamVersion)'if versions>1 else'')+r' \IfMathSolutionsT{(Solutions)}}'+'\n\\SetMathRightHeader{'+term(tag)+'}\n'
  text+=r'''
\ExplSyntaxOn
\NewDocumentCommand{\CompilerUseQuestion}{m}{
 \tl_set:Nx \l_tmpa_tl {\GetExerciseIdForProperty{ID}{#1}}
 \exp_args:NnV \ExerciseSetProperty {exercise}\l_tmpa_tl {use}{true}
 \printexercise{exercise}{#1}
 \IfMathSolutionsT{\printsolution{exercise}{#1}}
}
\ExplSyntaxOff
\begin{document}
\noindent Name: \hrulefill\par\medskip
'''
  if instructions:text+='\\noindent '+tex_input(instructions)+'\\par\\medskip\n'
  text+='\\begingroup\n\\ForEachUsedExerciseByID{\\ExerciseSetProperty{#1}{#2}{use}{false}}\n\\xsimsetup{exercise/use=false,exercise/print=false,solution/print=false}\n'+''.join('\\input{'+p+'}\n'for p in files)+'\\endgroup\n'+''.join('\\CompilerUseQuestion{'+q['id']+'}\n'for q in selected)
  if not selected:text+='% Add questions using the Question library.\n'
  text+='\\end{document}\n';path=m.COURSE/('quizzes'if kind=='Quiz'else'worksheets')/(kind.lower()+str(number)+'-'+tag+'.tex');return path,text
 def create_document(self,code,payload):
  with self.lock:
   if self.active:raise ValueError('Let the current compile finish before creating a document.')
   p,text=self.assembly(code,payload['semester'],payload['kind'],payload['number'],payload.get('ids',[]),payload.get('instructions',''),payload.get('versions',1))
   if p.exists():raise ValueError('That document already exists. Choose another number.')
   p.parent.mkdir(parents=True,exist_ok=True)
   with p.open('x',encoding='utf8')as f:f.write(text)
   save(self.data/'History'/('created-'+secrets.token_hex(8)+'.json'),{'path':str(p),'sha256':hash_file(p),'created':stamp()});return {'path':str(p),'key':payload['kind'].lower()+':'+str(payload['number'])}
 def preview_question(self,code,payload):
  question=tex_input(payload.get('question',''));solution=tex_input(payload.get('solution',''))
  if not question:raise ValueError('Choose or enter a question to preview.')
  self.module(code)
  packages=['mh-'+code+'-'+kind for kind in ('topics','objectives') if (self.repo/'lib'/('mh-'+code)/('mh-'+code+'-'+kind+'.sty')).is_file()]
  preamble=''.join('\\usepackage{'+package+'}\n' for package in packages)
  p=self.temp/'Drafts'/('question-'+secrets.token_hex(8)+'.tex');text='\\documentclass[manual,solutions]{mhdocument}\n'+preamble+'\\usepackage{needspace,framed}\n\\usetikzlibrary{patterns}\n\\usepgfplotslibrary{fillbetween}\n\\SetMathLeftHeader{Math '+code+'}\n\\SetMathCenterHeader{Question preview}\n\\SetMathRightHeader{Draft}\n\\begin{document}\n\\begin{exercise}[ID={Preview-0001},status=draft]\n'+question+'\n\\end{exercise}\n'+('\\begin{solution}\n'+solution+'\n\\end{solution}\n'if solution else'')+'\\end{document}\n';p.write_text(text,encoding='utf8');return self.start(code,self.module(code).CONFIG['default_semester'],[],custom=[{'name':'Question-preview','source':p,'prefix':'','folder':self.temp/'Drafts','kind':'Question preview','mode':'solutions','version':'A','preview_only':True}])
