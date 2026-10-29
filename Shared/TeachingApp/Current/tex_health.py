"""Selected-distribution checks; downloads occur only in an explicit repair job."""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,shutil,subprocess,sys,tempfile,threading,time,zlib,struct
sys.path.insert(0,str(Path(__file__).resolve().parent))
from private_module_ui import shared_tex
from app_catalog import catalog
from tex_lookup import missing_requirements,dependencies,MIKTEX_READ_ONLY

def run(args,timeout=30,env=None):
 return subprocess.run(list(map(str,args)),capture_output=True,text=True,errors='replace',timeout=timeout,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
 try:
  tmp.write_text(json.dumps(value,indent=2)+'\n','utf-8')
  for attempt in range(30):
   try:os.replace(tmp,path);break
   except PermissionError:
    if attempt==29:raise
    time.sleep(.025)
 finally:tmp.unlink(missing_ok=True)
def targets(root,apps=None):
 specs,_=catalog(root);selected=set(apps) if apps else set(specs);result=[];math=None
 if selected-set(specs):raise ValueError('Choose installed apps for the TeX check.')
 for ident,spec in specs.items():
  if ident not in selected:continue
  app=Path(spec['root'])/'Apps'/spec['folder']
  if not app.is_dir():continue
  library=app/'Dependencies/TeachingSupport/lib'
  if spec.get('suite')=='professional':
   if not (library/'mhdocument.cls').is_file():raise ValueError(spec['name']+' TeX support files are missing. Repair the app through Install / update.')
   if math is None:math={'kind':'teaching','library':str(library.resolve()),'names':[]};result.append(math)
   math['names'].append(spec['name'])
  settings=app/'Data/settings.json';values=json.loads(settings.read_text('utf-8-sig')) if settings.is_file() else {};source=values.get('tex_root')
  if source or (app/'dnd-git').is_dir():
   source=Path(source) if source else app/'dnd-git';source=source if source.is_absolute() else app/source
   if not (source/'lib/dndbook.cls').is_file():raise ValueError(spec['name']+' publication support files are missing. Check its source folder or repair the app through Install / update.')
   result.append({'kind':'publication','library':str((source/'lib').resolve()),'names':[spec['name']]})
 return result
def selection(root,value):
 if not isinstance(value,dict) or set(value)!=set(shared_tex.DEFAULT) or value['tex_distribution'] not in ('texlive','miktex','system'):raise ValueError('Choose a displayed TeX installation.')
 folder=value['tex_bin']
 if not isinstance(folder,str) or len(folder)>2000 or '\x00' in folder:raise ValueError('Choose a valid compiler folder.')
 if not folder:
  found=shared_tex.discover(root,configured=False)
  if not found:raise ValueError('No TeX installation was detected.')
  return {'tex_distribution':found[0]['distribution'],'tex_bin':found[0]['folder']}
 if not Path(folder).is_absolute() or not Path(folder).is_dir():raise ValueError('Choose an existing absolute compiler folder.')
 return dict(value)
def requirements(groups):
 manifest=json.loads(Path(__file__).with_name('tex_requirements.json').read_text('utf-8'));required=set(manifest['required_files']) if any(g['kind']=='teaching' for g in groups) else {'article.cls'}
 external,alternatives=dependencies([g['library'] for g in groups if g['kind']=='publication'],engine='luatex');required.update(external)
 return manifest,sorted(required),alternatives

def environment(selected,groups):
 env=dict(os.environ);env['PATH']=selected['tex_bin']+os.pathsep+env.get('PATH','');env['TEXINPUTS']=os.pathsep.join(g['library'].replace('\\','/')+'//' for g in groups)+os.pathsep+env.get('TEXINPUTS','')+os.pathsep;return env
def probe(root,value,apps=None,report=lambda text:None):
 groups=targets(root,apps)
 if not groups:return {'apps':[],'missing_files':[],'missing_tools':[],'checks':[],'state':'not_required','message':'These installed apps do not require TeX.'},groups
 selected=selection(root,value);folder=Path(selected['tex_bin']);suffix='.exe' if os.name=='nt' else '';teaching=any(g['kind']=='teaching' for g in groups);publication=any(g['kind']=='publication' for g in groups);primary='pdflatex' if teaching else 'lualatex';tools=(['pdflatex'] if teaching else [])+['kpsewhich']+(['lualatex','latexmk'] if publication else [])
 result={'selection':selected,'apps':[name for g in groups for name in g['names']],'missing_files':[],'missing_tools':[name for name in tools if not (folder/(name+suffix)).is_file()],'checks':[]}
 if not groups:return {**result,'state':'not_required','message':'These installed apps do not require TeX.'},groups
 if result['missing_tools']:return {**result,'state':'missing_tools','message':'Missing TeX tools: '+', '.join(result['missing_tools'])},groups
 version=run([folder/(primary+suffix),*(MIKTEX_READ_ONLY if selected['tex_distribution']=='miktex' else []),'--version'],timeout=10)
 if version.returncode:raise ValueError('The selected PDF compiler could not start: '+(version.stdout+version.stderr)[-1000:])
 actual='miktex' if 'miktex' in version.stdout.casefold() else 'texlive' if 'tex live' in version.stdout.casefold() else 'system'
 if selected['tex_distribution'] not in ('system',actual):raise ValueError('The selected folder contains '+actual+', which differs from the selected distribution.')
 selected['tex_distribution']=actual;result['compiler_version']=version.stdout.splitlines()[0];report(result['compiler_version']);manifest,required,alternatives=requirements(groups);env=environment(selected,groups)
 checked_files=len(set(required).union(*(set(group) for group in alternatives)));report('Checking '+str(checked_files)+' required TeX files for '+', '.join(result['apps'])+'.')
 result['missing_files']=missing_requirements(folder,actual,required,alternatives,env=env,runner=run)
 result['checked_files']=checked_files;result['requirements_version']=manifest['version'];result['checks']=['compiler','required files']
 result.update(state='missing_packages' if result['missing_files'] else 'ready',message=str(len(result['missing_files']))+(' required TeX file is missing.' if len(result['missing_files'])==1 else ' required TeX files are missing.') if result['missing_files'] else 'Compiler and required packages are available.')
 return result,groups
def repair_texlive(selected,missing,groups,report):
 folder=Path(selected['tex_bin']);base=folder.parents[1];perl=base/'tlpkg/tlperl/bin/perl.exe';manager=base/'texmf-dist/scripts/texlive/tlmgr.pl'
 if not perl.is_file() or not manager.is_file():raise ValueError('This TeX Live installation has no usable package manager. Repair it with TeX Live Manager.')
 packages=set();env=environment(selected,groups)
 for name in missing:
  found=run([perl,manager,'search','--global','--file','/'+re.escape(name)+'$'],timeout=180,env=env)
  if found.returncode:raise ValueError('TeX Live could not look up '+name+'.')
  packages.update(re.findall(r'(?m)^([A-Za-z0-9][A-Za-z0-9._+-]*):\s*$',found.stdout))
 if not packages:raise ValueError('TeX Live could not identify packages for the missing files.')
 report('Installing missing packages: '+', '.join(sorted(packages)));installed=run([perl,manager,'install',*sorted(packages)],timeout=1800,env=env);report(installed.stdout+installed.stderr)
 if installed.returncode:raise ValueError('TeX Live package installation did not finish.')
def smoke(selected,groups,work,repair,report):
 import instructor_tex
 from tex_compile import compile_document
 checks=[];suffix='.exe' if os.name=='nt' else '';folder=Path(selected['tex_bin'])
 try:
  for i,group in enumerate(groups):
   started=time.monotonic();report('Compiling test PDFs for '+', '.join(group['names'])+(' (LuaLaTeX; the first font-database scan can take several minutes).' if group['kind']=='publication' else '.'));workspace=work/str(i);workspace.mkdir()
   library=workspace/'mh-git/lib';library.parent.mkdir();shutil.copytree(group['library'],library)
   if group['kind']=='teaching':checks+=instructor_tex.smoke(workspace,folder,selected['tex_distribution'],install=repair)
   else:
    source=workspace/'check.tex';source.write_text(r'\documentclass[graphics=final,paper=false,art=false,ornaments=false]{dndbook}\begin{document}Publication compiler check.\end{document}','utf-8')
    image=workspace/'img/banner_hline.png';image.parent.mkdir();chunk=lambda kind,data:struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff);image.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff'))+chunk(b'IEND',b''))
    env=environment(selected,[{'library':str(library)}]);compiled=compile_document(folder/('lualatex'+suffix),source,workspace,miktex=selected['tex_distribution']=='miktex',install=repair,cwd=workspace,env=env,timeout=900 if repair else 240);report(compiled.stdout+compiled.stderr)
    if compiled.returncode or not (workspace/'check.pdf').is_file():raise ValueError('The publication PDF check failed. Expand the check log for details.')
    checks.append('publication PDF')
   report('Test PDFs passed for '+', '.join(group['names'])+' in '+str(round(time.monotonic()-started,1))+' seconds.')
 finally:
  for path in work.rglob('console.txt'):report(path.read_text('utf-8',errors='replace'))
 return checks
