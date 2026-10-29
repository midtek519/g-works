"""One TeX distribution choice for linked suite installations."""
from pathlib import Path
import hashlib,json,os,re,secrets,shutil,subprocess
try:from .runtime_paths import settings_directory
except ImportError:from runtime_paths import settings_directory
DEFAULT={'tex_distribution':'texlive','tex_bin':''}
TOOLS=frozenset(('latexmk','pdflatex','lualatex','xelatex','pdftex','luatex','kpsewhich','tlmgr','biber','bibtex'))

def path(root):return settings_directory(root)/'tex.json'
def read(root):
 p=path(root);return {**DEFAULT,**json.loads(p.read_text('utf-8-sig'))} if p.is_file() else dict(DEFAULT)
def document(root):
 p=path(root);raw=p.read_bytes() if p.is_file() else b'{}'
 return {'id':'shared-tex','name':'Shared TeX','value':read(root),'paths':[{'path':['tex_bin'],'kind':'folder'}],'hash':hashlib.sha256(raw).hexdigest()}
def save(root,payload):
 p=path(root);raw=p.read_bytes() if p.is_file() else b'{}'
 if payload.get('hash')!=hashlib.sha256(raw).hexdigest():raise ValueError('TeX settings changed elsewhere. Reload before saving.')
 value=payload.get('value')
 if not isinstance(value,dict) or set(value)!=set(DEFAULT) or value['tex_distribution'] not in ('texlive','miktex','system'):raise ValueError('Choose TeX Live, MiKTeX, or system TeX.')
 folder=value['tex_bin']
 if not isinstance(folder,str) or len(folder)>2000 or '\x00' in folder:raise ValueError('Choose a compiler folder.')
 if folder and (not Path(folder).is_absolute() or not Path(folder).is_dir()):raise ValueError('Choose an existing absolute compiler folder, or leave it blank for automatic detection.')
 p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name('tex-'+secrets.token_hex(6)+'.tmp')
 try:temp.write_text(json.dumps(value,indent=2)+'\n','utf-8');os.replace(temp,p)
 finally:temp.unlink(missing_ok=True)
 return document(root)
def selection(root):
 value=read(root);config=path(root)
 if not value.get('tex_bin') and config.is_file():
  found=discover(config.parents[2])
  if not found:raise ValueError('No shared TeX installation was detected. Choose one in Shared settings → TeX distribution.')
  value={**value,'tex_bin':found[0]['folder'],'tex_distribution':found[0].get('distribution',value['tex_distribution'])}
 return value
def executable(root,name,fallback=None):
 value=selection(root);folder=value.get('tex_bin')
 if not folder:return fallback
 candidate=Path(folder)/(name+('.exe' if os.name=='nt' else ''))
 if not candidate.is_file():raise ValueError(name+' is unavailable in the shared TeX folder. Check Shared settings → TeX distribution.')
 return str(candidate)

def discover(root,configured=True):
 """Inspect known local paths; never install packages or change the selection."""
 folders=[read(root).get('tex_bin','')] if configured else []
 for name in ('pdflatex','latexmk','xelatex','lualatex'):
  found=shutil.which(name)
  if found:folders.append(str(Path(found).parent))
 folders.extend(str(p) for p in Path('C:/texlive').glob('*/bin/windows'))
 for base in (os.environ.get('LOCALAPPDATA',''),os.environ.get('PROGRAMFILES',''),os.environ.get('PROGRAMFILES(X86)','')):
  if base:
   folders.extend(str(Path(base)/part) for part in ('Programs/MiKTeX/miktex/bin/x64','MiKTeX/miktex/bin/x64'))
 folders.extend(('/Library/TeX/texbin','/usr/bin','/usr/local/bin'))
 apps=Path(root)/'Apps'
 if apps.is_dir():
  for app in apps.iterdir():folders.append(str(app/'Dependencies/texlive/bin/windows'))
 result=[];seen=set()
 for folder in folders:
  if not folder:continue
  path=Path(folder).resolve();key=str(path).casefold()
  if key in seen:continue
  seen.add(key);suffix='.exe' if os.name=='nt' else '';compiler=path/('pdflatex'+suffix)
  if not compiler.is_file():continue
  try:
   probe=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   text=probe.stdout[:3000]
   if probe.returncode:continue
  except (OSError,subprocess.SubprocessError):continue
  kind='miktex' if 'miktex' in text.lower() else 'texlive' if 'tex live' in text.lower() else 'system'
  label={'texlive':'MacTeX' if os.name!='nt' and str(path).startswith('/Library/TeX') else 'TeX Live','miktex':'MiKTeX','system':'System TeX'}[kind]
  year=re.search(r'TeX Live (\d{4})',text,re.I)
  if year and kind=='texlive':label+=' '+year[1]
  if path.is_relative_to(Path(root).resolve()):label+=' (bundled)'
  elif os.name=='nt' and str(path).lower().startswith('c:\\texlive\\'):label+=' (system)'
  result.append({'distribution':kind,'label':label,'folder':str(path),'tools':{name:(path/(name+suffix)).is_file() for name in ('pdflatex','latexmk','lualatex','xelatex')}})
 return result
