"""Question-scoped local grading, retained partial runs and compatible-result reuse."""
import base64,copy,hashlib,json,secrets,threading,time
from datetime import datetime,timezone
import local_ai
import response_grading as response
from consistency import grading_schema,grading_guidance,resolve_consistency

def stamp():return datetime.now(timezone.utc).isoformat()
def packed(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
def fingerprint(value):return hashlib.sha256(packed(value).encode()).hexdigest()
def token():return secrets.token_hex(16)
EXTENDED_REASONING_TOKENS=8192

def profile(model,digest,thinking):
 return {'pipeline':response.PIPELINE,'model':model,'digest':digest,'thinking':bool(thinking),'budget':EXTENDED_REASONING_TOKENS if thinking else 600,'context':16384 if thinking else 8192}
def legacy_profile(model,digest,thinking):
 return {**profile(model,digest,thinking),'pipeline':1}
def question_profile(question,settings):
 # Saved per-question reasoning owns current readiness/reuse. Older questions
 # without that setting retain the run-level option as their fallback.
 config=question.get('response') or {}
 if settings.get('provider')=='chatgpt':return settings
 if settings.get('model')!='instructor' and settings.get('pipeline')==response.PIPELINE and response.kind(question) in ('single_choice','multiple_choice'):
  from choice_marks import READER
  return {**settings,'choiceReader':READER}
 if settings.get('model')!='instructor' and settings.get('pipeline')==response.PIPELINE and response.kind(question)=='free_response' and 'thinking' in config:
  return {**settings,**{k:v for k,v in profile(settings['model'],settings['digest'],config['thinking']).items() if k in ('thinking','budget','context')}}
 return settings
def recorded_profile(snapshot,question,settings):
 # Never reinterpret an older run: absent a saved per-question profile, its
 # actual inference used the single profile recorded at the time.
 if settings.get('pipeline')!=response.PIPELINE:return settings
 return snapshot.get('grading',{}).get('questionProfiles',{}).get(question['id'],settings)
def question_hash(snapshot,question,settings):
 q={k:v for k,v in question.items() if k not in ('checkedFiles','responseKey')}
 if response.kind(question)!='free_response' and settings.get('pipeline')==response.PIPELINE:settings={**settings,'thinking':False,'budget':220,'context':8192}
 policy=(snapshot.get('consistency') or {}).get('questions',{}).get(question['key'],{}).get('rules',[])
 return fingerprint({'exam':{k:snapshot.get(k) for k in ('course','term','exam','version')},'files':snapshot['files'],'booklets':snapshot['booklets'],'question':q,'rules':policy,'materials':snapshot.get('materials',[]),'handoutRef':snapshot.get('handoutRef',{}),'unavailableFiles':snapshot.get('unavailableFiles',[]),'profile':settings,'examples':[] if settings.get('model')=='instructor' else snapshot.get('reviewedExamples',{}).get(question['id'],[])})

class GradingControl:
 def grading_init(self):
  self.grading_clocks={};self.grading_model_cache={}
  with self.connect() as db:
   cols={r[1] for r in db.execute('PRAGMA table_info(runs)')}
   for name,definition in [('elapsed_seconds','REAL NOT NULL DEFAULT 0'),('session_seconds','REAL NOT NULL DEFAULT 0'),('session_started',"TEXT NOT NULL DEFAULT ''"),('finished',"TEXT NOT NULL DEFAULT ''")]:
    if name not in cols:db.execute('ALTER TABLE runs ADD COLUMN '+name+' '+definition)
   db.execute('CREATE TABLE IF NOT EXISTS grading_preferences(version_id TEXT PRIMARY KEY,model TEXT NOT NULL,model_digest TEXT NOT NULL,thinking INTEGER NOT NULL)')
 def _grading_model(self,model,thinking,force=False):
  if self.complete is not local_ai.complete:return profile(model,'fictional',thinking)
  import local_ai_config
  cache=self.grading_model_cache.get(model)
  if force or not cache or time.monotonic()-cache[0]>15:
   info=local_ai.validate_model(model,True)
   item=next((m for m in local_ai.models() if m['name']==model),None)
   if not item:raise ValueError('The configured local grading model is unavailable.')
   self.grading_model_cache[model]=(time.monotonic(),item['digest'],info)
  _,digest,info=self.grading_model_cache[model]
  if thinking and (local_ai_config.settings()['provider']!='ollama' or ('thinking' not in info.get('capabilities',[]) and True not in info.get('thinking',{}).get('values',[]))):
   raise ValueError('Choose a thinking-capable local Ollama model or turn off thinking for this run.')
  return profile(model,digest,thinking)
 def _grading_profile(self,vid):
  saved=self.rows('SELECT * FROM grading_preferences WHERE version_id=?',(vid,))
  if saved:
   r=saved[0]
   try:return self._grading_model(r['model'],bool(r['thinking']))
   except ValueError:return profile(r['model'],r['model_digest'],bool(r['thinking']))
  latest=self.rows("SELECT model,model_digest,snapshot FROM runs WHERE version_id=? AND model!='instructor' AND model_digest NOT LIKE 'chatgpt:%' ORDER BY created DESC,rowid DESC LIMIT 1",(vid,))
  if latest:
   r=latest[0];prior=json.loads(r['snapshot']).get('grading',{}).get('profile',legacy_profile(r['model'],r['model_digest'],False))
   try:return self._grading_model(prior['model'],prior['thinking'])
   except ValueError:return prior
  from answer_groups import MANUAL
  return dict(MANUAL)
 def grading_snapshot_compatible(self,v,snapshot,settings,old_settings):
  current=self.snapshot(v);lookup={q['id']:q for q in current['questions']}
  return all(q['id'] in lookup and question_hash(snapshot,q,recorded_profile(snapshot,q,old_settings))==question_hash(current,lookup[q['id']],question_profile(lookup[q['id']],settings)) for q in snapshot['questions'])
 def _question_ids(self,v,payload):
  ids=payload.get('questionIds',[q['id'] for q in v['questions'] if response.kind(q)!='manual'])
  if not isinstance(ids,list) or not ids or len(ids)>100 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids) or set(ids)-{q['id'] for q in v['questions']}:
   raise ValueError('Select one or more saved questions from this version.')
  if any(response.kind(q)=='manual' for q in v['questions'] if q['id'] in ids):raise ValueError('Manual questions are reviewed directly; choose an AI response format to process them.')
  return [q['id'] for q in v['questions'] if q['id'] in ids]
 def _assessment_index(self,v,settings,*,include_unfinished=False):
  current=self.snapshot(v);expected={q['id']:question_hash(current,q,question_profile(q,settings)) for q in v['questions']}
  runs=self.rows('SELECT * FROM runs WHERE version_id=? ORDER BY created DESC,rowid DESC',(v['id'],))
  # Online approval selects a provider for this question only. Other questions
  # retain their local model and reviewed results. A later local run switches
  # that question back without changing any unrelated question.
  online_profiles={};seen=set()
  for r in runs:
   if r['status']=='discarded' or r['model']=='instructor':continue
   snap=json.loads(r['snapshot']);base=snap.get('grading',{}).get('profile',{})
   for q in snap['questions']:
    if q['id'] in seen:continue
    seen.add(q['id']);selected=recorded_profile(snap,q,base)
    if selected.get('provider')=='chatgpt':online_profiles[q['id']]=selected
  expected.update({q['id']:question_hash(current,q,online_profiles[q['id']]) for q in v['questions'] if q['id'] in online_profiles})
  by_run={r['id']:r for r in runs};snapshots={};compatible={}
  for r in runs:
   snap=json.loads(r['snapshot']);snapshots[r['id']]=snap
   previous=snap.get('grading',{}).get('profile',legacy_profile(r['model'],r['model_digest'],False))
   if previous.get('model')=='instructor':
    from answer_groups import MANUAL
    current_q={q['id']:q for q in current['questions']}
    compatible[r['id']]={q['id'] for q in snap['questions'] if q['id'] in current_q and question_hash(current,current_q[q['id']],MANUAL)==question_hash(snap,q,MANUAL)}
   else:compatible[r['id']]={q['id'] for q in snap['questions'] if expected.get(q['id'])==question_hash(snap,q,recorded_profile(snap,q,previous))}
  # Keep the latest review, independently of proposal/run order.
  review_rows=self.rows("""SELECT w.* FROM reviews w JOIN proposals p ON p.id=w.proposal_id JOIN runs r ON r.id=p.run_id
   WHERE r.version_id=? ORDER BY w.created,w.rowid""",(v['id'],))
  reviews={r['proposal_id']:r for r in review_rows}
  valid_booklets={b['id'] for b in v['booklets']};index={};history=set()
  for r in runs:
   if r['status']=='discarded':continue
   for p in self.rows('SELECT * FROM proposals WHERE run_id=? ORDER BY created DESC,rowid DESC',(r['id'],)):
    pair=(p['question_id'],p['booklet_id'])
    if p['booklet_id'] not in valid_booklets:continue
    history.add(pair)
    accepted=p['question_id'] in compatible[r['id']]
    if not accepted and p['id'] in reviews:
     from answer_groups import MANUAL
     oldq=next((q for q in snapshots[r['id']]['questions'] if q['id']==p['question_id']),None);newq=next((q for q in current['questions'] if q['id']==p['question_id']),None)
     accepted=bool(oldq and newq and question_hash(snapshots[r['id']],oldq,MANUAL)==question_hash(current,newq,MANUAL))
    if pair in index or r['status'] not in (('complete','saved','running','paused','error') if include_unfinished else ('complete','saved')) or not accepted:continue
    p['result']=json.loads(p['result']);p['review']=reviews.get(p['id'])
    if p['review']:p['review']={**p['review'],'choices':json.loads(p['review']['choices'])}
    index[pair]=p
  return index,history
 def grading_status(self,vid,thinking=False,project_export=True):
  v=self.version(vid);settings=None;model_error='';thinking_error=''
  try:
   base=self._grading_model(local_ai.DEFAULT_MODEL,False)
   settings=profile(base['model'],base['digest'],thinking)
   if any(response.kind(q)=='free_response' and question_profile(q,settings)['thinking'] for q in v['questions']):
    try:self._grading_model(local_ai.DEFAULT_MODEL,True)
    except ValueError as e:thinking_error=str(e)
  except ValueError as e:model_error=str(e)
  selected_profile=self._grading_profile(vid)
  if selected_profile.get('provider')=='chatgpt':settings=selected_profile;model_error='';thinking_error=''
  index,history=self._assessment_index(v,settings or selected_profile)
  global_issues=[]
  try:self.require_gradescope_roster(v['project_id'])
  except ValueError as e:global_issues.append(str(e))
  scans=[f for f in v['files'] if f['kind']=='scans']
  if not scans or not v['booklets']:global_issues.append('Import scans and confirm their versions and boundaries.')
  elif any(not f['layout'].get('confirmed') or not f.get('available',True) for f in scans):global_issues.append('Confirm the active scan boundaries and availability.')
  if v['rubric_approved']!=self.rubric_hash(v):global_issues.append('Save and confirm the current rubric.')
  # Model availability is a question-level issue; manual review remains available.
  questions=[];policy=(self.consistency_snapshot(v) or {}).get('questions',{})
  for q in v['questions']:
   rules=policy.get(q['key'],{}).get('rules',[])
   issues=['Question '+q['key']+': '+message for message in response.issues(q,rules)]
   if model_error and response.kind(q)!='manual':issues.append(model_error)
   if thinking_error and response.kind(q)=='free_response' and question_profile(q,settings)['thinking']:issues.append(thinking_error)
   if not q.get('items'):issues.append('Missing rubric items.')
   if not q.get('rect'):issues.append('Missing question box in Exam outline.')
   elif any(q['page']>b['pages'] for b in v['booklets']):issues.append('Question page is outside an exam.')
   else:
    try:self.question_privacy_check(vid,[q])
    except ValueError as e:issues.append(str(e))
   n=sum((q['id'],b['id']) in index and index[(q['id'],b['id'])]['result'].get('method')!='manual' for b in v['booklets']);reviewed=sum(bool(index.get((q['id'],b['id']),{}).get('review')) for b in v['booklets']);old=sum((q['id'],b['id']) in history and (q['id'],b['id']) not in index for b in v['booklets'])
   questions.append({'id':q['id'],'key':q['key'],'title':q['title'],'responseType':response.kind(q),'issues':issues,'current':n,'reviewed':reviewed,'outdated':old,'total':len(v['booklets'])})
  export_ready=False;export_reason='Complete current results and confirm student matches for every populated version.'
  if project_export:
   try:
    for row in self.rows("SELECT id FROM versions WHERE project_id=? AND archived=''",(v['project_id'],)):
     other=v if row['id']==vid else self.version(row['id'])
     if not other['booklets']:continue
     target=self._grading_profile(other['id'])
     values,_=self._assessment_index(other,target)
     if len(values)!=len(other['booklets'])*len(other['questions']):raise ValueError(export_reason)
     self.export_student_identities(other['id'],[b['id'] for b in other['booklets']])
    export_ready=bool(v['booklets'])
   except ValueError as e:export_reason=str(e)
  return {'versionId':vid,'model':local_ai.DEFAULT_MODEL,'thinking':thinking,'questions':questions,'issues':global_issues,'submissions':len(v['booklets']),'activeRun':self.active,'activeBatch':self.project_queue_active,'questionVersionBatch':1,'exportReady':export_ready,'exportReason':'' if export_ready else export_reason}
 def start(self,vid,payload,*,_project=False):
  started=time.monotonic();started_at=stamp();self.require_gradescope_roster(self.one('versions',vid)['project_id'])
  with self.lock:
   if self.active:raise ValueError('A grading run is active. Pause it before starting another.')
   if self.project_queue_active and not _project:raise ValueError('Pause the project batch before starting a separate version run.')
   if self.archive_busy(ignore_project=_project,ignore_matching=True):raise ValueError('Finish the current scan operation before starting grading.')
   v=self.version(vid);resume=payload.get('resume')
   prior=self.one('runs',resume) if resume else None
   previous=json.loads(prior['snapshot']) if prior else None
   if previous and previous.get('grading',{}).get('profile',{}).get('provider')=='chatgpt':raise ValueError('Online grading requires a new crop review. Choose Grade online for this question to continue.')
   thinking=payload.get('thinking',previous.get('grading',{}).get('profile',{}).get('thinking',False) if previous else False)
   if type(thinking) is not bool or type(payload.get('redo',False)) is not bool:raise ValueError('Choose thinking and regrade options.')
   ids=self._question_ids(v,{'questionIds':[q['id'] for q in previous['questions']]} if previous else payload)
   thinking=thinking and any(response.kind(q)=='free_response' for q in v['questions'] if q['id'] in ids)
   model=payload.get('model',prior['model'] if prior else local_ai.DEFAULT_MODEL)
   provisional=profile(model,'',thinking)
   needs_thinking=any(response.kind(q)=='free_response' and question_profile(q,provisional)['thinking'] for q in v['questions'] if q['id'] in ids)
   verified=self._grading_model(model,needs_thinking,force=True);settings=profile(model,verified['digest'],thinking)
   if payload.get('useTemplateCrops') is True:v=self.apply_template_crops(vid,question_ids=ids)
   self.validate_ready(v,question_ids=ids)
   policy=(self.consistency_snapshot(v) or {}).get('questions',{})
   specs={q['id']:response.compile_spec(q,v['label'],policy.get(q['key'],{}).get('rules',[])) for q in v['questions'] if q['id'] in ids}
   if prior:
    if prior['version_id']!=vid or prior['status'] not in ('paused','error'):raise ValueError('Choose a paused run to resume.')
    old_profile=previous.get('grading',{}).get('profile',legacy_profile(prior['model'],prior['model_digest'],False))
    if not self.grading_snapshot_compatible(v,previous,settings,old_profile):
     raise ValueError('This run uses older sources, rubric, guidance, model or thinking settings. Regrade the affected questions instead.')
    rid=prior['id'];snapshot=previous;elapsed=prior['elapsed_seconds']
   else:
    index,_=self._assessment_index(v,settings)
    targets=[[q['id'],b['id']] for q in v['questions'] if q['id'] in ids for b in v['booklets'] if payload.get('redo') or (q['id'],b['id']) not in index]
    if not targets:raise ValueError('All selected questions already have current results. Choose Regrade selected questions for a fresh run.')
    snapshot=self.snapshot(v);snapshot['questions']=[q for q in snapshot['questions'] if q['id'] in ids]
    snapshot['grading']={'schema':2,'profile':settings,'questionProfiles':{q['id']:question_profile(q,settings) for q in snapshot['questions']},'targets':targets,'specifications':specs}
    rid=token();elapsed=0
    with self.connect() as db:db.execute('INSERT INTO runs(id,version_id,snapshot_hash,model,model_digest,status,created,snapshot) VALUES(?,?,?,?,?,?,?,?)',(rid,vid,fingerprint(snapshot),model,settings['digest'],'queued',started_at,packed(snapshot)))
   with self.connect() as db:
    db.execute("UPDATE runs SET status='queued',error='',session_started=?,session_seconds=0,finished='' WHERE id=?",(started_at,rid))
    db.execute('INSERT OR REPLACE INTO grading_preferences VALUES(?,?,?,?)',(vid,model,settings['digest'],int(thinking)))
    self.event(db,'grading-resumed' if resume else 'run-created',rid,{'thinking':thinking,'questionIds':ids})
   self.grading_clocks[rid]=(started,elapsed);self.active=rid;self.cancelled.discard(rid)
   threading.Thread(target=self._run,args=(rid,),daemon=True,name='exam-grader').start();return {'id':rid}
 def _run(self,rid):
  from grader import CHOICE_SCHEMA
  try:
   run=self.one('runs',rid);snapshot=json.loads(run['snapshot']);settings=snapshot.get('grading',{}).get('profile',legacy_profile(run['model'],run['model_digest'],False))
   targets=snapshot.get('grading',{}).get('targets',[[q['id'],b['id']] for q in snapshot['questions'] for b in snapshot['booklets']])
   qmap={q['id']:q for q in snapshot['questions']};bmap={b['id']:b for b in snapshot['booklets']}
   requests={}
   for qid,q in qmap.items():
    spec=snapshot['grading']['specifications'][qid]
    rules=spec.get('approvedDecisions',[])
    if response.kind(q)=='free_response':
     prompt=packed({k:v for k,v in spec.items() if k!='approvedDecisions'})+grading_guidance(rules)
     examples=self.reviewed_examples(snapshot,q,settings)
     if examples:prompt+='\nInstructor-reviewed rubric examples (compare visible work, never group by score alone):\n'+packed(examples)
     effective=recorded_profile(snapshot,q,settings)
     requests[qid]=(response.FR_SYSTEM,prompt,grading_schema(CHOICE_SCHEMA,rules),effective['budget'],effective['context'],effective['thinking'])
    else:
     system,prompt,schema=response.recognition_request(spec)
     requests[qid]=(system,prompt,schema,220,8192,False)
   with self.connect() as db:db.execute("UPDATE runs SET status='running' WHERE id=?",(rid,))
   for qid,bid in targets:
    if rid in self.cancelled:return
    if self.rows('SELECT id FROM proposals WHERE run_id=? AND booklet_id=? AND question_id=?',(rid,bid,qid)):continue
    begun=time.monotonic();q=qmap[qid];b=bmap[bid]
    rules=(snapshot.get('consistency') or {}).get('questions',{}).get(q['key'],{}).get('rules',[])
    source=self.one('files',b['file_id'])
    if hashlib.sha256(self.file_path(source).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('A scan changed. Reimport it and review the affected questions.')
    local_reading=None;mark_evidence=None
    if response.kind(q) in ('single_choice','multiple_choice'):crop,local_reading,mark_evidence=self.recognition_crop(bid,qid,details=True)
    else:crop=self.recognition_crop(bid,qid) if response.kind(q)!='free_response' else self.crop(bid,qid)
    spec=snapshot['grading']['specifications'][qid]
    system,prompt,schema,budget,context,thinking=requests[qid]
    if local_reading is not None:
     result=local_reading;stats={'reader':mark_evidence['reader'],'model_called':False,'eval_count':0,'prompt_eval_count':0}
    else:
     result,stats=self.complete(system,prompt,images=[base64.b64encode(crop).decode('ascii')],schema=schema,model=run['model'],max_tokens=budget,context=context,think=thinking,checked=True,temperature=0)
    if response.kind(q)=='free_response':
     result=resolve_consistency(q,rules,result)
     result.update(method='prepared_free_response',specificationHash=spec['hash'])
    else:
     result=response.score_recognition(spec,result)
     if mark_evidence:
      result['recognitionReader']=mark_evidence['reader'] if local_reading is not None else 'local_ai_fallback'
      result['regionEvidence']={key:mark_evidence[key] for key in ('reason','matched','measurements') if key in mark_evidence}
    allowed={i['id'] for i in q['items']};selected=result.get('items')
    if not isinstance(selected,list) or len(selected)>12 or len(set(selected))!=len(selected) or any(i not in allowed for i in selected) or type(result.get('needsReview')) is not bool or not isinstance(result.get('reason'),str) or not result['reason'].strip() or not isinstance(result.get('uncertainty'),str):raise ValueError('The local model returned an incomplete assessment. No partial result was saved.')
    result['reason']=result['reason'][:320];result['uncertainty']=result['uncertainty'][:500]
    result['needsReview']=result['needsReview'] or not selected or (q['selectionMode']=='one' and len(selected)!=1)
    result['stats']={**stats,'wall_seconds':round(time.monotonic()-begun,3)};result['cropHash']=hashlib.sha256(crop).hexdigest()
    # Pause is cooperative: retain the completed request before stopping.
    with self.connect() as db:db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?)',(token(),rid,bid,qid,packed(result),stamp()))
   with self.connect() as db:db.execute("UPDATE runs SET status='complete',finished=? WHERE id=?",(stamp(),rid));self.event(db,'run-complete',rid,{})
  except Exception as e:
   message=str(e)[:250] if isinstance(e,ValueError) else 'Local grading stopped. Check Ollama and resume; completed assessments were retained.'
   with self.connect() as db:db.execute("UPDATE runs SET status='error',error=?,finished=? WHERE id=?",(message,stamp(),rid))
  finally:
   with self.lock:
    begun,previous=self.grading_clocks.pop(rid,(time.monotonic(),0));session=max(0,time.monotonic()-begun)
    with self.connect() as db:
     db.execute('UPDATE runs SET elapsed_seconds=?,session_seconds=?,finished=? WHERE id=?',(previous+session,session,stamp(),rid))
     if rid in self.cancelled:db.execute("UPDATE runs SET status='paused' WHERE id=? AND status!='complete'",(rid,))
    self.active=None
 def recognition_crop(self,bid,qid,*,details=False):
  import io
  from PIL import Image
  import choice_marks
  def finish(raw,reading=None,evidence=None):return (raw,reading,evidence) if details else raw
  q=json.loads(self.one('questions',qid)['data']);config=response.normalize(q.get('response')) or {};b=self.one('booklets',bid)
  regions=([config['answerRegion']] if config.get('answerRegion') else [])+[r['rect'] for r in config.get('markRegions',[])]
  rect=q.get('rect')
  if regions and (not rect or any(r[0]<rect[0] or r[1]<rect[1] or r[2]>rect[2] or r[3]>rect[3] for r in regions)):raise ValueError('Redraw answer regions inside the current question box.')
  if config.get('answerRegion'):return finish(self.page(b['file_id'],b['start']+q['page']-1,rect=config['answerRegion']))
  regions=config.get('markRegions',[])
  if not regions:return finish(self.crop(bid,qid))
  references=self.rows("SELECT * FROM files WHERE version_id=? AND kind='handout' AND archived='' ORDER BY rowid LIMIT 1",(b['version_id'],))
  if not references or q['page']>references[0]['pages']:return finish(self.crop(bid,qid))
  # Two approved question renders, rather than ten full-page renders per answer.
  # Detection stays inside this crop; no name/identity fields enter the reader.
  scan_raw=self.crop(bid,qid);blank_raw=self.page(references[0]['id'],q['page']-1,rect=rect)
  with Image.open(io.BytesIO(scan_raw)) as scan_source,Image.open(io.BytesIO(blank_raw)) as blank_source:
   scan=scan_source.convert('RGB');blank=blank_source.convert('RGB')
  try:
   hints=[{'label':item['label'],'rect':[max(0,min(1,(item['rect'][i]-rect[i%2])/(rect[i%2+2]-rect[i%2]))) for i in range(4)]} for item in regions]
   evidence=choice_marks.analyze(blank,scan,hints,multiple=config['type']=='multiple_choice')
   sheet=choice_marks.comparison_sheet(blank,scan,hints,evidence)
   try:stream=io.BytesIO();sheet.save(stream,format='PNG');raw=stream.getvalue()
   finally:sheet.close()
   return finish(raw,evidence['recognition'],evidence)
  finally:scan.close();blank.close()
 def reviewed_examples(self,snapshot,q,settings):
  return snapshot.get('reviewedExamples',{}).get(q['id'],[])
 def pause(self,rid):
  row=self.one('runs',rid)
  if row['status'] not in ('queued','running'):raise ValueError('This run is not running.')
  self.cancelled.add(rid);return {'pausing':True}
 def run(self,rid):
  run=self.one('runs',rid);snapshot=json.loads(run.pop('snapshot'));settings=snapshot.get('grading',{}).get('profile',legacy_profile(run['model'],run['model_digest'],False))
  targets=snapshot.get('grading',{}).get('targets',[[q['id'],b['id']] for q in snapshot['questions'] for b in snapshot['booklets']])
  run['total']=len(targets);run['questions']=snapshot['questions'];run['booklets']=snapshot['booklets'];run['thinking']=any(response.kind(q)=='free_response' and recorded_profile(snapshot,q,settings)['thinking'] for q in snapshot['questions'])
  run['provider']=settings.get('provider','local')
  run['proposals']=self.rows('SELECT * FROM proposals WHERE run_id=? ORDER BY rowid',(rid,))
  review_rows=self.rows('SELECT w.* FROM reviews w JOIN proposals p ON p.id=w.proposal_id WHERE p.run_id=? ORDER BY w.created,w.rowid',(rid,))
  reviews={r['proposal_id']:r for r in review_rows}
  for p in run['proposals']:
   p['result']=json.loads(p['result']);p['review']=reviews.get(p['id'])
   if p['review']:p['review']['choices']=json.loads(p['review']['choices'])
  run['completed']=len(run['proposals']);expected={};actual={}
  for q,b in targets:expected.setdefault(b,set()).add(q)
  for p in run['proposals']:actual.setdefault(p['booklet_id'],set()).add(p['question_id'])
  run['totalSubmissions']=len(expected);run['completedSubmissions']=sum(qs.issubset(actual.get(b,set())) for b,qs in expected.items())
  current=self.snapshot(self.version(run['version_id']));lookup={q['id']:q for q in current['questions']}
  run['current']=all(q['id'] in lookup and question_hash(snapshot,q,recorded_profile(snapshot,q,settings))==question_hash(current,lookup[q['id']],question_profile(lookup[q['id']],settings)) for q in snapshot['questions'])
  if rid in self.grading_clocks:
   started,base=self.grading_clocks[rid];run['session_seconds']=time.monotonic()-started;run['elapsed_seconds']=base+run['session_seconds']
  return run
 def abandon_run(self,rid,payload):
  with self.lock:
   row=self.one('runs',rid)
   if row['status'] not in ('paused','error') or self.active==rid:raise ValueError('Pause this run and wait for its current request before abandoning it.')
   if set(payload)!={'choice','confirmed'} or payload.get('confirmed') is not True or payload.get('choice') not in ('save','discard'):raise ValueError('Choose Save partial results or Discard results.')
   discard=payload['choice']=='discard'
   with self.connect() as db:
    if discard:
     db.execute('DELETE FROM reviews WHERE proposal_id IN(SELECT id FROM proposals WHERE run_id=?)',(rid,));db.execute('DELETE FROM proposals WHERE run_id=?',(rid,))
    db.execute('UPDATE runs SET status=?,finished=? WHERE id=?',('discarded' if discard else 'saved',stamp(),rid))
    self.event(db,'grading-abandoned',rid,{'retained':not discard})
   return {'savedPartial':not discard,'discarded':discard}
 def grading_reset_preview(self,pid):
  self.one('projects',pid)
  runs=self.rows('SELECT id,status,snapshot_hash FROM runs WHERE version_id IN(SELECT id FROM versions WHERE project_id=?) ORDER BY id',(pid,))
  ids=[r['id'] for r in runs]
  proposals=self.rows('SELECT p.id FROM proposals p JOIN runs r ON r.id=p.run_id JOIN versions v ON v.id=r.version_id WHERE v.project_id=? ORDER BY p.id',(pid,))
  reviews=self.rows('SELECT w.id FROM reviews w JOIN proposals p ON p.id=w.proposal_id JOIN runs r ON r.id=p.run_id JOIN versions v ON v.id=r.version_id WHERE v.project_id=? ORDER BY w.id',(pid,))
  return {'projectId':pid,'runs':len(runs),'assessments':len(proposals),'reviews':len(reviews),'previewHash':fingerprint([runs,proposals,reviews])}
 def grading_reset(self,pid,payload):
  with self.lock:
   preview=self.grading_reset_preview(pid)
   active=self.rows('SELECT id FROM runs WHERE version_id IN(SELECT id FROM versions WHERE project_id=?) AND status IN(?,?)',(pid,'running','queued'))
   if active or self.project_queue_active or (self.active and any(r['id']==self.active for r in self.rows('SELECT id FROM runs WHERE version_id IN(SELECT id FROM versions WHERE project_id=?)',(pid,)))):raise ValueError('Pause project grading and wait for the current request before clearing its results.')
   if payload.get('confirmed') is not True or payload.get('previewHash')!=preview['previewHash']:raise ValueError('Preview and confirm removal of this project grading results.')
   with self.connect() as db:
    db.execute('DELETE FROM reviews WHERE proposal_id IN(SELECT p.id FROM proposals p JOIN runs r ON r.id=p.run_id JOIN versions v ON v.id=r.version_id WHERE v.project_id=?)',(pid,))
    db.execute('DELETE FROM proposals WHERE run_id IN(SELECT r.id FROM runs r JOIN versions v ON v.id=r.version_id WHERE v.project_id=?)',(pid,))
    db.execute('DELETE FROM runs WHERE version_id IN(SELECT id FROM versions WHERE project_id=?)',(pid,))
    db.execute('DELETE FROM answer_groups WHERE question_id IN(SELECT q.id FROM questions q JOIN versions v ON v.id=q.version_id WHERE v.project_id=?)',(pid,))
    db.execute('DELETE FROM reviewed_examples WHERE question_id IN(SELECT q.id FROM questions q JOIN versions v ON v.id=q.version_id WHERE v.project_id=?)',(pid,))
    db.execute('DELETE FROM grading_preferences WHERE version_id IN(SELECT id FROM versions WHERE project_id=?)',(pid,))
    db.execute('DELETE FROM project_batches WHERE project_id=?',(pid,))
    self.event(db,'project-grading-results-cleared',pid,{k:preview[k] for k in ('runs','assessments','reviews')})
   return {'removedRuns':preview['runs'],'removedAssessments':preview['assessments'],'removedReviews':preview['reviews'],'scansAndSetupPreserved':True}
 def export_current_version(self,vid):
  from grader import now
  v=self.version(vid);self.verify_source_hashes(v);self.materials_validate(vid)
  if v['rubric_approved']!=self.rubric_hash(v):raise ValueError('Save and confirm the current rubric before exporting.')
  settings=self._grading_profile(vid);index,_=self._assessment_index(v,settings)
  if not v['booklets'] or not v['questions'] or len(index)!=len(v['booklets'])*len(v['questions']):raise ValueError('Complete current results for every question in Version '+v['label']+' before exporting.')
  identities,mapping=self.export_student_identities(vid,[b['id'] for b in v['booklets']])
  files={f['id']:f for f in v['files']};scan_ids=[f['id'] for f in v['files'] if f['kind']=='scans']
  booklets=[{'id':b['id'],'label':'Exam '+str(i+1)+' - PDF '+str(scan_ids.index(b['file_id'])+1),'sourceHash':files[b['file_id']]['sha256'],'startPage':b['start']+1,'pages':b['pages'],'student':identities[b['id']],'versionLabel':v['label']} for i,b in enumerate(v['booklets'])]
  entries=[]
  for q in v['questions']:
   for b in v['booklets']:
    p=index[(q['id'],b['id'])];result=p['result'];review=p['review'];ids=review['choices'] if review else result['items'];selected=[i for i in q['items'] if i['id'] in ids]
    entries.append({'id':p['id'],'examId':b['id'],'questionKey':q['key'],'reviewed':bool(review),'result':{'rubricItem':' / '.join(i['label'] for i in selected) or 'Review needed','explanation':'Instructor-reviewed choice. Original model analysis is available in G-Scope.' if review else result['reason'],'uncertainty':'' if review else result['uncertainty'],'needsReview':False if review else result['needsReview'],'choices':[{'label':i['label'],'description':i['description'],'points':i['points']} for i in selected]}})
  sha=fingerprint([self.snapshot(v),settings,[(p['id'],p['review']['id'] if p['review'] else '') for p in index.values()]])
  return {'format':'rubric-lens-batch','version':2,'identityMatching':mapping,'batchId':sha[:32],'created':now(),'snapshotHash':sha,'exam':{'course':v['project']['course'],'term':v['project']['term'],'exam':v['project']['title'],'version':v['label']},'model':settings['model'],'modelDigest':settings['digest'],'rubricHash':self.rubric_hash(v),'questions':[{'key':q['key'],'title':q['title'],'number':str(q.get('number') or q['key']),'versionLabel':v['label'],'selectionMode':q['selectionMode']} for q in v['questions']],'booklets':booklets,'entries':entries,'complete':True,'mappingRequired':True}

 def response_suggestions(self,vid,payload):
  from answer_keys import source_question_key
  import re
  base=self._answer_base(vid);tex={};notice=''
  try:
   if base['blank']:tex=self.blank_question_context(vid,base['blank'])
  except (ValueError,OSError):notice='Linked question TeX is unavailable; suggestions use the rubric only.'
  questions=payload.get('questions',base['questions'])
  if not isinstance(questions,list) or len(questions)>100:raise ValueError('Choose saved questions for format suggestions.')
  known={q['id']:q for q in base['questions']};result={}
  for q in questions:
   if not isinstance(q,dict) or q.get('id') not in known:continue
   if not isinstance(q.get('items'),list) or len(q['items'])>50 or any(not isinstance(i,dict) or not isinstance(i.get('description',''),str) or len(i.get('description',''))>4000 for i in q['items']):raise ValueError('Check rubric text before suggesting formats.')
   key=source_question_key(base,known[q['id']]);parent=re.match(r'^\d+',key)
   source=tex.get(parent[0],{}).get('text','') if parent else ''
   # A parent's choice format is not evidence that every separately graded part is choice.
   if parent and key!=parent[0]:source=''
   result[q['id']]=response.suggest_format(q,source)
  return {'versionId':vid,'suggestions':result,'notice':notice}

 def response_keys(self,vid,payload):
  v=self.version(vid);known={q['id']:q for q in v['questions']};questions=payload.get('questions',[])
  if not isinstance(questions,list) or len(questions)>100:raise ValueError('Choose saved questions for answer-key extraction.')
  results={}
  for item in questions:
   if not isinstance(item,dict) or item.get('id') not in known:raise ValueError('Choose a saved question in this version.')
   q=known[item['id']];guidance=item.get('guidance',q.get('guidance',''));items=item.get('items',q['items'])
   if not isinstance(guidance,str) or len(guidance)>12000 or not isinstance(items,list) or len(items)>50 or any(not isinstance(i,dict) or not isinstance(i.get('description',''),str) or len(i.get('description',''))>4000 for i in items):raise ValueError('Check the reviewed key and rubric text.')
   candidate={**q,'guidance':guidance,'items':items,'response':item.get('response',q.get('response'))}
   resolved,info=response.resolve_correct(candidate,v['label'])
   results[q['id']]={'response':resolved,'responseKey':info}
  return {'versionId':vid,'questions':results}
