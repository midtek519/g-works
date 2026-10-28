from pathlib import Path
import argparse,json,subprocess,sys,os
sys.path.insert(0,str(Path(__file__).resolve().parent))
from core import Desk
from universal import Universal
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=p.parse_args()
try:
 desk=Desk(args.root);check=desk.system_check()
 for tool in desk.system_check()['tools']:
  result=subprocess.run([desk.tool(tool),'-version' if tool=='latexmk' else '--version' if tool=='pdflatex' else '-v'],capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if result.returncode:raise ValueError(tool+' did not start successfully.')
 from folder_picker import pick
 if os.name=='nt':
  import tkinter as tk
  root=tk.Tk();root.withdraw();root.destroy()
 bank=Universal(desk)
 if not bank.available():raise ValueError('The question bank is missing.')
 check['question_bank']='Available';check['folder_browser']='Ready';print(json.dumps(check,indent=2))
except Exception as exc:print('G-Whiz setup check: '+str(exc));raise SystemExit(1)
