"""Native folder selection for the local configuration form; no settings are saved here."""
from pathlib import Path
import json,subprocess,sys

def browse_folder(desk,data):
 code=data['course'];kind=data.get('kind');root=desk.resolve_base(code,data.get('base') or str(desk.output_root(code)))
 if kind and kind not in desk.material_defaults(code):raise ValueError('Choose an available document type.')
 original=str(data.get('pattern','')).strip()
 try:initial=desk.publish_folder(code,desk.module(code).CONFIG['default_semester'],kind,1,patterns={kind:original},root=str(root)) if kind else root
 except ValueError:initial=root
 start=initial
 while not start.is_dir() and start.parent!=start:start=start.parent
 result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--pick','Math '+code+(' — '+kind if kind else ' — Course base folder'),str(start)],capture_output=True,text=True,encoding='utf-8',timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if result.returncode:raise ValueError('The folder browser could not open. You can still type the folder path.')
 try:choice=json.loads(result.stdout).get('folder')
 except (ValueError,AttributeError):raise ValueError('The folder browser did not return a folder. Try again or type the path.')
 if not choice:return {'cancelled':True}
 folder=Path(choice).resolve()
 if not folder.is_dir() or not folder.is_absolute() or str(folder)==folder.anchor:raise ValueError('Choose a folder inside a drive.')
 if kind:
  if folder==initial and original:value=original
  elif folder.is_relative_to(root):value='[root]'+('\\'+str(folder.relative_to(root)) if folder!=root else '')
  else:value=str(folder)
 else:value=str(folder)
 return {'cancelled':False,'value':value,'folder':str(folder)}

def pick(title,initial):
 if sys.platform=='darwin':
  script='POSIX path of (choose folder with prompt '+json.dumps(title)+' default location POSIX file '+json.dumps(initial)+')'
  result=subprocess.run(['osascript','-e',script],capture_output=True,text=True)
  if result.returncode and '(-128)' in result.stderr:return ''
  if result.returncode:raise RuntimeError('The folder browser could not open.')
  return result.stdout.strip()
 import tkinter as tk
 from tkinter import filedialog
 root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
 try:return filedialog.askdirectory(parent=root,title=title,initialdir=initial,mustexist=True)
 finally:root.destroy()

if __name__=='__main__':
 if sys.argv[1:2]==['--pick']:print(json.dumps({'folder':pick(sys.argv[2],sys.argv[3])},ensure_ascii=True))
 elif sys.argv[1:2]==['--check']:
  import tkinter as tk
  root=tk.Tk();root.withdraw();root.destroy();print('Native folder browser ready')
