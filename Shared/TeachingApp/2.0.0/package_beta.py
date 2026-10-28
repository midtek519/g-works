"""Create clean, independent G-Whiz beta folders from the local authoring copy."""
from pathlib import Path
from copy import deepcopy
import argparse,json,os,re,secrets,shutil,sys,zipfile,subprocess
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parent))
from package_layout import profile_path, prepare_layout, instructor_folder
from distribution_policy import prune_folder, omission_reason
from toolchain import question_bank_path

def copy_file(source,destination,link=False):
 destination.parent.mkdir(parents=True,exist_ok=True)
 if link:
  try:os.link(source,destination);return str(destination)
  except OSError:pass
 return shutil.copy2(source,destination)

def tree(source,destination,link=False,exclude=()):
 if not source.is_dir():return
 for p in source.rglob('*'):
  rel=p.relative_to(source)
  if any(part in exclude or part=='__pycache__' for part in rel.parts) or p.suffix=='.pyc':continue
  if p.is_file():copy_file(p,destination/rel,link)

def course_question(q,code):
 source=q.get('source',{})
 return code in q.get('suitability',{}) or code in q.get('classifications',{}) or code in q.get('manual',{}) or (source.get('course') if isinstance(source,dict) else q.get('course',q.get('original_course')))==code

def bank_export(source,destination,code=None):
 cat=json.loads((source/'catalog.json').read_text(encoding='utf-8'))
 if code:
  cat=deepcopy(cat);cat['questions']=[q for q in cat['questions'] if course_question(q,code)];cat['archived_questions']=[q for q in cat.get('archived_questions',[]) if course_question(q,code)]
  selected=cat['questions']+cat['archived_questions'];ids={q['id'] for q in selected}
  for q in selected:
   for field in ('suitability','classifications','manual'):
    if isinstance(q.get(field),dict):q[field]={k:v for k,v in q[field].items() if k==code}
  topic_ids={x for q in selected for x in q.get('topics',[])};objective_ids={x for q in selected for x in q.get('objectives',[])}
  for folder in [source/'revisions'/ident for ident in ids]:
   for p in folder.glob('*.tex'):
    text=p.read_text(encoding='utf-8')
    for name,values in [('topics',topic_ids),('objectives',objective_ids)]:
     for match in re.findall(name+r'=\{([^}]+)\}',text):values.update(x.strip() for x in match.split(','))
  for field,wanted in [('topics',topic_ids),('archive_topics',topic_ids),('objectives',objective_ids),('archive_objectives',objective_ids)]:
   cat[field]=[x for x in cat.get(field,[]) if x['id'] in wanted]
   for item in cat[field]:
    for key in ('courses','course_details','course_labels'):
     if isinstance(item.get(key),dict):item[key]={k:v for k,v in item[key].items() if k==code}
    if isinstance(item.get('legacy_ids'),list):item['legacy_ids']=[x for x in item['legacy_ids'] if x.get('course')==code]
  cat['manuals']={code:cat.get('manuals',{}).get(code,{})}
  courses=cat.get('courses',{});cat['courses']={code:courses[code]} if isinstance(courses,dict) and code in courses else [x for x in courses if isinstance(x,dict) and x.get('code')==code] if isinstance(courses,list) else {}
  cat['archived_supplements']=[q for q in cat.get('archived_supplements',[]) if course_question(q,code)]
  cat['archive_categories']=sorted({q['archive_category'] for q in cat.get('archived_questions',[])+cat['archived_supplements'] if q.get('archive_category')})
  for field in ['import_issues','source_to_question','migration_audit','taxonomy_review_decisions','review_todos','merged_questions']:cat.pop(field,None)
  cat['summary']={'questions':len(cat['questions']),'edition':'Math 135 Instructor'}
 else:ids={q['id'] for q in cat['questions']+cat.get('archived_questions',[])}
 destination.mkdir(parents=True,exist_ok=True);(destination/'catalog.json').write_text(json.dumps(cat,indent=2,ensure_ascii=False),encoding='utf-8')
 for ident in ids:
  tree(source/'revisions'/ident,destination/'revisions'/ident)
 for q in cat['questions']+cat.get('archived_questions',[]):
  path=q.get('file')
  if path and (source/path).is_file():copy_file(source/path,destination/path)
 if code:
  selected_text='\n'.join(json.dumps(q,ensure_ascii=False) for q in cat['questions']+cat.get('archived_questions',[]))
  cat['assets']={k:v for k,v in cat.get('assets',{}).items() if k.startswith('mh-'+code+'-') or v.get('file','never-matches') in selected_text}
  for asset in cat['assets'].values():copy_file(source/asset['file'],destination/asset['file'])
  (destination/'catalog.json').write_text(json.dumps(cat,indent=2,ensure_ascii=False),encoding='utf-8')
 else:tree(source/'assets',destination/'assets')
 for p in (source/'assignments').glob('*.json'):
  a=json.loads(p.read_text(encoding='utf-8'))
  if not code or a.get('course')==code:copy_file(p,destination/'assignments'/p.name)
 for name in ('topics','objectives'):(destination/(name+'.json')).write_text(json.dumps(cat[name],indent=2,ensure_ascii=False),encoding='utf-8')
 (destination/'topics.tex').write_text('\n'.join('\\DeclareMathTopic{'+t['id']+'}{title={'+t['label']+'},section={}}' for t in cat['topics'])+'\n',encoding='utf-8')
 (destination/'objectives.tex').write_text('\n'.join('\\DeclareMathObjective{'+o['id']+'}{description={'+o['description']+'}}' for o in cat['objectives'])+'\n',encoding='utf-8')
 if not code:tree(source/'archive',destination/'archive')
 elif (source/'archive').is_dir():
  for p in (source/'archive').rglob('*'):
   if p.is_file() and any(ident in p.as_posix() for ident in ids):copy_file(p,destination/'archive'/p.relative_to(source/'archive'))
  out=destination/'archive/catalog.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps({k:cat.get(v,[]) for k,v in [('questions','archived_questions'),('categories','archive_categories'),('topics','archive_topics'),('objectives','archive_objectives'),('supplements','archived_supplements')]},ensure_ascii=False),encoding='utf-8')
 return cat

