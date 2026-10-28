"""Set up an exam's versions from one saved Materials handout build."""
import hashlib,json,os,re,time,urllib.request
from pathlib import Path
from materials_links import digest,version_letter


def exam_name(value):
    value=re.sub(r'[-_]+',' ',str(value)).strip()
    match=re.match(r'(?i)^(?:exam\s*(\d+)|final(?:\s+exam)?)(?:\b|$)',value)
    return ('Exam '+match[1]) if match and match[1] else 'Final Exam' if match else value


class HandoutBuilds:
    def handout_builds(self,vid):
        _,project,_=self._materials_context(vid)
        universal=getattr(getattr(self._materials_provider(),'library',None),'universal',None)
        rows=[]
        if universal:
            for a in universal.assignments():
                if str(a.get('course'))!=project['course'] or a.get('semester')!=project['term'] or a.get('kind') not in ('exam','final'):continue
                if exam_name(a.get('title'))!=exam_name(project['title']):continue
                rows.append({'id':a['id'],'revision':a['revision'],'title':exam_name(a['title']),'versions':int(a.get('versions',1))})
        return {'builds':rows,'course':project['course'],'term':project['term']}

    def _materials_main_request(self,path,payload=None):
        root=self._materials_provider().root
        state=__import__('integration_paths').ensure_materials_service(root)
        origin=state.get('url','')
        if not re.fullmatch(r'http://127\.0\.0\.1:\d+',origin) or Path(state.get('root','')).resolve()!=root.resolve():raise ValueError('Open G-Whiz before setting up a handout build.')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(route,data=None,token=None):
            headers={'Content-Type':'application/json'}
            if token:headers['X-App-Token']=token
            req=urllib.request.Request(origin+route,data=None if data is None else json.dumps(data).encode(),headers=headers)
            with opener.open(req,timeout=600 if route=='/api/universal/compile' else 45) as response:return json.load(response)
        health=request('/api/health')
        if health.get('app')!='GWhiz' or Path(health.get('root','')).resolve()!=root.resolve():raise ValueError('The Materials service could not be verified.')
        if path=='/api/universal/compile' and payload is not None and 'student_versions' in payload and health.get('selectedHandoutVersions') is not True:raise ValueError('Restart G-Whiz to load selected-version compilation before setting up this handout.')
        return request(path,payload,request('/api/bootstrap')['token'] if payload is not None else None)

    def setup_handout_build(self,vid,payload):
        with self.lock:
            self.writable(vid)
            if self.archive_busy():raise ValueError('Finish the current local job before setting up a handout build.')
            choices=self.handout_builds(vid)['builds'];chosen=next((x for x in choices if x['id']==payload.get('assignmentId')),None)
            if not chosen or payload.get('revision')!=chosen['revision']:raise ValueError('Refresh and choose the current handout build.')
            if payload.get('confirmed') is not True:raise ValueError('Confirm setup of the selected exam versions.')
            labels=payload.get('versionLabels',list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')[:chosen['versions']])
            allowed=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')[:chosen['versions']]
            if not isinstance(labels,list) or not labels or any(not isinstance(x,str) or x not in allowed for x in labels) or len(labels)!=len(set(labels)):raise ValueError('Select one or more versions from this Handout Build.')
            labels=[x for x in allowed if x in labels]
            project_id=self.one('versions',vid)['project_id']
            # Existing work is preserved. Another build can be linked manually.
            for v in self.rows('SELECT id FROM versions WHERE length(archived)=0 AND project_id=?',(project_id,)):
                if self.one('versions',v['id'])['label'] not in labels:continue
                value=self.version(v['id'])
                if value['files'] or self.materials_list(v['id'])['references']:raise ValueError('This project already has linked files. Use a new project for automatic build setup, or keep linking versions manually.')
            return self.jobs.submit(lambda checkpoint:self._setup_handout_worker(vid,chosen,checkpoint,labels),controlled=True,user_errors=True)

    def _setup_handout_worker(self,vid,chosen,checkpoint,selected=None):
        selected=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')[:chosen['versions']] if selected is None else selected
        include_solutions='A' in selected
        label='Versions '+', '.join(selected)
        started=time.monotonic();compile_label=label+(' and Version A solutions' if include_solutions else '')
        checkpoint({'message':'Preparing '+compile_label+'…','phase':'preparation','elapsedSeconds':0})
        batch=self._materials_main_request('/api/universal/compile',{'assignment_ids':[chosen['id']],'student_versions':selected,'mode':'all' if include_solutions else 'student','publish_when_ready':False})
        preparation_seconds=round(time.monotonic()-started,3)
        batch_id=batch['id']
        if not re.fullmatch('[a-f0-9]{16}',batch_id):raise ValueError('Materials returned an invalid build.')
        for _ in range(2400):
            batch=self._materials_main_request('/api/builds/'+batch_id)
            jobs=batch.get('jobs',[]);done=sum(job.get('status')=='ready' for job in jobs)
            message=('Compiling '+label+': '+str(done)+' of '+str(len(jobs))+' PDFs complete.' if jobs else 'Preparing '+label+(' and Version A solutions…' if include_solutions else '…'))
            if batch.get('phase')=='fingerprint':message='Checking the selected inputs for '+compile_label+'…'
            elif batch.get('phase')=='verify':message='Verifying '+compile_label+'…'
            elif jobs:message='Compiling '+compile_label+': '+str(done)+' of '+str(len(jobs))+' PDFs complete.'
            checkpoint({'message':message,'completed':done,'total':len(jobs),'phase':batch.get('phase','compile'),'elapsedSeconds':round(time.monotonic()-started,1),'preparationSeconds':preparation_seconds,'inputCheckSeconds':batch.get('timings',{}).get('input_check_seconds')})
            if batch['status'] not in ('queued','running'):break
            time.sleep(.5)
        if batch['status']!='ready':raise ValueError('The handout did not compile completely. Check the build in Materials before retrying.')
        if next((a for a in self.handout_builds(vid)['builds'] if a['id']==chosen['id']),{}).get('revision')!=chosen['revision']:raise ValueError('The handout changed while compiling. Refresh and set it up again.')
        checkpoint({'message':'Linking the compiled exam versions…'})
        result=self._import_handout_batch(vid,chosen,batch_id,selected)
        result['timings']={'preparationSeconds':preparation_seconds,'totalSeconds':round(time.monotonic()-started,3),**batch.get('timings',{})}
        return result

    def _import_handout_batch(self,vid,chosen,batch_id,selected=None):
        with self.lock:
            v=self.version(vid);pid=v['project_id'];self.writable(vid)
            catalog=self._materials_provider().catalog(v['project']['course'],v['project']['term'])
            sources=[s for s in catalog if s.get('buildId')==batch_id and s.get('assignmentId')==chosen['id']]
            handouts={version_letter(s['version']):s for s in sources if s['role']=='handout' and s['format']=='pdf'}
            expected=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')[:chosen['versions']]
            expected=[x for x in expected if selected is None or x in selected]
            if not set(expected).issubset(handouts):raise ValueError('The build is missing one or more blank exam versions. Check Materials.')
            for existing in self.rows('SELECT id,label FROM versions WHERE length(archived)=0 AND project_id=?',(pid,)):
                if version_letter(existing['label']) not in expected:continue
                if self.version(existing['id'])['files'] or self.materials_list(existing['id'])['references']:raise ValueError('Files were added while the handout was compiling. Keep them and set up this build in a new project.')
            solutions=[s for s in sources if s['role']=='solutions' and s.get('version')=='A'];solutions.sort(key=lambda s:s['format']!='tex')
            # Validate all bytes/PDFs before changing project metadata.
            prepared={}
            import pypdfium2 as pdfium
            for source in [*[handouts[x] for x in expected],*(solutions[:1] if 'A' in expected else [])]:
                meta,raw=self._materials_provider().read(v['project']['course'],v['project']['term'],source['id'])
                if meta['format']=='pdf':
                    pdf=pdfium.PdfDocument(raw);pages=len(pdf);pdf.close()
                    if not pages:raise ValueError('A compiled blank PDF is empty.')
                prepared[source['id']]=digest(raw)
            versions={version_letter(r['label']):r['id'] for r in self.rows('SELECT id,label FROM versions WHERE length(archived)=0 AND project_id=?',(pid,))}
            for letter in expected:
                if letter not in versions:versions[letter]=self.add_version(pid,{'label':letter})['id']
                target=versions[letter];source=handouts[letter]
                linked=self.materials_link(target,{'sourceId':source['id'],'sha256':prepared[source['id']],'role':'handout','targetVersion':letter,'versionConfirmed':True})
                ref=next(r for r in linked['references'] if r['role']=='handout')
                self.materials_use_handout(target,{'referenceId':ref['id'],'sha256':ref['sha256'],'confirmed':True})
            if solutions and 'A' in expected:
                source=solutions[0];self.materials_link(versions['A'],{'sourceId':source['id'],'sha256':prepared[source['id']],'role':'solutions','targetVersion':'A','versionConfirmed':True})
            with self.connect() as db:self.event(db,'handout-build-setup',pid,{'assignmentId':chosen['id'],'revision':chosen['revision'],'buildId':batch_id,'versions':expected})
            return {'versionId':versions.get(version_letter(v['label']),versions[expected[0]]),'versions':expected,'solutionsVersion':'A' if solutions and 'A' in expected else None,'warnings':[] if solutions else ['No solutions were found in this handout build. You can add a solutions PDF or an answer key later.'],'buildId':batch_id}
