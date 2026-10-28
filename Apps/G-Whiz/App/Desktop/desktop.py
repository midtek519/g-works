from pathlib import Path
import os,runpy,sys
ROOT=Path(__file__).resolve().parents[2]
os.environ['GWORKS_APP_ROOT']=str(ROOT)
CODE=(ROOT/'Dependencies/TeachingApp').resolve()
sys.path.insert(0,str(CODE))
runpy.run_path(str(CODE/'Desktop/desktop.py'),run_name='__main__')
