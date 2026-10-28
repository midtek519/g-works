"""Local deterministic extraction of report metadata; never findings or sanctions."""
from pathlib import Path
import re,subprocess

def given_name_first(value):
 value=value.strip()
 if value.count(',')==1:
  family,given=(part.strip() for part in value.split(',',1))
  if family and given:return given+' '+family
 return value

def read_pdf(path):
 if Path(path).suffix.lower()!='.pdf':return''
 r=subprocess.run(['C:/texlive/2026/bin/windows/pdftotext.exe','-layout',str(path),'-'],capture_output=True,timeout=45)
 return r.stdout.decode('utf8',errors='replace')[:1000000]if not r.returncode else''

def parse(text):
 def answer(pattern):
  m=re.search(pattern+r'[^\n]*\n',text,re.I)
  value=text[m.end():].strip().splitlines()[0].strip()if m and text[m.end():].strip()else''
  if re.match(r'(?:Course instructor|Semester and year|Course (?:Name|Number)|Alleged violation|Name of assignment|Percentage of|Description of Incident|If this matter)\b',value,re.I)or value.lower()in('n/a','none','not provided','unknown'):return''
  return value
 def inline(pattern,source=None):
  m=re.search(r'(?im)^\s*'+pattern+r'[ \t]+([^\n]+)',text if source is None else source);return m[1].strip()if m else''
 result={'students':[],'case_fields':{},'contacts':{'complainant':{},'instructor':{}},'warnings':[]}
 sections=re.split('Involved Parties',text,flags=re.I)
 section=re.split(r'\bQuestions\b',sections[1],maxsplit=1,flags=re.I)[0]if len(sections)>1 else''
 rows=list(re.finditer(r'(?m)^\s*([^\n\r()]+?)\s*\((\d{9})\)[ \t]*',section))
 for i,row in enumerate(rows):
  block=section[row.end():rows[i+1].start()if i+1<len(rows)else len(section)]
  emails=set(x.lower()for x in re.findall(r'(?i)\b[A-Z0-9._%+-]+@(?:scarletmail\.)?rutgers\.edu(?![\w.-])',block))
  result['students'].append({**__import__('student_names').parts(row[1]),'name':given_name_first(row[1]),'ruid':row[2],'email':next(iter(emails))if len(emails)==1 else''})
 if not rows:
  for block in re.split(r'(?im)(?=^\s*Name:)',section):
   name=re.search(r'(?im)^\s*Name:\s*([^\n]+)',block)
   if not name:continue
   ruid=re.search(r'(?i)(?:RUID|Student\s*(?:ID|number)|ID\s*number)\s*[:#-]?\s*([\d-]{9,11})',block)
   emails=set(re.findall(r'(?i)\b[A-Z0-9._%+-]+@(?:scarletmail\.)?rutgers\.edu(?![\w.-])',block))
   result['students'].append({**__import__('student_names').parts(name[1]),'name':given_name_first(name[1]),'ruid':re.sub(r'\D','',ruid[1])if ruid else'','email':next(iter(emails))if len(emails)==1 else''})
 fields=result['case_fields'];m=re.search(r'(?im)^\s*Date of incident\s+(\d{4}-\d{2}-\d{2})',text)
 if m:fields['incident_date']=m[1]
 for key,pattern in [('semester','Semester and year of incident'),('course','Course Number'),('assessment',r'Name of assignment\(s\) in question')]:
  value=answer(pattern)
  if value:fields[key]=value
 if re.fullmatch(r'\d{2}:\d{3}:\d{3}',fields.get('course','')):fields['course']=fields['course'].split(':')[-1]
 reporter=re.split('Involved Parties',text,flags=re.I)[0]
 name=inline(r"Incident reporter.s full name",reporter)or inline('Name:',reporter)
 addresses=set(re.findall(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',reporter))
 result['contacts']['complainant']={'name':name,'email':next(iter(addresses))if len(addresses)==1 else''}
 instructor=answer(r'Course instructor.s name');instructor_email=answer(r'Course instructor.s (?:RUTGERS )?email')
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',instructor_email):instructor_email=''
 result['contacts']['instructor']={'name':instructor,'email':instructor_email}
 clean=lambda value:set(re.findall(r'[a-z]+',re.sub(r'\([^)]*\)','',value).lower()))-{'dr','prof','professor'}
 if name and instructor and clean(name)==clean(instructor):
  result['contacts']['instructor_relationship']='same'
  if not instructor_email:result['contacts']['instructor']['email']=result['contacts']['complainant']['email']
 elif instructor:result['contacts']['instructor_relationship']='different'
 return result

def apply_blank_fields(c,suggestion,student=None,overwrite=False):
 changes=[]
 for key,value in suggestion.get('case_fields',{}).items():
  if value and (not c.get(key)or overwrite)and c.get(key)!=value:c[key]=value;changes.append(key)
 if student and c.get('parties'):
  p=c['parties'][0]
  if p.get('ruid')and student.get('ruid')and p['ruid']!=student['ruid']:raise ValueError('The report student does not match this case RUID.')
  for key in ('name','first_name','last_name','ruid','email'):
   if student.get(key)and (not p.get(key)or overwrite)and p.get(key)!=student[key]:p[key]=student[key];changes.append('student '+key)
 contacts=c.setdefault('contacts',{})
 for role in ('complainant','instructor'):
  target=contacts.setdefault(role,{})
  for key,value in suggestion.get('contacts',{}).get(role,{}).items():
   if value and (not target.get(key)or overwrite)and target.get(key)!=value:target[key]=value;changes.append(role+' '+key)
 if not contacts.get('instructor_relationship')and suggestion.get('contacts',{}).get('instructor_relationship'):contacts['instructor_relationship']=suggestion['contacts']['instructor_relationship']
 return changes
