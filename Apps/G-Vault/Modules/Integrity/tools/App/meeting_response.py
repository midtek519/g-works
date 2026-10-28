"""Explicitly recorded student response routes; no inferred procedural decisions."""
from copy import deepcopy
from datetime import date

STATUSES={'awaiting','scheduled','no_response','written'}

def response_required(case):
    meeting=next((s for s in case.get('steps',[]) if s['id']=='meeting'),{})
    return bool(case.get('meeting_response')) or not (case.get('closed') or meeting.get('done') or meeting.get('skipped'))

def meeting_needed(case):
    return case.get('meeting_response',{}).get('status') not in ('no_response','written')

def checklist_progress(case):
    steps=[s for s in case.get('steps',[]) if not s.get('optional') and (s['id']!='meeting' or meeting_needed(case))]
    extra=response_required(case)
    recorded=case.get('meeting_response',{}).get('status') in ('scheduled','no_response','written')
    return sum(bool(s.get('done') or s.get('skipped')) for s in steps)+int(extra and recorded),len(steps)+int(extra)

def save_response(case,payload,stamp,today=None):
    today=today or date.today()
    if not isinstance(payload,dict) or payload.get('status') not in STATUSES:raise ValueError('Choose how the student responded.')
    status=payload['status']
    def text(key,limit):
        value=payload.get(key,'')
        if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in value):raise ValueError('Check the meeting response fields.')
        return value.strip()
    def day(key):
        value=text(key,10)
        if value:
            try:date.fromisoformat(value)
            except ValueError:raise ValueError('Use dates in YYYY-MM-DD form.') from None
        return value
    record={'status':status,'response_deadline':day('response_deadline'),'meeting_date':day('meeting_date'),'meeting_time':text('meeting_time',5),'response_date':day('response_date'),'notes':text('notes',10000),'recorded_at':stamp}
    contact=next((s for s in case.get('steps',[]) if s['id']=='contact'),{})
    if status!='awaiting' and not contact.get('done'):raise ValueError('Confirm the initial contact was sent before recording the response.')
    if record['response_date'] and date.fromisoformat(record['response_date'])>today:raise ValueError('The response or confirmation date cannot be in the future.')
    if status=='scheduled':
        if not record['meeting_date']:raise ValueError('Enter the arranged meeting date.')
        if record['meeting_time']:
            import re
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',record['meeting_time']):raise ValueError('Use a valid meeting time.')
    elif status=='no_response':
        if payload.get('confirmed_no_response') is not True:raise ValueError('Confirm that the deadline passed without a student response.')
        if not record['response_deadline'] or not record['response_date']:raise ValueError('Enter the response deadline and the date you checked for a reply.')
        deadline=date.fromisoformat(record['response_deadline']);checked=date.fromisoformat(record['response_date'])
        if deadline>=checked or checked>today:raise ValueError('Record no response after the response deadline has passed.')
        record['confirmed_no_response']=True
    elif status=='written' and not record['response_date']:raise ValueError('Enter the date the written response was received.')
    if status!='scheduled':record.update(meeting_date='',meeting_time='')
    if status=='awaiting':record['response_date']=''
    previous=case.get('meeting_response')
    if previous:case.setdefault('meeting_response_history',[]).append(deepcopy(previous))
    case['meeting_response']=record
    return record