def build(root,destination,edition='135',link_dependencies=True,windows=True,bundle_tex=False):
 root=root.resolve();destination=destination.resolve()
 if not windows:raise ValueError('G-Works supports the Windows desktop edition.')
 nested_instructor=destination.parent==root and destination.name=='G-Whiz-Instructor-Version'
 if destination==root or root.is_relative_to(destination) or (destination.is_relative_to(root) and not nested_instructor):raise ValueError('Choose a separate package folder or a named instructor package directly inside G-Whiz.')
 if destination.is_symlink() or getattr(destination,'is_junction',lambda:False)():raise ValueError('Choose a normal folder, not a link.')
 if destination.exists():
  marker=profile_path(destination)
  if not marker.is_file() or json.loads(marker.read_text()).get('edition') not in ('math135-instructor','full-beta'):raise ValueError('Destination is not a generated beta folder.')
 stage=root/'Temp/Packages'/(destination.name+'.building-'+secrets.token_hex(4));stage.mkdir(parents=True)
 try:
  tree(root/'App',stage/'App',exclude=('Tests','course_adapters','node_modules'))
  if edition=='135':
   tree(root/'App/course_adapters/135',stage/'App/course_adapters/135')
  else:tree(root/'App/course_adapters',stage/'App/course_adapters')
  tree(root/'Dependencies',stage/'Dependencies',link=link_dependencies,exclude=('DesktopPrototype',)+(() if bundle_tex else ('texlive',)))
  repo=root/'mh-git';out=stage/'mh-git'
  for name in ['lib','img','semesters','standards']:
   unwanted=tuple(p.name for p in (repo/'lib').glob('mh-*') if p.is_dir() and p.name!='mh-135') if edition=='135' and name=='lib' else ()
   tree(repo/name,out/name,exclude=('signature.png','pdf-snapshots')+unwanted)
  course_dirs=[repo/'mh-135-course-documents'] if edition=='135' else sorted(repo.glob('mh-*-course-documents'))
  for folder in course_dirs:
   tree(folder,out/folder.name,exclude=('pdf-snapshots','coordination') if edition=='135' else ('pdf-snapshots',))
  if edition=='135':
   for name in ('first-recitation','first-recitation-mod','mylab-stu'):
    p=repo/'mh-135-course-documents/coordination'/(name+'.tex')
    if p.is_file():copy_file(p,out/'mh-135-course-documents/coordination'/p.name)
  for name in ['latexmkrc']:
   if (repo/name).is_file():copy_file(repo/name,out/name)
  cat=bank_export(question_bank_path(root,repo),stage/'Data/Question Bank','135' if edition=='135' else None)
  defaults=root/'Data/Syllabuses/Course defaults'
  for p in defaults.glob('*.json'):
   if edition!='135' or p.stem=='135':copy_file(p,stage/'Data/Syllabuses/Course defaults'/p.name)
  (stage/'Data').mkdir(exist_ok=True);(stage/'Temp').mkdir(exist_ok=True)
  (stage/'Data/settings.json').write_text(json.dumps({'portable_output':True},indent=2),encoding='utf-8')
  profile={'edition':'math135-instructor' if edition=='135' else 'full-beta','label':'On this computer' if edition=='135' else 'Full Beta','display_name':'G-Whiz','subtitle':'','theme':'rutgers' if edition=='135' else 'blue','courses':['135'] if edition=='135' else sorted(cat.get('manuals',{})),'coordination':edition!='135'}
  profile['platforms']=['windows']
  (stage/'Data/edition.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
  prepare_layout(root,stage,desktop_runtime=windows)
  prune_folder(stage)
  if destination.exists():
   old=root/'Data/Package History'/(destination.name+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(2));old.parent.mkdir(parents=True,exist_ok=True)
   destination.rename(old)
   try:stage.rename(destination)
   except Exception:old.rename(destination);raise
  else:stage.rename(destination)
  from sync_instructor import record_release
  record_release(root,destination)
  return {'folder':str(destination),'questions':len(cat['questions']),'edition':profile['label']}
 except Exception:
  # Preserve incomplete exports for diagnosis; never delete an installed copy.
  if stage.exists():print('Incomplete package retained at '+str(stage),file=sys.stderr)
  raise

def make_zip(folder):
 folder=Path(folder).resolve()
 if folder.is_symlink() or folder.is_junction():raise ValueError('Package a physical distribution folder.')
 marker=profile_path(folder)
 if not marker.is_file():raise ValueError('ZIP only a generated beta package.')
 profile=json.loads(marker.read_text('utf-8-sig'))
 if profile.get('edition') not in {'math135-instructor','full-beta'}:raise ValueError('ZIP only a generated beta package.')
 leftovers=[p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and omission_reason(p.relative_to(folder))]
 if leftovers:raise ValueError('Clean the instructor distribution before packaging: '+', '.join(leftovers[:10]))
 teaching=profile.get('edition')=='math135-instructor'
 public_name='G-Whiz' if teaching else folder.name
 target=(folder if teaching else folder.parent)/(public_name+'.zip')
 # Stage outside the distribution. Existing release archives must never become
 # inputs on a subsequent build; nested runtime ZIPs (python312.zip) are required.
 staging=Path(__file__).resolve().parents[1]/'Temp/Packaging'
 if staging.drive.casefold()!=folder.drive.casefold():
  staging=folder.parent/('.'+public_name+'-packaging')
 if staging.resolve().is_relative_to(folder):raise ValueError('ZIP staging must be outside the distribution.')
 staging.mkdir(parents=True,exist_ok=True)
 temporary=staging/(public_name+'-'+secrets.token_hex(8)+'.zip')
 inputs=[]
 for current,dirs,files in os.walk(folder,followlinks=False):
  base=Path(current)
  for directory in dirs:
   p=base/directory
   if p.is_symlink() or p.is_junction():raise ValueError('Linked directories are not release inputs.')
  dirs[:]=[d for d in dirs if d!='__pycache__' and not (base==folder and d=='Temp') and not (base==folder/'Data' and d=='Setup')]
  for filename in files:
   p=base/filename;rel=p.relative_to(folder)
   if p.is_symlink() or not p.resolve().is_relative_to(folder):raise ValueError('Release input escaped distribution.')
   if p==target or (len(rel.parts)==1 and p.suffix.lower()=='.zip') or p.suffix.lower() in {'.lnk','.pyc','.pyo'}:continue
   if teaching:
    if rel.parts[0] not in {'App','Data','Dependencies','mh-git'} and rel.as_posix() not in {'START HERE.txt','Open G-Whiz.cmd'}:continue
    if rel.parts[0]=='Data' and rel.as_posix() not in {'Data/settings.json','Data/edition.json'} and rel.parts[:3]!=('Data','Syllabuses','Course defaults') and rel.parts[:2]!=('Data','Question Bank'):continue
   inputs.append((p,rel))
 try:
  with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True,strict_timestamps=False) as z:
   for directory in ('Temp','Dependencies'):
    info=zipfile.ZipInfo(public_name+'/'+directory+'/');info.create_system=3;info.external_attr=(0o40755<<16)|0x10;z.writestr(info,b'')
   for p,rel in sorted(inputs,key=lambda item:item[1].as_posix()):
    name=public_name+'/'+rel.as_posix()
    if teaching and rel.as_posix()=='Data/settings.json':
     z.writestr(name,json.dumps({'portable_output':True},indent=2)+'\n')
    else:z.write(p,arcname=name)
    info=z.getinfo(name);info.create_system=3;info.external_attr=((0o100755 if p.suffix=='.command' else 0o100644)<<16)
  with zipfile.ZipFile(temporary) as z:
   bad=z.testzip()
   if bad:raise ValueError('ZIP verification failed: '+bad)
   assert not any(len(Path(n).parts)==2 and n.lower().endswith('.zip') for n in z.namelist()),'Release archive entered itself'
  temporary.replace(target)
  return str(target)
 finally:temporary.unlink(missing_ok=True)

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--destination',type=Path)
 p.add_argument('--edition',choices=['full','135'],default='135');p.add_argument('--zip',action='store_true');p.add_argument('--offline',action='store_true',help='Include the complete Windows TeX Live runtime; default setup downloads it only if needed.')
 args=p.parse_args();name='G-Whiz-Instructor-Version' if args.edition=='135' else 'G-Whiz-Full-Beta'
 package_name=name
 target=args.destination or (instructor_folder(args.root) if args.edition=='135' else args.root.with_name(package_name))
 result=build(args.root,target,args.edition,bundle_tex=args.offline)
 if args.zip:result['zip']=make_zip(target)
 print(json.dumps(result,indent=2))
