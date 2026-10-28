"""Deterministic local PDF contact suggestions. Nothing is assigned until confirmed."""
from pathlib import Path
import re,subprocess
EMAIL=r'[^\s@,;<>]+@[^\s@,;<>]+\.[A-Za-z]{2,}'
def email(value):
 value=str(value or'').strip()
 if not re.fullmatch(EMAIL,value):raise ValueError('Enter one valid email address for each role.')
 return value

def contact_suggestions(text,name='',sender=None):
 text=text.replace('\r','');compact=re.sub(r'\W','',text.lower())
 report=bool(re.search(r'(?:^|[- _])IR(?:\d|[- _])|complaint[ _-]*(?:received|report)|incident[ _-]*report',name,re.I))or'initialacademicintegrityreportingform'in compact
 result={'is_report':report,'complainant':{'name':'','email':''},'instructor':{'name':'','email':''},'instructor_relationship':'','warnings':[]}
 if not report:return result
 m=re.search(r'Reported by\s*\n(.*?)(?:Involved Parties|Questions)',text,re.S|re.I)
 if m:
  for field,label in [('name','Name'),('email','Email')]:
   found=re.search(r'(?im)^\s*'+label+r':[ \t]*([^\n]*)',m[1])
   if found:result['complainant'][field]=found[1].strip()
 # Official complaint-received letters can identify the author as the complainant,
 # but they do not establish who the course instructor was.
 if not result['complainant']['name']and re.search(r'received your complaint',text,re.I):
  who=re.search(r'Dear\s+([^,\n]+),',text);sender=sender or{};words=lambda s:set(re.findall(r'[a-z]+',s.lower()))-{'dr','professor','prof'}
  if who and words(sender.get('name',''))and words(sender.get('name',''))<=words(who[1]):
   result['complainant']['name']=sender['name'];addresses=re.findall(EMAIL,' '.join(sender.get('contact_lines',[])))
   if len(set(addresses))==1:result['complainant']['email']=addresses[0]
 def answer(label):
  found=re.search(r'(?im)^\s*Course instructor.s '+label+r'[^\n]*\n',text)
  if not found:return''
  tail=text[found.end():];value=re.split(r'(?im)^\s*(?:Course instructor|Semester and year|Course [Nn]ame|Course [Nn]umber|Alleged violation)',tail)[0].strip()
  return value.splitlines()[0].strip()if value else''
 result['instructor']['name']=answer('name');result['instructor']['email']=answer('(?:RUTGERS )?email')
 for role in ('complainant','instructor'):
  value=result[role]['email']
  if value and not re.fullmatch(EMAIL,value):result[role]['email']='';result['warnings'].append('Check the '+role+' email against the report.')
 if any(result['instructor'].values()):result['instructor_relationship']='different'
 if not all(result['instructor'].values()):result['warnings'].append('Confirm whether the complainant is also the instructor; otherwise enter the instructor name and email.')
 return result

def inspect_pdf(path,name,sender=None):
 if Path(path).suffix.lower()!='.pdf':return {'is_report':False}
 known=bool(re.search(r'(?:^|[- _])IR(?:\d|[- _])|complaint[ _-]*(?:received|report)|incident[ _-]*report',name,re.I))
 exe=Path('C:/texlive/2026/bin/windows/pdftotext.exe')
 if not exe.is_file():return {'is_report':known,'warnings':['PDF text extraction is unavailable; enter contacts manually.']}
 try:
  output=subprocess.run([str(exe),'-layout','-f','1','-l','3',str(path),'-'],capture_output=True,timeout=20)
  if output.returncode:return {'is_report':known,'warnings':['No readable report text was found; enter contacts manually.']}
  return contact_suggestions(output.stdout.decode('utf-8',errors='replace')[:200000],name,sender)
 except (OSError,subprocess.TimeoutExpired):return {'is_report':known,'warnings':['Report text could not be extracted; enter contacts manually.']}