class Guard:
 def __init__(self,path):
  path.parent.mkdir(parents=True,exist_ok=True);self.file=path.open('a+b');self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
  try:
   if os.name=='nt':import msvcrt;msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
   else:import fcntl;fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError:self.file.close();raise ValueError('Another TeX check or repair is running.') from None
 def close(self):self.file.close()
class Checks:
 def __init__(self,root):self.root=Path(root);self.folder=shared_tex.path(root).parent/'TeXChecks'
 def read(self,identity):
  if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{16}',identity):raise ValueError('Choose a TeX check.')
  path=self.folder/(identity+'.json')
  if not path.is_file():raise ValueError('That TeX check is unavailable.')
  return json.loads(path.read_text('utf-8'))
 def latest(self):
  records=[self.read(p.stem) for p in self.folder.glob('*.json') if re.fullmatch('[a-f0-9]{16}',p.stem)]
  return max(records,key=lambda record:record['created']) if records else None
 def log(self,identity):self.read(identity);return self.folder/(identity+'.txt')
 def start(self,payload):
  if not isinstance(payload,dict) or set(payload)-{'value','repair'} or type(payload.get('repair',False)) is not bool:raise ValueError('Use the displayed TeX check controls.')
  value=payload.get('value');selection(self.root,value);guard=Guard(self.folder/'operation.lock');identity=secrets.token_hex(8);record={'id':identity,'status':'running','message':'Checking the selected TeX installation…','requested_value':value,'repair':payload.get('repair',False),'created':time.time()};write(self.folder/(identity+'.json'),record)
  threading.Thread(target=self.work,args=(record,guard),daemon=False).start();return record
 def work(self,record,guard):
  log=self.folder/(record['id']+'.txt')
  def progress(text):
   with log.open('a',encoding='utf-8') as file:file.write(str(text)+'\n')
   if len(str(text))<500:record['message']=str(text);write(self.folder/(record['id']+'.json'),{**record,'status':'running'})
  try:
   result,groups=probe(self.root,record['requested_value'],report=progress);record['result']=result
   if result['state'] in ('missing_tools','not_required'):record.update(status='failed' if result['state']=='missing_tools' else 'ready',message=result['message']);return
   if result['missing_files'] and not record['repair']:record.update(status='failed',message=result['message']);progress('Missing files: '+', '.join(result['missing_files']));return
   if result['missing_files'] and record['repair'] and result['selection']['tex_distribution']=='texlive':repair_texlive(result['selection'],result['missing_files'],groups,progress)
   progress('Checking real test PDFs'+(' and installing missing packages as needed.' if record['repair'] else ' without installing packages.'))
   with tempfile.TemporaryDirectory(prefix='check-',dir=self.folder) as temporary:
    workspace=Path(temporary);assert workspace.resolve().is_relative_to(self.folder.resolve());checks=smoke(result['selection'],groups,workspace,record['repair'],progress)
   checked,_=probe(self.root,result['selection'],report=progress)
   checked['checks']+=checks;record['result']=checked
   if checked['state']!='ready':raise ValueError(checked['message'])
   record.update(status='ready',result=checked,message='Required packages and test PDFs passed.');progress(record['message'])
  except Exception as error:record.update(status='failed',message=str(error)[:2000]);progress(str(error))
  finally:
   guard.close();write(self.folder/(record['id']+'.json'),record)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--apps',nargs='*');args=parser.parse_args()
 try:
  guard=Guard(Checks(args.root).folder/'operation.lock');guard.close()
  result,_=probe(args.root,shared_tex.read(args.root),args.apps);print(json.dumps(result));return 0
 except ValueError as error:
  print(json.dumps({'state':'checking' if 'Another TeX check' in str(error) else 'check_failed','message':str(error)[:1000]}));return 0
 except Exception as error:print(json.dumps({'state':'check_failed','message':str(error)[:1000]}));return 0
if __name__=='__main__':raise SystemExit(main())
