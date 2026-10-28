"""A single student and checklist per case; incidents may be shared by cases."""
import copy,re

STAGES=[('intake','Upload incident report into evidence'),('contact','Generate and send meeting contact letter'),('meeting','Hold meeting or document the applicable alternative'),('evidence','Complete evidence review and investigation'),('outcome','Generate and send outcome letter'),('report','Generate Final Reporting Form JSON file and submit'),('appeal-received','Received notice of student appeal and appeal statement'),('appeal-response','Generated appeal response'),('appeal-decision','Appeal decision received')]
APPEAL_IDS={'appeal-received','appeal-response','appeal-decision'}
DOCUMENT_TYPES={'incident-report','email-correspondence','assignment','student-testimony','student-meeting-summary','supporting-evidence','other'}

def normalize_evidence(c):
 for f in c.get('files',[]):
  f.pop('party_id',None)
  kind=f.get('kind','other');name=f.get('name','')
  if kind=='finding-rationale':f['purpose']='finding-rationale'
  if kind in DOCUMENT_TYPES:continue
  f.setdefault('original_kind',kind)
  if re.search(r'(?:^|[- _])IR\d',name,re.I):kind='incident-report'
  elif kind in ('exam-evidence','exam','assignment-evidence'):kind='assignment'
  elif kind in ('written-response','student-response','student-statement','written-statement')or re.match(r'Written\b',name,re.I):kind='student-testimony'
  elif kind in ('email','email-correspondence','complaint-received')or name.lower().endswith(('.eml','.msg')):kind='email-correspondence'
  elif kind in ('meeting-notes','meeting-summary'):kind='student-meeting-summary'
  else:kind='other'
  f['kind']=kind
 return c

def active_appeal(c):
 steps={s['id']:s for s in c.get('steps',[])}
 return bool(steps.get('appeal-received',{}).get('done')and not steps.get('appeal-decision',{}).get('done'))

def normalize(c):
 if c.get('workflow_version')==2:return normalize_evidence(c)
 old=copy.deepcopy(c.get('steps',[]));c['legacy_steps']=old
 parties=c.get('parties',[])
 if len(parties)>1:
  if len({p['ruid']for p in parties if p.get('ruid')})>1:raise ValueError('Different student RUIDs must be placed in separate cases before consolidating this record.')
  c['legacy_parties']=copy.deepcopy(parties)
  tokens=lambda v:set(re.findall(r'[a-z0-9]+',str(v).lower()))
  title=tokens(c.get('title',''))
  def score(p):
   names=tokens(p['name']);return (len(names&title)/max(1,len(names|title)),bool(p.get('ruid')),bool(p.get('email')))
  primary=max(parties,key=score)
  for key in ('ruid','email','netid'):
   vals={p.get(key,'').strip()for p in parties};vals.discard('')
   if not primary.get(key)and len(vals)==1:primary[key]=next(iter(vals))
  for p in parties:
   if p is not primary and p.get('notes')and p['notes']not in primary.get('notes',''):primary['notes']=(primary.get('notes','')+'\n\n'+p['notes']).strip()
  ids={p['id']for p in parties}
  for item in c.get('files',[])+c.get('communications',[]):
   if item.get('party_id')in ids:item['party_id']=primary['id']
   for export in item.get('report_exports',[]):
    if export.get('party_id')in ids:export['party_id']=primary['id']
  c['parties']=[primary]
 c['steps']=[]
 for identity,label in STAGES:
  candidates=[s for s in old if s['id']==identity]if identity not in APPEAL_IDS else[]
  done=[s for s in candidates if s.get('done')]
  source=next(iter(done or candidates),{})
  c['steps'].append({'id':identity,'label':label,'party_id':'','done':bool(done),'completed_at':source.get('completed_at','')if done else'','skipped':False,'optional':identity in APPEAL_IDS})
 c['workflow_version']=2;c.setdefault('meetings',[])
 reports=[f for f in c.get('files',[])if f.get('kind')=='incident-report'or re.search(r'(?:^|[- _])IR\d',f.get('name',''),re.I)]
 if reports:
  row=c['steps'][0]
  if not row['done']:row.update(done=True,completed_at=next((f['uploaded']for f in reports if f.get('uploaded')),''),date_basis='Report stored locally')
 if c.get('closed'):
  for row in c['steps']:
   if row['optional']:continue
   row['done']=True
   if not row['completed_at']and row['id']=='outcome':
    dates=[l.get('date','')for l in c.get('communications',[])if l.get('outcome_kind')or l.get('kind')=='outcome']
    row['completed_at']=c.get('outcome_date')or next(iter(sorted(filter(None,dates),reverse=True)),'')
    if row['completed_at']:row['date_basis']='Letter date; send date unknown'
   row['date_unknown']=not bool(row['completed_at'])
   if not row['completed_at']:row['date_basis']='Date unknown'
 return normalize_evidence(c)

def missing_details(c):
 p=next(iter(c.get('parties',[])),{});contacts=c.get('contacts',{})
 fields=[('Student name',p.get('name')),('RUID',p.get('ruid')),('Student email',p.get('email')),('Complainant name',contacts.get('complainant',{}).get('name')),('Complainant email',contacts.get('complainant',{}).get('email')),('Instructor name',contacts.get('instructor',{}).get('name')),('Instructor email',contacts.get('instructor',{}).get('email')),('Incident date',c.get('incident_date')),('Assessment',c.get('assessment')),('Course number',c.get('course')),('Semester',c.get('semester'))]
 return [label for label,value in fields if not str(value or'').strip()]

def set_step(c,identity,done,stamp,skipped=False):
 normalize(c);steps={s['id']:s for s in c['steps']}
 if identity not in steps:raise ValueError('Choose a checklist item.')
 if identity=='meeting' and done and not skipped:
  from meeting_response import response_required
  if response_required(c) and c.get('meeting_response',{}).get('status')!='scheduled':raise ValueError('Record an arranged meeting before completing the meeting item.')
 if identity in ('appeal-response','appeal-decision')and not steps['appeal-received']['done']:raise ValueError('Record the appeal notice before completing appeal follow-up items.')
 if skipped and identity in APPEAL_IDS|{'report'}:raise ValueError('This item must be explicitly completed rather than marked not needed.')
 row=steps[identity];row.update(done=done and not skipped,skipped=skipped,completed_at=stamp if done and not skipped else'')
 if identity=='appeal-received':
  if done:c['closed']=False
  else:
   for child in ('appeal-response','appeal-decision'):steps[child].update(done=False,completed_at='',skipped=False)
   c['closed']=bool(steps['report']['done'])
 elif identity=='appeal-decision':c['closed']=bool(done)or(bool(steps['report']['done'])and not active_appeal(c))
 elif identity=='report':c['closed']=bool(done)and not active_appeal(c)
 if identity in ('report','appeal-received','appeal-decision'):c['status_review']=False
 return row
