"""Approved reusable wording; private case selections remain in the local app."""
from datetime import date
import calendar,re

def month_date(value,months):
 d=date.fromisoformat(value);offset=d.year*12+d.month-1+months;y,m=divmod(offset,12);m+=1
 return date(y,m,min(d.day,calendar.monthrange(y,m)[1])).isoformat()

def validate_sanctions(catalog,selected):
 if not isinstance(selected,list)or len(selected)>20:raise ValueError('Check the sanction selections.')
 counts={};used=set()
 for selection in selected:
  if not isinstance(selection,dict):raise ValueError('Check the sanction selections.')
  item=next((x for x in catalog['sanctions']if x['id']==selection.get('id')),None)
  if not item or item['id']in used:raise ValueError('Choose each sanction at most once.')
  used.add(item['id']);group=item['category'];counts[group]=counts.get(group,0)+1
  if group in ('disciplinary','educational')and counts[group]>1:raise ValueError('Choose at most one '+group+' sanction, or None.')
 return counts

def validate_sanction_decisions(catalog,choices,complete=False):
 counts=validate_sanctions(catalog,choices.get('sanctions',[]));decisions=choices.get('sanction_decisions',{})
 if not isinstance(decisions,dict):raise ValueError('Check the sanction decisions.')
 for group in ('disciplinary','educational','academic'):
  decision=decisions.get(group,'selected'if counts.get(group)else'')
  if decision not in ('','none','selected'):raise ValueError('Check the '+group+' sanction decision.')
  if decision=='none'and counts.get(group):raise ValueError('None cannot be combined with a '+group+' sanction.')
  if complete and(decision==''or decision=='selected'and not counts.get(group)):raise ValueError('Choose a '+group+' sanction or explicitly select None.')
 return counts

def probation_end(params,label):
 mode=params.get('PROBATION MODE','')
 if not mode:return str(params.get('PROBATION END','')).strip()or'[PROBATION END]'
 if mode=='date':
  value=str(params.get('PROBATION DATE','')).strip()
  if not value:return'[PROBATION END]'
  try:return label(date.fromisoformat(value).isoformat())
  except ValueError:raise ValueError('Enter a valid probation end date.')
 if mode not in ('beginning','end'):raise ValueError('Choose a probation end date, beginning, or end of semester.')
 value=str(params.get('PROBATION SEMESTER','')).strip()
 if not value:return'[PROBATION END]'
 match=re.fullmatch(r'(Spring|Summer|Fall|Winter)\s+(20\d{2})',value,re.I)
 if not match:raise ValueError('Enter a semester such as Fall 2026.')
 return 'the '+mode+' of the '+match[1].title()+' '+match[2]+' semester'

def compose(catalog,case,letter,choices,days,label):
 kind=letter['outcome_kind'];assessment=next((str(v).strip()for v in (choices.get('assessment'),letter.get('assessment'),case.get('assessment'))if v and str(v).strip()and not re.search(r'\[[A-Z][A-Z _-]*\]',str(v))),'[ASSESSMENT]')
 course=case['course'];course=('Math '+course)if course.isdigit()else course
 values={'ASSESSMENT':assessment,'COURSE':course or'[COURSE]','SEMESTER':case['semester']or'[SEMESTER]'}
 def fill(t,extra=None):
  for k,v in {**values,**(extra or{})}.items():t=t.replace('['+k+']',str(v))
  return t
 if kind=='not-responsible':return fill(catalog['not_responsible']),{'assessment':assessment,'effective_outcome_kind':kind}
 violations=choices.get('violations',[]);selected=choices.get('sanctions',[])
 if not isinstance(violations,list)or not isinstance(selected,list):raise ValueError('Check the violation and sanction selections.')
 if len(violations)>30 or len(selected)>20:raise ValueError('Too many selections.')
 validate_sanction_decisions(catalog,choices)
 lines=[]
 for v in violations:
  cat=str(v.get('category','')).strip();level=str(v.get('level','')).strip();description=str(v.get('description','')).strip()
  if not cat:continue
  if level not in ('1','2','3'):raise ValueError('Select a level for each violation.')
  lines.append('- '+cat+' — Level '+level+(': '+description if description else''))
 sanction_text=[];serious=kind=='responsible-serious';used=set()
 for selection in selected:
  sid=selection.get('id');item=next((x for x in catalog['sanctions']if x['id']==sid),None)
  if not item or sid in used:raise ValueError('Check the selected sanctions.')
  used.add(sid);serious=serious or item['serious'];params=selection.get('parameters',{})
  if not isinstance(params,dict):raise ValueError('Check sanction details.')
  extra={k:str(params.get(k,'')).strip()or'['+k+']'for k in item['fields']}
  for key in ('PENALTY','NUMBER'):
   if key in extra and not extra[key].startswith('['):
    try:number=float(extra[key])
    except ValueError:raise ValueError('Enter a numeric penalty.')
    if number<=0 or (key=='NUMBER'and(not number.is_integer()or number>6))or(key=='PENALTY'and number>100):raise ValueError('Check the penalty amount.')
  if sid=='probation':extra['PROBATION END']=probation_end(params,label)
  if sid=='xf':
   if not case.get('incident_date'):raise ValueError('Enter the incident date in Overview to calculate the 18-month XF eligibility date.')
   extra['X-REMOVAL ELIGIBILITY DATE']=label(month_date(case['incident_date'],18))
  if sid in ('canvas','reflection'):
   deadline=label(days(letter['date'],15));extra['COMPLETION DEADLINE']=deadline;extra['REFLECTION DEADLINE']=deadline
  sanction_text.append(item['label']+'\n'+fill(item['body'],extra))
 rationale=str(choices.get('rationale','')).strip()or'[APPROVED CASE-SPECIFIC RATIONALE]'
 if serious:
  procedure=str(choices.get('hearing_text','')).strip()or catalog['serious_hearing'];heading='Hearing and response options'
  procedure=procedure.replace('[RESPONSE DEADLINE]',label(days(letter['date'],10)))
 else:procedure=fill(catalog['standard_appeal'],{'APPEAL DEADLINE':label(days(letter['date'],10))});heading='Appeal information'
 body='\n\n'.join([fill(catalog['responsible_opening']),'Violations','\n'.join(lines)or'[VIOLATIONS, LEVELS, AND DESCRIPTIONS]','Rationale',rationale,'Recommended sanctions','\n\n'.join(sanction_text)or('No sanctions are imposed.'if all(choices.get('sanction_decisions',{}).get(g)=='none'for g in ('disciplinary','educational','academic'))else'[SELECT SANCTIONS]'),heading,procedure,catalog['contact']])
 return body,{'assessment':assessment,'effective_outcome_kind':'responsible-serious'if serious else'responsible-standard'}
