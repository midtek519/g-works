"""Personal sender details, kept locally; Rutgers Mathematics is the institution."""
from pathlib import Path
import json, os, tempfile

FIELDS=('name','title','email','phone','office','website')
BASE={'institution':'Rutgers University','department':'Department of Mathematics'}

def profile_path(root):
    return Path(root)/'Data/instructor-profile.json'

def read(root):
    path=profile_path(root)
    value=json.loads(path.read_text('utf-8-sig')) if path.is_file() else {}
    return {**{key:'' for key in FIELDS},**value,**BASE,'configured':bool(value.get('name'))}

def validate(value):
    if not isinstance(value,dict):raise ValueError('Enter your instructor details.')
    result={**BASE,'schema':1}
    for key in FIELDS:
        text=value.get(key,'')
        if not isinstance(text,str) or len(text)>300 or any(ord(c)<32 for c in text):raise ValueError('Check your '+key+'.')
        result[key]=text.strip()
    if not result['name']:raise ValueError('Enter your name.')
    return result

def write(root,value):
    result=validate(value);path=profile_path(root);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False,suffix='.new') as stream:
        temporary=Path(stream.name);json.dump(result,stream,indent=2)
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return read(root)
