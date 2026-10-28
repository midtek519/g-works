"""Version-scoped answer grouping and explicit human rubric decisions.

Groups never imply a grade. Recognition is grouped only by a readable final
answer, never by a model's score. Every mutation is stale-checked under the store
lock. Human decisions remain reviews of retained proposals, including manual
proposals created without any AI request.
"""
import copy
import json
import secrets
import re
from datetime import datetime,timezone

import response_grading as response
from consistency import rubric_score
from math_answers import canonical_math


def stamp():return datetime.now(timezone.utc).isoformat()
def token():return secrets.token_hex(16)
def packed(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
MANUAL={'pipeline':response.PIPELINE,'model':'instructor','digest':'manual','thinking':False,'budget':0,'context':0}


def grouping_key(q,result,bid):
    """Unclear/unsupported/free-response work always starts in separate groups."""
    c=response.normalize(q.get('response')) or {'type':'free_response'}
    value=result.get('recognition',{}) if result else {}
    if c['type'] in ('manual','free_response') or value.get('state') not in ('clear','blank'):
        return ('single',bid),'Needs review' if c['type'] not in ('manual','free_response') else 'Individual answer','uncertain'
    if value['state']=='blank':
        if value.get('selected') or value.get('text'):return ('single',bid),'Needs review','uncertain'
        return ('blank',),'Blank response','blank'
    if c['type'] in ('single_choice','multiple_choice'):
        selected=value.get('selected')
        if not isinstance(selected,list) or not selected or any(x not in c['options'] for x in selected) or len(selected)!=len(set(selected)):return ('single',bid),'Needs review','uncertain'
        labels=tuple(x for x in c['options'] if x in selected)
        return ('choices',labels),' + '.join(labels),'recognized'
    text=value.get('text')
    if not isinstance(text,str) or not text.strip():return ('single',bid),'Needs review','uncertain'
    try:
        if c.get('comparison')=='math':key=canonical_math(text)
        elif c.get('comparison')=='numeric':key=('number',str(response.number(text)))
        else:key=('text',response.text_form(text))
    except ValueError:return ('single',bid),'Needs review','uncertain'
    return key,text[:120],'recognized'


class AnswerGroups:
    def answer_groups_init(self):
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS answer_groups(question_id TEXT PRIMARY KEY,context_hash TEXT NOT NULL,groups_json TEXT NOT NULL,updated TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS reviewed_examples(id TEXT PRIMARY KEY,question_id TEXT NOT NULL,context_hash TEXT NOT NULL,note TEXT NOT NULL,choices TEXT NOT NULL,created TEXT NOT NULL)')

    def _example_context(self,v,q):
        return response.sha({'version':v['label'],'question':{k:x for k,x in q.items() if k not in ('checkedFiles','responseKey')},'sources':[{k:f[k] for k in ('id','sha256','layout')} for f in v['files']]})

    def _validate_example(self,v,q,note):
        if response.kind(q)!='free_response' or not note.strip():raise ValueError('Add a mathematical explanation for this free-response example.')
        if len(note)>700 or re.search(r'@|https?://|[A-Za-z]:[\\/]|\b(?:netid|student id|ruid)\b',note,re.I):raise ValueError('Use a short mathematical note without identities, addresses or file paths.')
        people,_=self._roster_students(v['project_id'])
        lowered=note.casefold()
        for person in people:
            values=[person.get('name',''),person.get('netid','')]+person.get('emails',[])
            if any(value and re.search(r'(?<!\w)'+re.escape(value.casefold())+r'(?!\w)',lowered) for value in values):raise ValueError('Remove student identity details before sharing a mathematical example with local grading.')

    def reviewed_examples_snapshot(self,v):
        result={}
        for q in v['questions']:
            rows=self.rows('SELECT note,choices FROM reviewed_examples WHERE question_id=? AND context_hash=? ORDER BY created DESC,rowid DESC LIMIT 6',(q['id'],self._example_context(v,q)))
            if rows:result[q['id']]=[{'instructorNote':r['note'],'rubricItems':json.loads(r['choices'])} for r in rows]
        return result

    def grading_setup(self,qid,payload):
        with self.lock:
            row=self.one('questions',qid);vid=row['version_id'];self.writable(vid)
            if self.active or self.archive_busy():raise ValueError('Wait for active work before changing grading setup.')
            if not isinstance(payload,dict) or payload.get('reviewed') is not True:raise ValueError('Review the grading setup before saving.')
            if type(payload.get('applyToAllVersions',False)) is not bool:raise ValueError('Choose whether to apply this setup to all versions.')
            v=self.version(vid)
            if payload.get('projectId',v['project_id'])!=v['project_id']:raise ValueError('Choose a question in this assignment.')
            q=next(q for q in v['questions'] if q['id']==qid)
            config=response.normalize(payload.get('response'))
            if config is None:raise ValueError('Choose a question format.')
            def validate(question,settings):
                rect=question.get('rect');regions=([settings['answerRegion']] if settings.get('answerRegion') else [])+[r['rect'] for r in settings.get('markRegions',[])]
                if regions and (not rect or any(r[0]<rect[0]-1e-9 or r[1]<rect[1]-1e-9 or r[2]>rect[2]+1e-9 or r[3]>rect[3]+1e-9 for r in regions)):raise ValueError('Keep every answer region inside the saved question box.')
                if settings.get('markRegions'):
                    if settings['type'] not in ('single_choice','multiple_choice') or {r['label'] for r in settings['markRegions']}!=set(settings['options']):raise ValueError('Draw one choice region for each option label.')
                    first=settings['markRegions'][0]['rect'];size=(first[2]-first[0],first[3]-first[1])
                    if any(abs((r['rect'][2]-r['rect'][0])-size[0])>1e-6 or abs((r['rect'][3]-r['rect'][1])-size[1])>1e-6 for r in settings['markRegions']):raise ValueError('Choice regions must have equal sizes.')
                if settings.get('answerRegion') and settings['type']!='fill_in':raise ValueError('Use a final-answer region only for fill-in questions.')
            validate(q,config)
            updated=copy.deepcopy(q);updated['response']=config
            updated['response'],_=response.resolve_correct(updated,v['label'])
            planned=[(v,updated)];skipped=[]
            if payload.get('applyToAllVersions'):
                def mapped(rect,target):
                    a=q['rect'];b=target['rect']
                    return [round(b[i%2]+(rect[i]-a[i%2])/(a[2+i%2]-a[i%2])*(b[2+i%2]-b[i%2]),12) for i in range(4)]
                for entry in self.rows("SELECT id FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(v['project_id'],)):
                    if entry['id']==vid:continue
                    self.writable(entry['id']);target=self.version(entry['id'])
                    matches=[item for item in target['questions'] if item['key']==q['key']]
                    if len(matches)!=1:
                        skipped.append({'versionLabel':target['label'],'reason':'No matching question.'});continue
                    prior=matches[0];shared=copy.deepcopy(prior)
                    shared['response']=response.shared_response(updated['response'],prior.get('response'))
                    if config.get('answerRegion') or config.get('markRegions'):
                        if not prior.get('rect'):
                            skipped.append({'versionLabel':target['label'],'reason':'Save this question box before sharing answer regions.'});continue
                        for field in ('answerRegion','markRegions'):shared['response'].pop(field,None)
                        if config.get('answerRegion'):shared['response']['answerRegion']=mapped(config['answerRegion'],prior)
                        if config.get('markRegions'):shared['response']['markRegions']=[{'label':r['label'],'rect':mapped(r['rect'],prior)} for r in config['markRegions']]
                    else:
                        for field in ('answerRegion','markRegions'):shared['response'].pop(field,None)
                    referenced={config.get('correctLabel'),config.get('incorrectLabel')}|{r['label'] for r in config.get('partialRules',[])}
                    referenced.discard(None);referenced.discard('')
                    source_items={i['label']:i['points'] for i in q['items']};target_items={i['label']:i['points'] for i in prior['items']}
                    if q['selectionMode']!=prior['selectionMode'] or any(label not in target_items or source_items.get(label)!=target_items[label] for label in referenced):
                        skipped.append({'versionLabel':target['label'],'reason':'The rubric score mapping differs.'});continue
                    shared['response']=response.normalize(shared['response']);validate(shared,shared['response'])
                    shared['response'],_=response.resolve_correct(shared,target['label'])
                    planned.append((target,shared))
            # Preflight every destination before the single commit; saved histories remain.
            applied=[]
            with self.connect() as db:
                for version,question in planned:
                    approved=version['rubric_approved']==self.rubric_hash(version)
                    questions=[question if item['id']==question['id'] else item for item in version['questions']]
                    db.execute('UPDATE questions SET data=? WHERE id=?',(packed({k:x for k,x in question.items() if k not in ('id','responseKey')}),question['id']))
                    if approved:db.execute('UPDATE versions SET rubric_approved=? WHERE id=?',(self.rubric_hash({'questions':questions}),version['id']))
                    self.event(db,'question-grading-setup-saved',question['id'],{'type':config['type'],'grouping':config.get('grouping','individual'),'sourceVersionId':vid})
                    applied.append({'versionId':version['id'],'versionLabel':version['label']})
            result=self.version(vid)
            result['gradingSetupShared']={'applied':applied,'skipped':skipped,'versionAnswerKeysPreserved':True}
            return result

    def _answer_group_data(self,qid):
        row=self.one('questions',qid);v=self.version(row['version_id']);q=next(q for q in v['questions'] if q['id']==qid)
        settings=self._grading_profile(v['id']);index,_=self._assessment_index(v,settings,include_unfinished=True)
        from grading_control import question_hash
        context=response.sha({'questionContext':question_hash(self.snapshot(v),q,MANUAL),'recognition':[(b['id'],index.get((qid,b['id']),{}).get('result',{}).get('recognition')) for b in v['booklets']]})
        saved=self.rows('SELECT * FROM answer_groups WHERE question_id=?',(qid,))
        groups=json.loads(saved[0]['groups_json']) if saved and saved[0]['context_hash']==context else []
        valid={b['id'] for b in v['booklets']}
        groups=[{**g,'memberIds':[x for x in g['memberIds'] if x in valid]} for g in groups]
        groups=[g for g in groups if g['memberIds']]
        members=[]
        for i,b in enumerate(v['booklets']):
            p=index.get((qid,b['id']));result=p['result'] if p else None;review=p.get('review') if p else None
            identity={}
            try:identity=self.export_student_identities(v['id'],[b['id']])[0][b['id']]
            except ValueError:pass
            ids=review['choices'] if review else result.get('items',[]) if result else []
            score=rubric_score(q,ids) if p else None
            members.append({'id':b['id'],'bookletId':b['id'],'label':'Exam '+str(i+1),'name':identity.get('name','Not matched to a student'),'section':identity.get('section',''),'proposalId':p['id'] if p else None,'runId':p['run_id'] if p else None,'result':result,'review':({**review,'score':score} if review else None),'score':score,'cropUrl':'/api/crop?bookletId='+b['id']+'&questionId='+qid,'processed':bool(result and result.get('method')!='manual')})
        membermap={m['id']:m for m in members}
        for g in groups:
            g['name']=g['label'];g['bookletIds']=g['memberIds'];g['count']=len(g['memberIds']);g['reviewed']=all(membermap[i]['review'] for i in g['memberIds'])
        revision=response.sha({'context':context,'groups':groups,'results':[(m['id'],m['proposalId'],m['review']['id'] if m['review'] else '') for m in members]})
        value={'questionId':qid,'versionId':v['id'],'projectId':v['project_id'],'question':q,'groups':groups,'members':members,'submissions':members,'processed':sum(m['processed'] for m in members),'reviewed':sum(bool(m['review']) for m in members),'total':len(members),'current':not saved or saved[0]['context_hash']==context,'revision':revision}
        return value,v,q,context,index

    def answer_groups(self,qid,project_id=None):
        with self.lock:
            data=self._answer_group_data(qid)[0]
            if project_id is not None and project_id!=data['projectId']:raise ValueError('Choose a question in this assignment.')
            return data

    def change_answer_groups(self,qid,payload,*,_project=None):
        with self.lock:
            data,v,q,context,index=self._answer_group_data(qid)
            if _project is not None:
                batches=self.rows('SELECT project_id FROM project_batches WHERE id=?',(_project,))
                if _project!=self.project_queue_active or not batches or batches[0]['project_id']!=v['project_id'] or payload.get('action')!='build':raise ValueError('Choose the active project queue for group creation.')
            else:self.writable(v['id'])
            if self.active or self.archive_busy(ignore_project=_project is not None):raise ValueError('Wait for active work before editing answer groups.')
            if payload.get('projectId',v['project_id'])!=v['project_id']:raise ValueError('Choose a question in this assignment.')
            if payload.get('revision')!=data['revision']:raise ValueError('These answers changed. Refresh and review the current answers.')
            action=payload.get('action');groups=copy.deepcopy(data['groups']);byid={g['id']:g for g in groups};members={m['id']:m for m in data['members']}
            def label(default):
                value=payload.get('label',default)
                if not isinstance(value,str) or not value.strip() or len(value)>160:raise ValueError('Enter a group name of at most 160 characters.')
                return value.strip()
            def selected(field,available):
                ids=payload.get(field)
                if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids) or set(ids)-set(available):raise ValueError('Choose current answers or groups from this question.')
                return ids
            def group():
                if not isinstance(payload.get('groupId'),str) or payload['groupId'] not in byid:raise ValueError('Choose a current answer group.')
                return byid[payload['groupId']]
            if action=='build':
                buckets={};groups=[]
                for m in data['members']:
                    key,name,kind=grouping_key(q,m['result'],m['id'])
                    if key not in buckets:
                        g={'id':token(),'label':name,'kind':kind,'memberIds':[]};groups.append(g);buckets[key]=g
                    buckets[key]['memberIds'].append(m['id'])
            elif action=='rename':group()['label']=label('Answers')
            elif action=='merge':
                ids=selected('groupIds',byid)
                if len(ids)<2:raise ValueError('Select at least two groups to merge.')
                merged=[i for gid in ids for i in byid[gid]['memberIds']]
                groups=[g for g in groups if g['id'] not in ids]+[{'id':token(),'label':label('Merged answers'),'kind':'manual','memberIds':merged}]
            elif action=='split':
                old=group();ids=selected('memberIds',old['memberIds'])
                old['memberIds']=[i for i in old['memberIds'] if i not in ids]
                groups.append({'id':token(),'label':label('Split answers'),'kind':'manual','memberIds':ids})
            elif action=='move':
                target=group();ids=selected('memberIds',members)
                for g in groups:g['memberIds']=[i for i in g['memberIds'] if i not in ids]
                target['memberIds']+=ids;target['kind']='manual'
            elif action=='grade':
                ids=list(group()['memberIds']) if payload.get('groupId') else selected('bookletIds',members)
                if payload.get('reviewed') is not True:raise ValueError('Review every selected answer before assigning rubric items.')
                choices=selected('choices',{i['id'] for i in q['items']})
                if q['selectionMode']=='one' and len(choices)!=1:raise ValueError('Choose exactly one rubric item.')
                note=payload.get('note','')
                if not isinstance(note,str) or len(note)>2000:raise ValueError('Keep the review note within 2,000 characters.')
                example=payload.get('example',False)
                if type(example) is not bool:raise ValueError('Choose whether to save a reviewed example.')
                if example:self._validate_example(v,q,note)
                self.validate_ready(v,template_crops=True,question_ids=[qid])
                snapshot=self.snapshot(v);snapshot['questions']=[x for x in snapshot['questions'] if x['id']==qid]
                snapshot['grading']={'schema':2,'profile':MANUAL,'targets':[[qid,b] for b in ids]}
                missing=[b for b in ids if (qid,b) not in index];rid=token();created=stamp()
                with self.connect() as db:
                    if missing:db.execute('INSERT INTO runs(id,version_id,snapshot_hash,model,model_digest,status,created,snapshot) VALUES(?,?,?,?,?,?,?,?)',(rid,v['id'],response.sha(snapshot),'instructor','manual','complete',created,packed(snapshot)))
                    for bid in ids:
                        p=index.get((qid,bid));pid=p['id'] if p else token()
                        if not p:
                            result={'items':[],'reason':'Instructor-reviewed answer; no AI assessment.','uncertainty':'','needsReview':True,'method':'manual'}
                            db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?)',(pid,rid,bid,qid,packed(result),created))
                        db.execute('INSERT INTO reviews VALUES(?,?,?,?,?)',(token(),pid,packed(choices),note,created))
                    if example:db.execute('INSERT INTO reviewed_examples VALUES(?,?,?,?,?,?)',(token(),qid,self._example_context(v,q),note,packed(choices),created))
                    self.event(db,'answer-group-reviewed',qid,{'answers':len(ids),'groupId':payload.get('groupId')})
                return self._answer_group_data(qid)[0]
            else:raise ValueError('Choose a supported answer-group action.')
            groups=[{k:g[k] for k in ('id','label','kind','memberIds')} for g in groups if g['memberIds']]
            flat=[x for g in groups for x in g['memberIds']]
            if len(flat)!=len(set(flat)) or set(flat)-set(members):raise ValueError('An answer cannot occur in more than one group.')
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO answer_groups VALUES(?,?,?,?)',(qid,context,packed(groups),stamp()));self.event(db,'answer-groups-'+action,qid,{'groups':len(groups)})
            return self._answer_group_data(qid)[0]
