"""Save a placeholder-based draft without exposing local student identities."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from store import Store
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--letter',required=True);parser.add_argument('--brief',type=Path,required=True);parser.add_argument('--body-file',type=Path,required=True)
    args=parser.parse_args()
    try:
        record=Store(args.root).apply_draft(args.letter,args.body_file.read_text(encoding='utf-8-sig'),args.brief)
        print('Saved anonymized draft for '+record['id']+'. The complete letter requires author review before signing.')
    except(ValueError,OSError):
        print('Draft was not applied. Check that the approved brief matches the unchanged letter, and use placeholders for identities.');sys.exit(1)
