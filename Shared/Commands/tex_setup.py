"""Find and reuse an existing TeX Live before selecting a bundled runtime."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

REQUIRED=('xsim.sty','pgfplots.sty','enumitem.sty','booktabs.sty','mathpazo.sty','xparse.sty')
def usable(folder):
 suffix='.exe' if os.name=='nt' else ''
 if not all((folder/(name+suffix)).is_file() for name in ('latexmk','pdflatex','kpsewhich')):return False
 env=os.environ.copy();env['PATH']=str(folder)+os.pathsep+env.get('PATH','')
 def run(name,*args):
  return subprocess.run([str(folder/(name+suffix)),*args],capture_output=True,text=True,errors='replace',timeout=15,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  version=run('pdflatex','--version')
  if version.returncode or 'TeX Live' not in version.stdout:return False
  for package in REQUIRED:
   result=run('kpsewhich',package)
   if result.returncode or not result.stdout.strip():return False
  return run('latexmk','-version').returncode==0
 except (OSError,subprocess.TimeoutExpired):return False

def select(root,explicit=None,prefer_bundled=False):
 root=Path(root).resolve();settings=root/'Data/settings.json'
 from instructor_tex import enabled,discover
 if enabled(root):
  selected=discover(root,explicit or (root/'Dependencies/texlive/bin/windows' if prefer_bundled else None))
  selected['message']=selected.get('message') or ('Using '+selected['distribution']+': '+selected['bin'])
  if not selected.get('usable'):selected['source']='missing'
  return selected
 config=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.is_file() else {}
 bundled=[root/'Dependencies/texlive/bin/windows',*sorted((root/'Dependencies/texlive/bin').glob('*darwin*'))]
 if explicit and not usable(Path(explicit).expanduser().resolve()):return {'source':'missing','message':'The selected TeX Live bin folder is missing a compiler or required package.'}
 candidates=[]
 if explicit:candidates.append(Path(explicit).expanduser())
 if config.get('texlive_bin'):candidates.append((root/config['texlive_bin']).resolve())
 for name in ('pdflatex','latexmk'):
  found=shutil.which(name)
  if found:candidates.append(Path(found).parent)
 if os.name=='nt':candidates.extend(sorted(Path('C:/texlive').glob('*/bin/windows'),reverse=True))
 else:candidates.extend([Path('/Library/TeX/texbin'),*sorted(Path('/usr/local/texlive').glob('*/bin/*darwin*'),reverse=True)])
 candidates=[p.resolve() for p in candidates if p.resolve() not in [b.resolve() for b in bundled]]
 order=[('bundled',p) for p in bundled] if prefer_bundled else [('existing',p) for p in dict.fromkeys(candidates)]
 if not prefer_bundled:order.extend(('bundled',p) for p in bundled)
 for source,folder in order:
  if usable(folder):
   value=folder.relative_to(root).as_posix() if folder.is_relative_to(root) else str(folder)
   return {'source':source,'bin':value,'message':('Reusing your existing TeX Live: ' if source=='existing' else 'Using the included TeX Live; no separate installation is needed: ')+str(folder)}
 return {'source':'missing','message':'A usable TeX Live was not found. Choose its bin folder if already installed, or run Install G-Whiz to download and install it.'}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--bin');p.add_argument('--bundled',action='store_true');p.add_argument('--configure',action='store_true');a=p.parse_args()
 result=select(a.root,a.bin,a.bundled)
 if result['source']!='missing' and a.configure:
  settings=a.root/'Data/settings.json';settings.parent.mkdir(parents=True,exist_ok=True)
  data=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.is_file() else {};data['texlive_bin']=result['bin']
  settings.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False));raise SystemExit(2 if result['source']=='missing' else 0)
