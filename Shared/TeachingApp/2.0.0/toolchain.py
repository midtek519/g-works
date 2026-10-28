"""Relocatable runtime and content paths for G-Whiz."""
from pathlib import Path
import json,os,shutil,sys,subprocess

def repository_path(root,override=None):
 root=Path(root).resolve()
 if override:return Path(override).resolve()
 bundled=root/'mh-git'
 if bundled.is_dir():return bundled
 settings=root/'Data/settings.json'
 config=json.loads(settings.read_text(encoding='utf-8')) if settings.is_file() else {}
 value=config.get('repository')
 if value:return (root/value).resolve()
 from course_content import prepare
 return prepare(root)

def question_bank_path(root,repo=None):
 root=Path(root).resolve();local=root/'Data/Question Bank'
 return local if local.is_dir() else (Path(repo) if repo else repository_path(root))/'exercise-bank'

def executable(root,name):
 root=Path(root).resolve();filename=name+('.exe' if os.name=='nt' else '')
 settings=root/'Data/settings.json'
 config=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.is_file() else {}
 selected=config.get('tex_bin') or config.get('texlive_bin')
 if selected:
  candidate=(root/selected)/filename
  if candidate.is_file():return str(candidate.resolve())
 folders=[root/'Dependencies/texlive/bin/windows',root/'Dependencies/poppler/Library/bin',root/'Dependencies/poppler/bin',*sorted((root/'Dependencies/texlive/bin').glob('*darwin*'))]
 for folder in folders:
  candidate=folder/filename
  if candidate.is_file():return str(candidate)
 if sys.platform=='darwin':
  for folder in ['/Library/TeX/texbin','/opt/homebrew/bin','/usr/local/bin']:
   candidate=Path(folder)/filename
   if candidate.is_file():return str(candidate)
 installed=shutil.which(name)
 if installed:return installed
 if name in ('latexmk','pdflatex','kpsewhich'):
  for folder in sorted(Path('C:/texlive').glob('*/bin/windows'),reverse=True):
   candidate=folder/filename
   if candidate.is_file():return str(candidate)
 raise ValueError(name+' is missing. Run Install G-Whiz to check the bundled runtime.')


def open_folder(folder):
 if os.name=='nt':os.startfile(str(folder))
 else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
