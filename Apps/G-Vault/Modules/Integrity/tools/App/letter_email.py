"""Prepare unsent Thunderbird compose windows; never sends messages."""
import hashlib,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
from contact_review import email

def prepare(case,letter,party,pdf,settings):
 to=email(party.get('email'))
 if not re.fullmatch(r'[^\s@]+@(?:scarletmail\.)?rutgers\.edu',to,re.I):raise ValueError('Set the student Rutgers email in Overview first.')
 if letter.get('delivery')=='email':
  body=letter['body']
  if not re.match(r'\s*(?:Dear|Hello|Hi)\b',body):body=letter.get('salutation','Hello,')+'\n\n'+body
  addresses=re.findall(r'[^\s@<>:]+@[^\s@<>]+\.[A-Za-z]{2,}',' '.join(settings.get('sender',{}).get('contact_lines',[])))
  result={'to':to,'cc':[],'bcc':[],'subject':letter.get('subject','Academic Integrity'),'body':body,'from':addresses[0]if len(set(addresses))==1 else'','attachment_name':'','attachment_url':''}
  result['fingerprint']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest();return result
 contacts=case.get('contacts',{})
 if not contacts.get('confirmed_at')or contacts.get('instructor_relationship')not in('same','different'):raise ValueError('Confirm the complainant and instructor contacts in Overview first.')
 cc=[]
 for role in ('complainant','instructor'):
  contact=contacts.get(role,{})
  if not contact.get('name'):raise ValueError('Confirm the '+role+' name first.')
  address=email(contact.get('email'))
  if address.lower()!=to.lower()and address.lower()not in [v.lower()for v in cc]:cc.append(address)
 course=case.get('course','');course='Math '+course if course.isdigit()else course
 subject='Academic Integrity Decision'+(' — '+course if course else'')+(' — '+case['semester']if case.get('semester')else'')
 subject=' '.join(subject.split())
 body='Hello,\n\nPlease see the attached outcome letter regarding your academic integrity case.\n\n'
 attachment=Path(pdf['path']);sender_addresses=re.findall(r'[^\s@<>:]+@[^\s@<>]+\.[A-Za-z]{2,}',' '.join(settings.get('sender',{}).get('contact_lines',[])))
 result={'to':to,'cc':cc,'bcc':[],'subject':subject,'body':body,'attachment_path':str(attachment),'attachment_name':attachment.name,'attachment_sha256':pdf['sha256'],'revision_id':pdf['id'],'from':sender_addresses[0]if len(set(sender_addresses))==1 else''}
 result['fingerprint']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest();return result

def compose_argument(plan):
 values={'to':plan['to'],'cc':','.join(plan['cc']),'bcc':','.join(plan['bcc']),'subject':plan['subject'],'body':plan['body'],'format':'text'}
 if plan.get('attachment_path'):values['attachment']=Path(plan['attachment_path']).resolve().as_uri()
 if plan.get('from'):values['from']=plan['from']
 # Encode all delimiters before passing one argument directly to Thunderbird.
 return ','.join(k+'='+quote(v,safe='')for k,v in values.items())

def launch(plan,executable,opener=None):
 executable=Path(executable)
 if executable.name.lower()!='thunderbird.exe'or not executable.is_file():raise ValueError('Thunderbird was not found. Check its configured program path.')
 if plan.get('attachment_path'):
  attachment=Path(plan['attachment_path'])
  if not attachment.is_file()or hashlib.sha256(attachment.read_bytes()).hexdigest()!=plan['attachment_sha256']:raise ValueError('The signed attachment changed. Generate a fresh email preview.')
 (opener or subprocess.Popen)([str(executable),'-compose',compose_argument(plan)],cwd=str(executable.parent),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
