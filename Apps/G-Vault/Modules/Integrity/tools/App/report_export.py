"""Local-only reporting payload; no network access or inferred findings."""
import hashlib,re
from student_names import full_name
DEFAULT_SANCTION_RATIONALE='The sanctions are proportionate to the level of the offense and the assignment’s weight in the course grade, and are consistent with sanctions imposed in similar cases.'
DEFAULT_NR_RATIONALE='The available evidence does not establish, by a preponderance of the evidence, that the student committed the alleged academic integrity violation. Accordingly, the student is found not responsible.'
CATEGORIES={'Plagiarism':4,'Cheating':5,'Fabrication':6,'Facilitation of dishonesty':7,'Academic sabotage':8,'Violation of research or professional ethics':9}

def prepare(case,letter,party,schema,stamp,pdf=None,reporter=None):
 extraction=letter.get('report_extraction',{})
 r=letter.get('reporting',{});q={**extraction.get('outcome_choices',{}),**letter.get('outcome_choices',{})};kind=letter.get('outcome_kind')or extraction.get('outcome_kind','');fields={};missing=[];warnings=[]
 bykey={f['id']or f['name']:f for f in schema['fields']if f['visible']and f['type']!='file'}
 def put(key,value,required=False,label=None):
  value=str(value or'').strip()
  if not value:
   if required:missing.append(label or bykey[key].get('group_legend')or bykey[key]['label'])
   return
  rule=bykey[key]
  if key=='email_0'and not re.fullmatch(r'[^\s@]+@(?:scarletmail\.)?rutgers\.edu',value,re.I):
   missing.append('Rutgers student email');return
  if '['in value and re.search(r'\[[A-Z][A-Z -]+\]',value):
   missing.append((label or rule['label'])+' (unresolved placeholder)');return
  if rule['type']=='select'and value not in {o['value']for o in rule['options']if not o['disabled']}:
   warnings.append((label or rule['label'])+': value is not offered on this form');return
  if rule['type']=='radio':
   vals={f.get('option_value')for f in schema['fields']if f['name']==rule['name']}
   if value not in vals:warnings.append('Unsupported choice: '+(label or key));return
  if rule.get('max_length')and len(value)>int(rule['max_length']):warnings.append((label or rule['label'])+': exceeds form field length');return
  fields[key]=value
 put('reporters_full_name',case.get('contacts',{}).get('instructor',{}).get('name')or r.get('instructor'),True,"Instructor's name")
 reporter=reporter or {};contacts=' '.join(reporter.get('contact_lines',[]));email=re.search(r'[^\s<>:]+@[^\s<>]+',contacts)
 put('reporters_title',r.get('reporter_title') or reporter.get('title'));put('reporters_email_address',r.get('reporter_email') or (email.group(0) if email else ''),True,'Reporter email')
 put('date_of_incident',case.get('incident_date'),True,'Incident date');put('location_of_incident','01 - SAS - New Brunswick')
 put('person_0',full_name(party),True,'Student name');put('sid_0',party.get('ruid'),True,'RUID');put('email_0',party.get('email'),True,'Student email')
 default_name='Calculus I for Life Sciences'if case['course']in('135','Math 135')else''
 put('aq[1][answer]',r.get('course_name')or default_name,True,'Course name');put('aq[2][answer]',r.get('course_number')or('01:640:135'if default_name else case['course']if re.fullmatch(r'\d{2}:\d{3}:\d{3}',case['course'])else''),True,'Full course number')
 put('aq[3][answer]',q.get('assessment')or letter.get('assessment'),True,'Assessment')
 decisions={};conflicting_categories=set();finding='not responsible'if kind=='not-responsible'else'responsible'
 for v in q.get('violations',[]):
  category=v.get('category');level=str(v.get('level',''))
  if category not in CATEGORIES or level not in ('1','2'):warnings.append('Violation cannot be mapped to this form: '+str(category)+' Level '+level);continue
  choice=category+' Level '+level+' — '+finding
  if category in decisions and decisions[category]!=choice:conflicting_categories.add(category)
  decisions[category]=choice
 for category in conflicting_categories:
  decisions.pop(category,None);warnings.append('Multiple levels selected for '+category+'; the online form permits one choice per category.')
 selected_count=0
 for category,index in CATEGORIES.items():
  value=decisions.get(category)
  if value:put('aq['+str(index)+'][answer]',value,label=category);selected_count+=int('aq['+str(index)+'][answer]'in fields)
 if not selected_count:missing.append('At least one violation category, level, and finding')
 def section(title,next_titles):
  m=re.search(r'(?:^|\n)'+re.escape(title)+r'\s*\n',letter['body'])
  if not m:return''
  value=letter['body'][m.end():];end=re.search(r'(?:^|\n)(?:'+'|'.join(map(re.escape,next_titles))+r')\s*(?:\n|$)',value)
  return value[:end.start()].strip()if end else value.strip()
 nr=kind=='not-responsible'
 put('aq[10][answer]',r.get('additional_notes'))
 put('aq[11][answer]',r.get('decision_rationale')or(DEFAULT_NR_RATIONALE if nr else q.get('rationale')or section('Rationale',['Recommended sanctions'])),True,'Decision rationale')
 sanctions=section('Recommended sanctions',['Appeal information','Hearing and response options'])
 if q.get('sanction_rationale')and sanctions.endswith(q['sanction_rationale'].strip()):sanctions=sanctions[:-len(q['sanction_rationale'].strip())].rstrip()
 put('aq[12][answer]',r.get('sanctions_text')or('None — not responsible.'if nr else sanctions),True,'Recommended sanctions')
 put('aq[13][answer]',r.get('sanction_rationale')or('Not applicable — not responsible.'if nr else q.get('sanction_rationale')or DEFAULT_SANCTION_RATIONALE),True,'Sanction rationale')
 put('aq[14][answer]',r.get('communicated'),True,'Whether student communicated')
 put('aq[15][answer]',r.get('admitted'),True,'Whether student admitted responsibility')
 if r.get('communicated')=='No'and r.get('admitted')in('Yes','No'):warnings.append('Check admission response: no communication is recorded.')
 put('aq[16][answer]',r.get('explanation'))
 if r.get('communicated')=='Yes'and not str(r.get('explanation','')).strip():missing.append('Student explanation (communication recorded)')
 put('aq[17][answer]',r.get('ai_use'),True,'AI involvement')
 fields['sendCopyToAuthor']=True
 bodyhash=hashlib.sha256(letter['body'].encode()).hexdigest()
 status='signed'if pdf and pdf.get('kind')=='signed'else'historical'if pdf and pdf.get('kind')=='historical original'else'draft'
 if status=='draft':warnings.append('Draft export: refresh from the signed final before submitting.')
 if not letter.get('reviewed')and not letter.get('historical'):warnings.append('Letter wording has not been marked reviewed.')
 attachments=[]
 if pdf:attachments.append({'role':'outcome-letter','path':pdf['path'],'sha256':pdf.get('sha256','')})
 return {'schema_version':1,'document_type':'rutgers-final-integrity-report','generated_at':stamp,'case_id':case['id'],'communication_id':letter['id'],'student':{'name':full_name(party),'ruid':party.get('ruid','')},'letter_date':letter['date'],'letter_status':status,'letter_body_sha256':bodyhash,'form':{'origin':'https://cm.maxient.com','path':'/reportingform.php','institution':'RutgersUniv','layout_id':'38'},'fields':fields,'missing_fields':missing,'warnings':warnings,'attachments':attachments,'ready_for_review':not missing and not warnings,'attachment_limit_bytes':5*1024**3,'submission_is_manual':True}
