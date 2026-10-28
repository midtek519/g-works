"""User-created course workspaces, separate from supplied course packages."""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import json,re

def validate(code,name=''):
    code=str(code).strip();name=str(name).strip()
    if not re.fullmatch(r'[0-9]{3}',code) or code=='136':raise ValueError('Enter an active three-digit Rutgers Math course number (136 is discontinued).')
    if len(name)>100 or any(ord(c)<32 for c in name):raise ValueError('Keep the course name under 100 characters.')
    return {'code':code,'name':name or 'Math '+code}

def records(root):
    path=Path(root)/'Data/custom-courses.json'
    value=json.loads(path.read_text('utf-8-sig')) if path.is_file() else {'schema':1,'courses':[]}
    return [validate(row['code'],row.get('name','')) for row in value.get('courses',[])]

def semester():
    now=datetime.now();return ('sp' if now.month<6 else 'su' if now.month<9 else 'fa')+str(now.year)[-2:]

def adapter(desk,row):
    code=row['code'];course=desk.repo/('mh-'+code+'-course-documents');output=desk.root/'Published'/code
    def term(tag):
        if not re.fullmatch(r'(fa|sp|su|wi)\d{2}',tag):raise ValueError('Select a valid semester.')
        return {'fa':'Fall','sp':'Spring','su':'Summer','wi':'Winter'}[tag[:2]]+' 20'+tag[2:],tag[:2].title()+tag[2:]
    def discover(tag):
        term(tag);return []
    def plan(items,tag,mode='all',version='all'):
        term(tag)
        if items:raise ValueError('Create a saved handout in this course before compiling it.')
        return []
    return SimpleNamespace(CONFIG={'default_semester':semester(),'course_directory':str(output)},COURSE=course,OUTPUT=output,semester_info=term,discover=discover,plan=plan,display_name=row['name'])

def load(desk):
    for row in records(desk.root):
        desk.modules[row['code']]=adapter(desk,row)

def create(desk,payload):
    from core import save
    from toolchain import question_bank_path
    if not desk.materials_enabled:raise ValueError('Open G-Whiz to add a course.')
    row=validate(payload.get('code',''),payload.get('name',''));code=row['code']
    with desk.lock:
        if code in desk.modules:raise ValueError('That course is already available.')
        saved=records(desk.root)
        if any(item['code']==code for item in saved):raise ValueError('That course is already registered.')
        # Only a directory marker is needed: handouts, questions and syllabuses
        # are created through their existing editing workflows.
        directory=desk.repo/('mh-'+code+'-course-documents');directory.mkdir(parents=True,exist_ok=True)
        bank=question_bank_path(desk.root,desk.repo);catalog=bank/'catalog.json'
        value=json.loads(catalog.read_text('utf-8-sig')) if catalog.is_file() else {'schema_version':1,'status':'ready','questions':[],'topics':[],'objectives':[],'courses':[],'manuals':{},'assets':{}}
        if not any(str(item.get('code'))==code for item in value.setdefault('courses',[])):value['courses'].append(row)
        from course_content import commit,encoded
        commit({catalog:encoded(value),desk.root/'Data/custom-courses.json':encoded({'schema':1,'courses':saved+[row]})})
        desk.modules[code]=adapter(desk,row)
        return {'course':row,'courses':desk.courses()}
