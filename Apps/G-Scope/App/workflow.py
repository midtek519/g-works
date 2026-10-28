"""Cross-version rubric reuse, region approval and ordered suggestion exports."""
import copy,hashlib,json,re,secrets,threading,time
from datetime import datetime,timezone

def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()

from scan_archive import fingerprint,stamp

class ExamWorkflow:
    def workflow_init(self):
        self.project_queue_active=None;self.project_queue_cancel=threading.Event()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS project_batches(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,model TEXT NOT NULL,versions TEXT NOT NULL,runs TEXT NOT NULL,status TEXT NOT NULL,current_run TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',created TEXT NOT NULL)")
            if 'options' not in {r[1] for r in db.execute('PRAGMA table_info(project_batches)')}:db.execute("ALTER TABLE project_batches ADD COLUMN options TEXT NOT NULL DEFAULT '{}'")
            db.execute("UPDATE project_batches SET status='paused' WHERE status IN ('queued','running')")

    def project_batch(self,pid):
        self.one('projects',pid)
        rows=self.rows('SELECT * FROM project_batches WHERE project_id=? ORDER BY rowid DESC LIMIT 1',(pid,))
        if not rows:return None
        value=rows[0];value['versions']=json.loads(value['versions']);value['runs']=json.loads(value['runs']);value['options']=json.loads(value.get('options','{}'));return value

    def assignment_progress(self,pid):
        # Read-only saved state. Never contact or warm a model for sidebar badges.
        self.one('projects',pid)
        versions=[self.version(row['id']) for row in self.rows("SELECT id FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(pid,))]
        from answer_groups import MANUAL
        from grading_control import profile,legacy_profile
        from response_grading import BLOCK,kind,issues
        states={name:[] for name in ('materials','template','rubric','decisions','scans','match','process','reviewgrades')}
        def add(name,done,started):states[name].append({'done':bool(done),'started':bool(started or done)})
        for version in versions:
            vid=version['id'];questions=version['questions'];books=version['booklets'];files=version['files']
            blank=[f for f in files if f['kind']=='handout' and f.get('available',True)]
            references=self.materials_list(vid)['references']
            linked_blank=any(r['role']=='handout' and (self.root/'Projects'/vid/'Materials'/(r['id']+'.'+r['format'])).is_file() for r in references)
            add('materials',bool(blank) or linked_blank,bool(references or files))
            add('template',bool(questions) and all(q.get('rect') for q in questions),bool(questions))
            answers=all(kind(q)=='manual' or (not issues(q) if kind(q)!='free_response' else bool(BLOCK.search(q.get('guidance','')))) for q in questions)
            add('rubric',bool(questions) and answers and all(q.get('items') for q in questions) and version['rubric_approved']==self.rubric_hash(version),any(q.get('items') or q.get('guidance') for q in questions))
            notes=any(BLOCK.sub('',q.get('guidance','')).strip() or (q.get('response') or {}).get('expectedWork','').strip() for q in questions)
            policy=(self.consistency_snapshot(version) or {}).get('questions',{})
            guidance=notes or any(value.get('rules') for value in policy.values())
            add('decisions',guidance,guidance)
            scans=[f for f in files if f['kind']=='scans']
            add('scans',bool(books) and all(f['layout'].get('confirmed') and f.get('available',True) for f in scans),bool(scans or books))
            matched=False
            if books:
                try:self.export_student_identities(vid,[b['id'] for b in books]);matched=True
                except ValueError:pass
            identities=self.rows('SELECT i.booklet_id FROM scan_identities i JOIN booklets b ON b.id=i.booklet_id WHERE b.version_id=?',(vid,))
            add('match',matched,any(item['booklet_id'] in {b['id'] for b in books} for item in identities))
            saved=self.rows('SELECT * FROM grading_preferences WHERE version_id=?',(vid,))
            settings=profile(saved[0]['model'],saved[0]['model_digest'],bool(saved[0]['thinking'])) if saved else dict(MANUAL)
            if not saved:
                latest=self.rows("SELECT model,model_digest,snapshot FROM runs WHERE version_id=? AND model!='instructor' ORDER BY created DESC,rowid DESC LIMIT 1",(vid,))
                if latest:
                    r=latest[0];settings=json.loads(r['snapshot']).get('grading',{}).get('profile',legacy_profile(r['model'],r['model_digest'],False))
            try:index,_=self._assessment_index(version,settings)
            except ValueError:index={}
            total=len(questions)*len(books);done=len(index);reviewed=sum(bool(item.get('review')) for item in index.values())
            add('process',total>0 and done==total,done>0 or bool(version['runs']))
            add('reviewgrades',total>0 and reviewed==total,reviewed>0)
        def aggregate(items):
            count=sum(item['done'] for item in items)
            state='done' if items and count==len(items) else 'partial' if any(item['started'] for item in items) else 'empty'
            return {'state':state,'complete':count,'total':len(items)}
        result={name:aggregate(items) for name,items in states.items()}
        inbox=self.intake_list(pid);sources=[source for source in inbox['sources'] if not source.get('deleted')]
        if sources and (any(not source.get('layout',{}).get('confirmed') or not source.get('booklets') or any(not packet.get('assignedBookletId') for packet in source.get('booklets',[])) for source in sources) or result['scans']['state']=='empty'):result['scans']['state']='partial'
        roster=self.roster_get(pid);result['roster']={'state':'done' if roster['ready'] else 'partial' if roster['configured'] else 'empty','complete':int(roster['ready']),'total':1}
        return {'assignmentId':pid,'steps':result,'versionCount':len(versions)}

    def start_project(self,pid,payload):
        self.require_gradescope_roster(pid)
        with self.lock:return self._start_project(pid,payload)

    def _start_project(self,pid,payload):
        self.one('projects',pid)
        if self.active or self.project_queue_active or self.archive_busy(ignore_matching=True):raise ValueError('Finish or pause the current local processing job first.')
        versions=[self.version(v['id']) for v in self.rows('SELECT id FROM versions WHERE length(archived)=0 AND project_id=? ORDER BY rowid',(pid,))]
        versions=[v for v in versions if v['booklets']]
        if not versions:raise ValueError('Assign exams to versions before processing.')
        intake=self.intake_list(pid)
        if any(not f.get('layout',{}).get('confirmed') or not f.get('booklets') for f in intake['sources'] if not f.get('deleted')):raise ValueError('Confirm boundaries for every active source PDF before processing the project.')
        if any(not b.get('assignedBookletId') for f in intake['sources'] if not f.get('deleted') for b in f.get('booklets',[])):raise ValueError('Review and assign every active inbox exam before processing the full project.')
        from response_grading import kind
        selected_key=payload.get('questionKey')
        if selected_key is not None and (not isinstance(selected_key,str) or not re.fullmatch(r'[A-Za-z0-9_.()-]{1,40}',selected_key)):raise ValueError('Choose an exact question label for all versions.')
        if any(type(payload.get(k,False)) is not bool for k in ('redo','formGroups')):raise ValueError('Choose valid regrade and answer-group options.')
        def selected(version):
            if selected_key is None:return [q for q in version['questions'] if kind(q)!='manual']
            matches=[q for q in version['questions'] if q['key']==selected_key]
            if len(matches)!=1:raise ValueError('Version '+version['label']+': Question '+selected_key+' is missing or duplicated.')
            if kind(matches[0])=='manual':raise ValueError('Version '+version['label']+': Question '+selected_key+' uses manual grading.')
            return matches
        selections={v['id']:[q['id'] for q in selected(v)] for v in versions}
        options={'questionKey':selected_key,'redo':payload.get('redo',False),'formGroups':payload.get('formGroups',False)} if selected_key is not None else {}
        versions=[v for v in versions if selections[v['id']]]
        if not versions:raise ValueError('These questions use manual review. Open a question to assign rubric items.')
        for v in versions:
            try:self.validate_ready(v,template_crops=payload.get('useTemplateCrops') is True,question_ids=selections[v['id']])
            except ValueError as error:raise ValueError('Version '+v['label']+': '+str(error)) from error
        model=payload.get('model')
        if not isinstance(model,str) or not model.strip() or len(model)>200:raise ValueError('Choose an installed local model.')
        self.model_identity(model)
        if payload.get('useTemplateCrops') is True:
            for v in versions:self.apply_template_crops(v['id'],question_ids=selections[v['id']])
        jid=secrets.token_hex(16)
        with self.connect() as db:db.execute('INSERT INTO project_batches(id,project_id,model,versions,runs,status,created,options) VALUES(?,?,?,?,?,?,?,?)',(jid,pid,model,json.dumps([v['id'] for v in versions]),'[]','queued',datetime.now(timezone.utc).isoformat(),json.dumps(options)))
        self.project_queue_active=jid;self.project_queue_cancel.clear()
        threading.Thread(target=self._project_worker,args=(jid,),daemon=True,name='exam-project-queue').start()
        return self.project_batch(pid)

    def _project_worker(self,jid):
        try:
            row=self.rows('SELECT * FROM project_batches WHERE id=?',(jid,))[0];done=[];options=json.loads(row.get('options','{}'))
            with self.connect() as db:db.execute("UPDATE project_batches SET status='running' WHERE id=?",(jid,))
            for vid in json.loads(row['versions']):
                if self.project_queue_cancel.is_set():break
                from grading_control import profile
                v=self.version(vid);settings=self._grading_model(row['model'],False)
                current,_=self._assessment_index(v,settings)
                from response_grading import kind
                ai_ids={q['id'] for q in v['questions'] if kind(q)!='manual' and (not options.get('questionKey') or q['key']==options['questionKey'])}
                if not options.get('redo') and all((qid,b['id']) in current for qid in ai_ids for b in v['booklets']):
                    self.verify_source_hashes(v)
                    rid=current[(next(iter(ai_ids)),v['booklets'][0]['id'])]['run_id']
                else:
                    # Use the same question/profile compatibility as individual jobs.
                    resumable=None
                    for candidate in self.rows("SELECT * FROM runs WHERE version_id=? AND status IN ('paused','error') ORDER BY created DESC",(vid,)):
                        saved=json.loads(candidate['snapshot'])
                        previous=saved.get('grading',{}).get('profile',profile(candidate['model'],candidate['model_digest'],False))
                        if not options.get('redo') and {q['id'] for q in saved['questions']}==ai_ids and self.grading_snapshot_compatible(v,saved,settings,previous):
                            resumable=candidate;break
                    payload={'model':row['model'],'thinking':False,'questionIds':sorted(ai_ids),'redo':options.get('redo',False),**({'resume':resumable['id']} if resumable else {})}
                    rid=self.start(vid,payload,_project=True)['id']
                    with self.connect() as db:db.execute('UPDATE project_batches SET current_run=? WHERE id=?',(rid,jid))
                    while self.active==rid:
                        if self.project_queue_cancel.is_set():self.pause(rid)
                        time.sleep(.1)
                    run=self.one('runs',rid)
                    if self.project_queue_cancel.is_set():break
                    if run['status']!='complete':raise ValueError(run['error'] or 'A version did not finish. Resume after checking its run.')
                if options.get('formGroups'):
                    for q in v['questions']:
                        if q['id'] not in ai_ids or q.get('response',{}).get('grouping')!='groups':continue
                        with self.lock:
                            data=self.answer_groups(q['id'],v['project_id'])
                            if not data['groups']:self.change_answer_groups(q['id'],{'projectId':v['project_id'],'revision':data['revision'],'action':'build'},_project=jid)
                done.append(rid)
                with self.connect() as db:db.execute('UPDATE project_batches SET runs=? WHERE id=?',(json.dumps(done),jid))
            with self.connect() as db:db.execute("UPDATE project_batches SET status=?,current_run='' WHERE id=?",('paused' if self.project_queue_cancel.is_set() else 'complete',jid))
        except Exception as e:
            message=str(e) if isinstance(e,ValueError) and len(str(e))<250 and '\\' not in str(e) else 'Project processing stopped. Check the saved version runs and local model.'
            with self.connect() as db:db.execute("UPDATE project_batches SET status='error',error=? WHERE id=?",(message,jid))
        finally:self.project_queue_active=None

    def pause_project(self,pid):
        row=self.project_batch(pid)
        if row and row['id']==self.project_queue_active:
            self.project_queue_cancel.set()
            if self.active:self.pause(self.active)
        return {'pausing':True}

    def question_privacy_check(self,vid,questions):
        layout=self.layout_get(vid)
        for q in questions:
            if not q.get('rect'):continue
            x,y,x1,y1=q['rect']
            for name in ('name','netid'):
                field=layout.get('fields',{}).get(name)
                if not field or field['page']!=q['page']:continue
                a,b,a1,b1=field['rect']
                if max(x,a)<min(x1,a1) and max(y,b)<min(y1,b1):
                    raise ValueError('A question region overlaps the saved name or NetID region. Adjust the question crop before grading.')

    def apply_template_crops(self,vid,question_ids=None):
        v=self.version(vid);self.writable(vid);self.validate_ready(v,template_crops=True,question_ids=question_ids)
        files=[f['id'] for f in v['files'] if f['kind']=='scans']
        with self.connect() as db:
            for q in v['questions']:
                if question_ids is not None and q['id'] not in question_ids:continue
                data=copy.deepcopy(q);qid=data.pop('id');data['checkedFiles']=files
                db.execute('UPDATE questions SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),qid))
            self.event(db,'template-regions-applied-at-grading-start',vid,{'files':files,'snapshotHash':_digest(self.snapshot(v))})
        return self.version(vid)

    def approve_all_crops(self,vid,payload):
        v=self.version(vid);self.writable(vid)
        if payload.get('approved') is not True or payload.get('snapshotHash')!=_digest(self.snapshot(v)):
            raise ValueError('Refresh the version, inspect sample crops, then approve the current scan set.')
        self.question_privacy_check(vid,v['questions'])
        files=[f for f in v['files'] if f['kind']=='scans']
        if not files or not v['questions'] or any(not q.get('rect') for q in v['questions']):raise ValueError('Save every question region and import scan PDFs first.')
        for f in files:
            if not f['layout'].get('confirmed'):raise ValueError('Confirm booklet boundaries in every PDF first.')
            booklets=[b for b in v['booklets'] if b['file_id']==f['id']]
            if not booklets:raise ValueError('Confirm the booklet boundaries first.')
            if any(q['page']>b['pages'] for q in v['questions'] for b in booklets):raise ValueError('A question page is outside a booklet.')
            # Exercise the saved renderer and file availability without model access.
            for q in v['questions']:self.crop(booklets[0]['id'],q['id'])
        with self.connect() as db:
            for q in v['questions']:
                q=copy.deepcopy(q);qid=q.pop('id');q['checkedFiles']=[f['id'] for f in files]
                db.execute('UPDATE questions SET data=? WHERE id=?',(json.dumps(q,ensure_ascii=False),qid))
            self.event(db,'all-regions-approved',vid,{'files':[f['id'] for f in files],'snapshotHash':payload['snapshotHash']})
        return self.version(vid)

    def share_rubric(self,pid,payload):
        with self.lock:return self._share_rubric(pid,payload)

    def _share_rubric(self,pid,payload):
        from response_grading import shared_response,issues
        self.one('projects',pid)
        source=self.version(payload.get('sourceVersionId',''))
        if source['project_id']!=pid or payload.get('confirmed') is not True:raise ValueError('Confirm a source version in this exam project.')
        if source['rubric_approved']!=self.rubric_hash(source) and payload.get('saveReviewed') is not True:raise ValueError('Confirm the source rubric before sharing it.')
        if not source['questions'] or any(not q['items'] for q in source['questions']):raise ValueError('Complete the source rubric items before applying them to all versions.')
        versions=[self.version(v['id']) for v in self.rows('SELECT id FROM versions WHERE length(archived)=0 AND project_id=? ORDER BY rowid',(pid,))]
        for v in versions:self.writable(v['id'])
        pending=[]
        def finish(version):
            problems=[{'questionKey':q['key'],'issues':issues(q)} for q in version['questions'] if issues(q)]
            if problems:pending.append({'versionId':version['id'],'versionLabel':version['label'],'questions':problems})
            self.approve_rubric(version['id'],{'approved':True})
        for v in versions:
            if v['id']==source['id']:
                if payload.get('saveReviewed') is True:finish(source)
                continue
            old={q['key']:q for q in v['questions']};questions=[]
            for q in source['questions']:
                prior=old.get(q['key'],{})
                shared={k:copy.deepcopy(q[k]) for k in ('key','maxPoints','selectionMode','items')}
                # A shared rubric does not imply identical exam questions or solutions.
                shared.update(response=shared_response(q.get('response'),prior.get('response')),title=prior.get('title','Question '+q['key']),guidance=prior.get('guidance',''),page=prior.get('page',1),rect=prior.get('rect'))
                if prior.get('id'):shared['id']=prior['id']
                questions.append(shared)
            self.import_rubric(v['id'],{'text':source['raw_rubric'] or 'Shared instructor-reviewed rubric.'})
            self.save_questions(v['id'],{'questions':questions})
            if source.get('rubricOutline'):
                with self.connect() as db:db.execute('INSERT OR REPLACE INTO version_rubric_outline VALUES(?,?)',(v['id'],json.dumps(source['rubricOutline'],ensure_ascii=False)))
            if source.get('rubricStructured'):
                with self.connect() as db:db.execute('INSERT OR REPLACE INTO version_structured_rubrics VALUES(?)',(v['id'],))
            finish(self.version(v['id']))
            with self.connect() as db:self.event(db,'project-rubric-shared',v['id'],{'sourceVersionId':source['id']})
        return {'versions':len(versions),'versionSpecificSolutionsPreserved':True,'responseFormatsShared':True,'needsResponseReview':pending}

    def export_version(self,vid):
        return self.export_current_version(vid)

    def export_project(self,pid):
        project=self.one('projects',pid);self.require_gradescope_roster(pid)
        versions=self.rows("SELECT id,label FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(pid,))
        versions=[v for v in versions if self.booklets_in_source_order(v['id'])]
        if not versions:raise ValueError('No active exams are available to export.')
        batches=[self.export_version(v['id']) for v in versions]
        booklets=[];questions=[];entries=[];seen=set()
        for version,batch in zip(versions,batches):
            prefix=version['label']+'.'
            for booklet in batch['booklets']:
                if booklet['student']['netid'] in seen:raise ValueError('One student is linked to exams in more than one version. Resolve that duplicate before exporting.')
                seen.add(booklet['student']['netid']);booklets.append(booklet)
            questions.extend({**q,'key':prefix+q['key']} for q in batch['questions'])
            entries.extend({**entry,'questionKey':prefix+entry['questionKey']} for entry in batch['entries'])
        snapshot_hash=fingerprint([{'batch':b['batchId'],'snapshot':b['snapshotHash']} for b in batches])
        return {'format':'rubric-lens-batch','version':2,'batchId':snapshot_hash[:32],'created':stamp(),'snapshotHash':snapshot_hash,
                'rubricHash':fingerprint([b['rubricHash'] for b in batches]),'identityMatching':batches[0]['identityMatching'],
                'exam':{'course':project['course'],'term':project['term'],'exam':project['title'],'version':'All versions'},
                'model':'per-version','modelDigest':'per-version','booklets':booklets,'questions':questions,'entries':entries,'complete':True,'mappingRequired':True}
