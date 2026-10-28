"""Apply only a matching approved-brief draft. Never prints private case fields."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from casebook import Store
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--case',required=True);p.add_argument('--communication',required=True);p.add_argument('--brief',required=True,type=Path);p.add_argument('--body-file',required=True,type=Path);a=p.parse_args()
 try:Store(a.root).apply_draft(a.case,a.communication,a.brief,a.body_file.read_text(encoding='utf-8-sig'));print('Draft saved locally for author review. No letter was signed or sent.')
 except (ValueError,OSError):p.exit(1,'Draft not saved. Check the approved brief and whether the communication has changed.\n')
