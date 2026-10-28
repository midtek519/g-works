from version_reader import MarkerDocument
from rosters import resolve_identity_reading,identity_sheet,suggest_identity_reading
"""Project-wide cover-aware scan splitting and required local roster matching."""
import base64,io,json,re,threading
from PIL import Image,ImageChops,ImageDraw,ImageStat,ImageFilter
import pypdfium2 as pdfium
import local_ai
from scan_archive import packed,fingerprint,stamp,short_text,IDENTITY_SCHEMA,TRANSCRIPTION_SYSTEM
from rosters import name_key

class Submissions:
    def submissions_init(self):
        self.submission_jobs={};self.version_jobs={}
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS project_scan_settings(project_id TEXT PRIMARY KEY,pages INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_source_versions(source_id TEXT PRIMARY KEY,version_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_split_reviews(source_id TEXT PRIMARY KEY,data TEXT NOT NULL,confirmed INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_matching(packet_id TEXT PRIMARY KEY,status TEXT NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_version_reviews(source_id TEXT PRIMARY KEY,data TEXT NOT NULL);''')

    def _submission_job(self,mapping,pid):
        job=mapping.get(pid)
        if not job:return None
        try:return self.jobs.get(job)
        except ValueError:mapping.pop(pid,None);return None

    def project_scan_pages(self,pid):
        self.one('projects',pid)
        counts={r['pages'] for r in self.rows("SELECT f.pages FROM files f JOIN versions v ON v.id=f.version_id WHERE v.project_id=? AND v.archived='' AND f.archived='' AND f.kind='handout'",(pid,))}
        saved=self.rows('SELECT pages FROM project_scan_settings WHERE project_id=?',(pid,))
        if len(counts)!=1:raise ValueError('Link blank exams with one consistent page count for this project before uploading scans.')
        pages=next(iter(counts))
        if saved and saved[0]['pages']!=pages:raise ValueError('The blank exam page count changed after scans were uploaded. Resolve the exam source before splitting new scans.')
        if not 1<=pages<=200:raise ValueError('The blank exam must contain between 1 and 200 pages.')
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO project_scan_settings VALUES(?,?)',(pid,pages))
        return pages

    @staticmethod
    def _ink(image,fields):
        gray=image.convert('L').resize((384,498),Image.Resampling.LANCZOS)
        contrast=ImageChops.subtract(gray.filter(ImageFilter.GaussianBlur(5)),gray)
        ink=ImageChops.lighter(contrast.point(lambda n:255 if n>12 else 0),gray.point(lambda n:255 if n<160 else 0))
        draw=ImageDraw.Draw(ink)
        draw.rectangle((0,0,383,8),fill=0);draw.rectangle((0,489,383,497),fill=0)
        draw.rectangle((0,0,8,497),fill=0);draw.rectangle((375,0,383,497),fill=0)
        for r in fields:
            if r and r['page']==1:
                a,b,c,d=r['rect'];draw.rectangle((int(a*384)-4,int(b*498)-4,int(c*384)+4,int(d*498)+4),fill=0)
        return ink.resize((192,249),Image.Resampling.BOX).point(lambda n:255 if n>35 else 0)

    @staticmethod
    def _cover_move(image,dx,dy):
        result=Image.new('L',image.size);result.paste(image,(dx,dy));return result

    @staticmethod
    def _cover_profiles(image):
        return list(image.resize((192,1),Image.Resampling.BOX).tobytes()),list(image.resize((1,249),Image.Resampling.BOX).tobytes())

    @staticmethod
    def _cover_shifts(a,b):
        scores=[]
        for shift in range(-10,11):
            pairs=[(x,b[i-shift]) for i,x in enumerate(a) if 0<=i-shift<len(b)]
            scores.append((sum(min(x,y) for x,y in pairs),shift))
        return [s for _,s in sorted(scores,reverse=True)[:4]]

    @staticmethod
    def _cover_match(template,scan):
        count=ImageStat.Stat(template).sum[0]/255;amount=ImageStat.Stat(scan).sum[0]/255
        if min(count,amount)<150:return {'score':0,'shift':[0,0],'ink':[count,amount]}
        tx,ty=Submissions._cover_profiles(template);sx,sy=Submissions._cover_profiles(scan)
        dilated=scan.filter(ImageFilter.MaxFilter(3));td=template.filter(ImageFilter.MaxFilter(3));best=(0,0,0)
        for dx in Submissions._cover_shifts(tx,sx):
            for dy in Submissions._cover_shifts(ty,sy):
                coverage=ImageStat.Stat(ImageChops.multiply(template,Submissions._cover_move(dilated,dx,dy))).sum[0]/255/count
                precision=ImageStat.Stat(ImageChops.multiply(td,Submissions._cover_move(scan,dx,dy))).sum[0]/255/amount
                score=2*coverage*precision/(coverage+precision) if coverage+precision else 0
                if score>best[0]:best=(score,dx,dy)
        return {'score':round(best[0],4),'shift':list(best[1:]),'ink':[count,amount]}

    def _cover_starts(self,pid,raw,total):
        # Local structural comparison only. No page or identity enters an AI prompt.
        templates=[];seen=set()
        for f in self.rows("SELECT f.* FROM files f JOIN versions v ON v.id=f.version_id WHERE v.project_id=? AND v.archived='' AND f.archived='' AND f.kind='handout'",(pid,)):
            fields=list(self.layout_get(f['version_id'])['fields'].values())
            with Image.open(io.BytesIO(self.page(f['id'],0))) as image:ink=self._ink(image,fields)
            signature=fingerprint(ink.tobytes())
            if signature not in seen and ImageStat.Stat(ink).sum[0]/255>=150:
                templates.append((ink,fields));seen.add(signature)
        if not templates or total>1000:return [],False,[]
        starts=[];diagnostics=[]
        with self.lock:
            doc=pdfium.PdfDocument(raw)
            try:
                for number in range(total):
                    page=doc[number];bitmap=page.render(scale=min(1.5,1000/max(page.get_size())));image=bitmap.to_pil().copy();bitmap.close();page.close()
                    best={'score':0,'shift':[0,0],'ink':[0,0]}
                    try:
                        for template,fields in templates:
                            candidate=self._ink(image,fields)
                            result=self._cover_match(template,candidate)
                            if result['score']>best['score']:best=result
                            candidate.close()
                    finally:image.close()
                    # The threshold applies to contrast-normalized, locally tolerant
                    # coverage in both directions, not the old exact-pixel Dice score.
                    matched=best['score']>=.78
                    if matched:starts.append(number)
                    diagnostics.append({'page':number+1,'score':best['score'],'matched':matched,'shift':best['shift']})
            finally:
                doc.close()
                for template,_ in templates:template.close()
        return starts,True,diagnostics

    def split_scan(self,sid):
        s=self._archive_one('scan_sources',sid);self._archive_idle();pages=self.project_scan_pages(s['project_id']);raw=self._source_bytes(s)
        if self.rows('SELECT id FROM scan_packets WHERE source_id=?',(sid,)):return
        starts,checked,diagnostics=self._cover_starts(s['project_id'],raw,s['pages'])
        anchored=bool(starts and starts[0]==0)
        if not anchored:starts=list(range(0,s['pages'],pages))
        ends=starts[1:]+[s['pages']];lengths=[b-a for a,b in zip(starts,ends)]
        regular=all(n==pages for n in lengths)
        confirmed=regular and anchored
        reason='' if confirmed else ('Cover-page comparison is unavailable. The suggested splits use the blank exam page count; review the boundaries.' if not checked else 'The cover positions do not match the expected exam length. Check the affected boundaries for missing or extra pages.' if anchored and not regular else 'The printed cover could not be matched confidently. Page-count splits are suggestions; this does not by itself mean pages are missing.')
        review={'expectedPages':pages,'starts':starts,'lengths':lengths,'coverCheck':checked,'coverAnchored':anchored,'reason':reason,'sourceHash':s['sha256'],'coverMethod':'contrast-tolerant-v2','coverThreshold':.78,'coverScores':diagnostics}
        import secrets
        with self.connect() as db:
            for start,count in zip(starts,lengths):db.execute('INSERT INTO scan_packets(id,source_id,start,pages) VALUES(?,?,?,?)',(secrets.token_hex(16),sid,start,count))
            db.execute('UPDATE scan_sources SET layout=? WHERE id=?',(packed({'pages_per_exam':pages,'skip':0,'rotation':0,'confirmed':confirmed}),sid))
            db.execute('INSERT OR REPLACE INTO scan_split_reviews VALUES(?,?,?)',(sid,packed(review),int(confirmed)))
            self.event(db,'scan-auto-split',sid,{'exams':len(starts),'reviewRequired':not confirmed})

    def confirm_scan_splits(self,sid,payload):
        s=self._archive_one('scan_sources',sid);self._archive_idle();self._source_bytes(s);expected=self.project_scan_pages(s['project_id'])
        if payload.get('confirmed') is not True or payload.get('sourceHash')!=s['sha256']:raise ValueError('Review the proposed split points for this unchanged PDF first.')
        starts=payload.get('starts')
        if not isinstance(starts,list) or not starts or starts[0]!=0 or any(type(n) is not int or not 0<=n<s['pages'] for n in starts) or starts!=sorted(set(starts)):raise ValueError('Choose ordered cover-page positions starting at page 1.')
        if self.rows("SELECT id FROM scan_packets WHERE source_id=? AND assigned_booklet_id!=''",(sid,)):raise ValueError('Assigned exam splits are retained. Replace the incorrect upload to change them.')
        ends=starts[1:]+[s['pages']];lengths=[b-a for a,b in zip(starts,ends)]
        if any(n>200 for n in lengths):raise ValueError('Each submission must be at most 200 pages.')
        import secrets
        with self.connect() as db:
            existing=self.rows('SELECT start,pages FROM scan_packets WHERE source_id=? ORDER BY start',(sid,))
            if [(r['start'],r['pages']) for r in existing]!=list(zip(starts,lengths)):
                db.execute('DELETE FROM scan_packets WHERE source_id=?',(sid,))
                db.execute('DELETE FROM scan_version_reviews WHERE source_id=?',(sid,))
                for start,count in zip(starts,lengths):db.execute('INSERT INTO scan_packets(id,source_id,start,pages) VALUES(?,?,?,?)',(secrets.token_hex(16),sid,start,count))
            db.execute('UPDATE scan_sources SET layout=? WHERE id=?',(packed({'pages_per_exam':expected,'skip':0,'rotation':0,'confirmed':True}),sid))
            db.execute('INSERT OR REPLACE INTO scan_split_reviews VALUES(?,?,1)',(sid,packed({'starts':starts,'lengths':lengths,'expectedPages':expected,'sourceHash':s['sha256'],'reason':'Reviewed split points.'})))
        return {'confirmed':True,'incompleteExams':sum(n!=expected for n in lengths)}

    def set_packet_version(self,packet_id,vid,*,internal=False):
        p=self._archive_one('scan_packets',packet_id);s=self._archive_one('scan_sources',p['source_id'])
        if p['assigned_booklet_id']:
            b=self.one('booklets',p['assigned_booklet_id'])
            if b['version_id']!=vid:raise ValueError('This exam is already assigned to another version. Replace the incorrect upload to change it.')
            return {'assigned':True,'existing':True,'bookletId':b['id'],'versionId':vid}
        if p['pages']!=self.project_scan_pages(s['project_id']):raise ValueError('This exam has missing or extra pages. Correct the scan before assigning it for grading.')
        result=self.intake_assign(packet_id,{'versionId':vid,'reviewed':True,'sourceHash':s['sha256'],'manual':True},_internal=internal)
        with self.connect() as db:db.execute("UPDATE scan_identities SET reviewed=0 WHERE booklet_id=? AND name='' AND netid=''",(result['bookletId'],))
        return result

    def set_source_version(self,sid,payload):
        # HTTP actions and recognition commits share this lock. Manual choices
        # take precedence over this project's in-flight marker reader.
        with self.lock:
            s=self._archive_one('scan_sources',sid);self._source_bytes(s)
            if payload.get('sourceHash')!=s['sha256']:raise ValueError('Refresh this unchanged PDF before choosing its version.')
            vid=payload.get('versionId') or ''
            if not isinstance(vid,str):raise ValueError('Choose an exam version for this PDF.')
            if vid:
                v=self.one('versions',vid)
                if v['project_id']!=s['project_id']:raise ValueError('Choose a version within this exam project.')
                self.writable(vid)
            evidence=self.source_version_evidence(s)
            override=bool(vid and (evidence['status']!='consistent' or evidence['versionId']!=vid))
            if vid and payload.get('evidenceHash')!=evidence['hash']:
                raise ValueError('The printed-version evidence changed. Refresh this PDF and review it before applying a version.')
            if override and payload.get('override') is not True:
                raise ValueError('This PDF has unknown, mixed or conflicting printed versions. Review the warning and explicitly override to apply one version.')
            expected=self.project_scan_pages(s['project_id'])
            packets=self.rows('SELECT * FROM scan_packets WHERE source_id=? ORDER BY start',(sid,))
            # Preflight the entire PDF before assigning anything. Same-version
            # assignments are no-ops so student matches and provenance survive.
            for p in packets:
                if vid and p['assigned_booklet_id'] and self.one('booklets',p['assigned_booklet_id'])['version_id']!=vid:
                    raise ValueError('An exam in this PDF is already assigned to another version. Replace the incorrect upload before changing that assignment.')
            own=self._submission_job(self.version_jobs,s['project_id'])
            own_reader=bool(own and own['status'] in ('queued','running') and not self.active and not self.project_queue_active)
            if own_reader:
                with self.jobs.lock:
                    others=any(j['id']!=own['id'] and j['status'] in ('queued','running') for j in self.jobs.jobs.values())
                    draining=own['status']=='queued' and self.jobs.active_workers>0
                    if others or draining:raise ValueError('Wait for other local processing to finish before choosing this PDF version.')
            else:self._archive_idle()
            with self.connect() as db:
                if vid:
                    db.execute('INSERT OR REPLACE INTO scan_source_versions VALUES(?,?)',(sid,vid))
                    review={'versionId':vid,'sourceHash':s['sha256'],'evidenceHash':evidence['hash'],'override':override,'evidence':{k:v for k,v in evidence.items() if k!='review'},'reviewedAt':stamp()}
                    db.execute('INSERT OR REPLACE INTO scan_version_reviews VALUES(?,?)',(sid,packed(review)))
                else:
                    db.execute('DELETE FROM scan_source_versions WHERE source_id=?',(sid,))
                    db.execute('DELETE FROM scan_version_reviews WHERE source_id=?',(sid,))
                self.event(db,'scan-pdf-version',sid,{'version_id':vid,'override':override,'evidenceHash':evidence['hash']})
            confirmed=json.loads(s['layout']).get('confirmed');assigned=0
            if vid and confirmed:
                for p in packets:
                    if p['pages']==expected:self.set_packet_version(p['id'],vid,internal=own_reader);assigned+=1
            return {'versionId':vid,'assigned':assigned,'waitingForSplitReview':bool(vid and not confirmed),'incompleteExams':sum(p['pages']!=expected for p in packets),'versionJob':own['id'] if own_reader else None}

    def review_packet_versions(self,sid,payload):
        """Review current per-exam marker proposals without a PDF-wide assumption."""
        with self.lock:
            self._archive_idle()
            source=self._archive_one('scan_sources',sid);self._source_bytes(source)
            evidence=self.source_version_evidence(source)
            if payload.get('reviewed') is not True or payload.get('sourceHash')!=source['sha256'] or payload.get('evidenceHash')!=evidence['hash']:
                raise ValueError('Refresh and review the current printed-version evidence first.')
            if not json.loads(source['layout']).get('confirmed'):raise ValueError('Confirm the PDF splits before assigning detected versions.')
            ids=payload.get('packetIds')
            if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
                raise ValueError('Choose complete exams with a current readable version.')
            versions=self.rows("SELECT id,label FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(source['project_id'],))
            expected=self.project_scan_pages(source['project_id']);pending=[]
            for packet_id in ids:
                packet=self._archive_one('scan_packets',packet_id);proposal=json.loads(packet['proposal'])
                if packet['source_id']!=sid or packet['assigned_booklet_id'] or packet['pages']!=expected:
                    raise ValueError('Only unassigned complete exams in this PDF may use detected versions.')
                if proposal.get('versionContext')!=self._version_context(source,packet,versions) or proposal.get('needsReview') or proposal.get('versionId') not in {v['id'] for v in versions}:
                    raise ValueError('An exam version is unreadable, conflicting or stale. Review it manually.')
                self.writable(proposal['versionId']);pending.append((packet_id,proposal['versionId']))
            assigned=[self.set_packet_version(packet_id,vid) for packet_id,vid in pending]
            with self.connect() as db:self.event(db,'scan-versions-reviewed',sid,{'packetIds':ids,'evidenceHash':evidence['hash']})
            return {'assigned':len(assigned),'mixed':len({v for _,v in pending})>1}

    def review_scans(self,pid,payload):
        """One explicit review confirms unchanged splits and per-exam versions.

        Preflight every source before changing any split or version assignment.
        Missing/unclear labels need an explicit manual choice; a neighboring
        exam or a whole-PDF default is never used to fill them in here.
        """
        with self.lock:
            self.one('projects',pid);self._archive_idle()
            if not isinstance(payload,dict) or payload.get('confirmed') is not True:
                raise ValueError('Review the ready scans and explicitly confirm them first.')
            selections=payload.get('sources')
            if not isinstance(selections,list) or not 1<=len(selections)<=200:
                raise ValueError('Choose one or more scan PDFs to review.')
            versions=self.rows("SELECT id,label FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(pid,))
            version_ids={v['id'] for v in versions};expected=self.project_scan_pages(pid)
            seen_sources=set();seen_packets=set();plans=[];total=0
            for selection in selections:
                if not isinstance(selection,dict):raise ValueError('Check the scan review selection.')
                sid=selection.get('sourceId')
                if not isinstance(sid,str) or sid in seen_sources:raise ValueError('Choose each scan PDF only once.')
                seen_sources.add(sid)
                source=self._archive_one('scan_sources',sid)
                if source['project_id']!=pid or source['deleted']:
                    raise ValueError('Choose available scan PDFs within this exam project.')
                self._source_bytes(source)
                if selection.get('sourceHash')!=source['sha256']:
                    raise ValueError('A scan source changed. Refresh and review it again.')
                evidence=self.source_version_evidence(source)
                if selection.get('evidenceHash')!=evidence['hash']:
                    raise ValueError('Printed-version evidence changed. Refresh and review it again.')
                packets=self.rows('''SELECT p.* FROM scan_packets p
                    LEFT JOIN booklets b ON b.id=p.assigned_booklet_id
                    LEFT JOIN scan_removed_files r ON r.file_id=b.file_id
                    WHERE p.source_id=? AND r.file_id IS NULL ORDER BY p.start''',(sid,))
                starts=selection.get('starts');current_starts=[p['start'] for p in packets]
                if not packets or not isinstance(starts,list) or any(type(n) is not int for n in starts) or starts!=current_starts:
                    raise ValueError('The PDF boundaries changed. Review edited splits separately before confirming versions.')
                layout=json.loads(source['layout']);confirm_splits=selection.get('confirmSplits',False)
                if not isinstance(confirm_splits,bool):raise ValueError('Choose whether to confirm the reviewed splits.')
                if not layout.get('confirmed'):
                    if not confirm_splits:raise ValueError('Confirm the reviewed PDF splits before assigning versions.')
                    lengths=[b-a for a,b in zip(starts,starts[1:]+[source['pages']])]
                    if starts[0]!=0 or any(n!=expected for n in lengths) or any(p['pages']!=expected for p in packets):
                        raise ValueError('This PDF has missing or extra pages. Correct its split points or scan before confirming it.')
                entries=selection.get('packetVersions',[])
                if not isinstance(entries,list) or len(entries)>500:
                    raise ValueError('Choose a valid list of complete exams to confirm.')
                if not entries and not confirm_splits:raise ValueError('Select an exam version or confirm the reviewed splits.')
                total+=len(entries)
                if total>5000:raise ValueError('Review at most 5000 exams in one action.')
                by_id={p['id']:p for p in packets};assignments=[]
                for entry in entries:
                    if not isinstance(entry,dict):raise ValueError('Check the selected exam version.')
                    packet_id=entry.get('packetId');vid=entry.get('versionId');manual=entry.get('manual',False)
                    if not isinstance(packet_id,str) or packet_id in seen_packets or packet_id not in by_id:
                        raise ValueError('Choose each available exam once within its original PDF.')
                    seen_packets.add(packet_id)
                    if not isinstance(vid,str) or vid not in version_ids or not isinstance(manual,bool):
                        raise ValueError('Choose a version within this exam project.')
                    self.writable(vid);packet=by_id[packet_id]
                    if packet['pages']!=expected:
                        raise ValueError('An exam has missing or extra pages. Correct it before assigning its version.')
                    if packet['assigned_booklet_id']:
                        if self.one('booklets',packet['assigned_booklet_id'])['version_id']!=vid:
                            raise ValueError('An exam is already assigned to another version. Its existing grading provenance is retained.')
                        assignments.append((packet_id,vid,manual,True));continue
                    proposal=json.loads(packet['proposal'])
                    detected=(proposal.get('versionContext')==self._version_context(source,packet,versions)
                        and not proposal.get('versionNeedsReview',proposal.get('needsReview')) and proposal.get('versionId')==vid)
                    if not detected and not manual:
                        raise ValueError('An exam version is unreadable, conflicting or stale. Choose and review its version manually.')
                    assignments.append((packet_id,vid,manual,False))
                choices=self.rows('SELECT version_id FROM scan_source_versions WHERE source_id=?',(sid,))
                clear_pdf_choice=bool(choices and any(vid!=choices[0]['version_id'] for _,vid,_,_ in assignments))
                plans.append((source,layout,starts,confirm_splits,assignments,clear_pdf_choice))
            assigned=existing=confirmed_sources=newly_confirmed=0
            for source,layout,starts,confirm_splits,assignments,clear_pdf_choice in plans:
                sid=source['id'];was_confirmed=bool(layout.get('confirmed'))
                if confirm_splits:
                    confirmed_sources+=1
                    if not was_confirmed:
                        layout['confirmed']=True
                        prior=self.rows('SELECT data FROM scan_split_reviews WHERE source_id=?',(sid,))
                        review=json.loads(prior[0]['data']) if prior else {}
                        review.update(starts=starts,lengths=[expected]*len(starts),expectedPages=expected,
                            sourceHash=source['sha256'],reason='Reviewed scan splits.',reviewedAt=stamp())
                        with self.connect() as db:
                            db.execute('UPDATE scan_sources SET layout=? WHERE id=?',(packed(layout),sid))
                            db.execute('INSERT OR REPLACE INTO scan_split_reviews VALUES(?,?,1)',(sid,packed(review)))
                        newly_confirmed+=1
                if clear_pdf_choice:
                    prior=self.rows('SELECT data FROM scan_version_reviews WHERE source_id=?',(sid,))
                    with self.connect() as db:
                        self.event(db,'scan-pdf-choice-superseded',sid,{'previousReview':json.loads(prior[0]['data']) if prior else None})
                        db.execute('DELETE FROM scan_source_versions WHERE source_id=?',(sid,))
                        db.execute('DELETE FROM scan_version_reviews WHERE source_id=?',(sid,))
                for packet_id,vid,manual,already_assigned in assignments:
                    self.set_packet_version(packet_id,vid)
                    if already_assigned:existing+=1
                    else:assigned+=1
                with self.connect() as db:self.event(db,'scan-review-confirmed',sid,{
                    'sourceHash':source['sha256'],'evidenceHash':next(s['evidenceHash'] for s in selections if s['sourceId']==sid),
                    'confirmedSplits':confirm_splits,'packetVersions':[{'packetId':i,'versionId':v,'manual':m} for i,v,m,_ in assignments]})
            remaining=sum(len(self.rows('''SELECT p.id FROM scan_packets p
                LEFT JOIN booklets b ON b.id=p.assigned_booklet_id LEFT JOIN scan_removed_files r ON r.file_id=b.file_id
                WHERE p.source_id=? AND p.assigned_booklet_id='' AND r.file_id IS NULL''',(s['id'],))) for s,*_ in plans)
            return {'assigned':assigned,'existing':existing,'confirmedSources':confirmed_sources,
                'newlyConfirmedSources':newly_confirmed,'reviewedPackets':assigned+existing,
                'remainingUnassigned':remaining,'sources':len(plans)}

    def prepare_scans(self,pid):
        self.one('projects',pid)
        old=self._submission_job(self.version_jobs,pid)
        if old and old['status'] in ('queued','running'):return {'job':{'id':old['id']}}
        self._archive_idle();pages=self.project_scan_pages(pid);issues=[]
        for source in self.rows("SELECT id FROM scan_sources WHERE project_id=? AND deleted='' ORDER BY rowid",(pid,)):
            try:self.split_scan(source['id'])
            except ValueError as error:issues.append(str(error))
            except Exception:issues.append('A PDF was retained but could not be split. Check or replace that upload.')
        versions=self.rows('SELECT id,label FROM versions WHERE length(archived)=0 AND project_id=? ORDER BY rowid',(pid,))
        ready=[];layouts={v['id']:self.layout_get(v['id']) for v in versions}
        for source in self.rows("SELECT * FROM scan_sources WHERE project_id=? AND deleted='' ORDER BY rowid",(pid,)):
            packets=self.rows('SELECT * FROM scan_packets WHERE source_id=? ORDER BY start',(source['id'],))
            choice=self.rows('SELECT version_id FROM scan_source_versions WHERE source_id=?',(source['id'],))
            reviews=self.rows('SELECT data FROM scan_version_reviews WHERE source_id=?',(source['id'],))
            if choice and reviews and json.loads(source['layout']).get('confirmed'):
                for packet in packets:
                    if packet['pages']==pages:self.set_packet_version(packet['id'],choice[0]['version_id'])
            if any(json.loads(p['proposal']).get('versionContext')!=self._version_context(source,p,versions,layouts) for p in packets):ready.append(source['id'])
        job=None
        if ready:
            try:job=self.intake_recognize(pid,{'sourceIds':ready,'phase':'versions'});self.version_jobs[pid]=job['id']
            except ValueError as error:issues.append(str(error))
            except Exception:issues.append('Version detection could not start. Check the approved Version box in Exam outline or explicitly choose a PDF version.')
        return {'pagesPerExam':pages,'job':job,'issues':list(dict.fromkeys(issues))}

    def _version_context(self,source,packet,versions,layouts=None):
        from version_reader import READER_VERSION
        return fingerprint({'reader':READER_VERSION,'source':source['sha256'],'start':packet['start'],'pages':packet['pages'],
            'rotation':(source['layout'] if isinstance(source['layout'],dict) else json.loads(source['layout'])).get('rotation',0),
            'versions':[{'id':v['id'],'label':v['label'],'layout':layouts[v['id']] if layouts is not None else self.layout_get(v['id'])} for v in versions]})

    def source_version_evidence(self,source):
        versions=self.rows("SELECT id,label FROM versions WHERE project_id=? AND archived='' ORDER BY rowid",(source['project_id'],))
        packets=self.rows('''SELECT p.* FROM scan_packets p LEFT JOIN booklets b ON b.id=p.assigned_booklet_id
            LEFT JOIN scan_removed_files r ON r.file_id=b.file_id WHERE p.source_id=? AND r.file_id IS NULL ORDER BY p.start''',(source['id'],))
        exams=[];known=set();layouts={v['id']:self.layout_get(v['id']) for v in versions}
        for number,packet in enumerate(packets,1):
            proposal=json.loads(packet['proposal']);current=proposal.get('versionContext')==self._version_context(source,packet,versions,layouts)
            vid=proposal.get('versionId','') if current and not proposal.get('needsReview') else ''
            v=next((v for v in versions if v['id']==vid),None)
            if v:known.add(vid)
            exams.append({'exam':number,'startPage':packet['start']+1,'pages':packet['pages'],
                'versionId':v['id'] if v else '', 'versionLabel':v['label'] if v else '',
                'status':'read' if v else 'unreadable' if current else 'not_checked',
                'method':proposal.get('versionMethod','vision') if current else '',
                'milliseconds':proposal.get('versionReadMs') if current else None,
                'reason':proposal.get('versionReason',proposal.get('reason','')) if current else 'Printed version has not been checked.'})
        unread=[e['exam'] for e in exams if not e['versionId']]
        status='mixed' if len(known)>1 else 'partial' if known and unread else 'consistent' if known and not unread else 'unknown'
        tentative=next(iter(known)) if status=='consistent' else ''
        value={'status':status,'versionId':tentative,'versionLabel':next((v['label'] for v in versions if v['id']==tentative),''),'exams':exams,'unreadableExams':unread,'needsReview':status!='consistent'}
        value['hash']=fingerprint({'source':source['sha256'],**value})
        records=self.rows('SELECT data FROM scan_version_reviews WHERE source_id=?',(source['id'],))
        value['review']=json.loads(records[0]['data']) if records else None
        return value

    def _match_packet(self,packet_id):
        p=self._archive_one('scan_packets',packet_id);s=self._archive_one('scan_sources',p['source_id'])
        if not p['assigned_booklet_id']:raise ValueError('Assign the exam version in Exam scans first.')
        b=self.one('booklets',p['assigned_booklet_id']);return p,s,b

    def matching_crop(self,packet_id,field):
        p,s,b=self._match_packet(packet_id)
        if field not in ('name','netid'):raise ValueError('Choose the name or NetID field.')
        region=self.layout_get(b['version_id'])['fields'].get(field)
        if not region or region['page']>p['pages']:raise ValueError('Save a name/NetID box inside this exam first.')
        return self._render(self._source_bytes(s),p['start']+region['page']-1,json.loads(s['layout']).get('rotation',0),region['rect'])

    def _roster_students(self,pid):
        rows=self.rows('SELECT data FROM project_rosters WHERE project_id=?',(pid,));raw=rows[0]['data'] if rows else '[]'
        students=json.loads(raw)
        for s in students:s['id']=fingerprint({'roster':raw,'student':s})[:32]
        return students,fingerprint(raw)

    def _save_match(self,packet_id,status,data):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO scan_matching VALUES(?,?,?,?)',(packet_id,status,packed(data),stamp()))

    def _write_identity(self,packet_id,student,status,roster_hash):
        p,s,b=self._match_packet(packet_id)
        duplicates=self.rows('''SELECT m.packet_id,m.status,m.data FROM scan_matching m JOIN scan_packets p ON p.id=m.packet_id JOIN scan_sources s ON s.id=p.source_id JOIN booklets b ON b.id=p.assigned_booklet_id LEFT JOIN scan_removed_files removed ON removed.file_id=b.file_id WHERE s.project_id=? AND removed.file_id IS NULL AND m.packet_id!=? AND m.status IN ('auto','manual')''',(s['project_id'],packet_id))
        for duplicate in duplicates:
            if student['id'] and json.loads(duplicate['data']).get('rosterId')==student['id']:
                if status=='auto' and duplicate['status']=='auto':
                    identities=self.rows('SELECT i.reviewed FROM scan_identities i JOIN scan_packets p ON p.assigned_booklet_id=i.booklet_id WHERE p.id=?',(duplicate['packet_id'],))
                    if not identities or not identities[0]['reviewed']:self._save_match(duplicate['packet_id'],'unmatched',{'reason':'Duplicate roster identity. Review both exams.'})
                raise ValueError('This roster student is already linked to another exam. Review the duplicate before assigning.')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO scan_identities VALUES(?,?,?,?,?)',(b['id'],student['name'],student['netid'],int(status=='manual'),stamp()))
            self.event(db,'scan-student-'+status+'-matched',packet_id,{'rosterHash':roster_hash})
        self._save_match(packet_id,status,{'rosterId':student.get('id',''),'section':student.get('section',''),'rosterHash':roster_hash})

    def match_manually(self,packet_id,payload):
        with self.lock:return self._match_manually_locked(packet_id,payload)

    def _match_manually_locked(self,packet_id,payload):
        p,s,b=self._match_packet(packet_id);self._matching_write_idle();self.require_gradescope_roster(s['project_id']);self._source_bytes(s)
        if set(payload)-{'studentId','name','netid','reviewed'}:raise ValueError('Choose a roster student or enter the reviewed name/NetID.')
        if payload.get('reviewed') is not True:raise ValueError('Confirm the student assignment.')
        students,sha=self._roster_students(s['project_id'])
        if payload.get('studentId'):
            student=next((r for r in students if r['id']==payload['studentId']),None)
            if not student:raise ValueError('Select a student from the current assignment roster.')
        else:
            netid=short_text(payload.get('netid',''),40).lower();name=short_text(payload.get('name',''),160)
            matches=[row for row in students if row['netid']==netid and (not name or name_key(row['name'])==name_key(name))]
            if len(matches)!=1:raise ValueError('Choose the matching student from this exam roster.')
            student=matches[0]
        self._write_identity(packet_id,student,'manual',sha);return {'assigned':True}

    def clear_student_match(self,packet_id,payload):
        with self.lock:
            p,s,b=self._match_packet(packet_id);self._matching_write_idle();self._source_bytes(s)
            _,roster_hash=self._roster_students(s['project_id'])
            if set(payload)!={'rosterHash','reviewed'} or payload.get('reviewed') is not True or payload.get('rosterHash')!=roster_hash:
                raise ValueError('Refresh and confirm clearing this student assignment.')
            prior=self.rows('SELECT status,data FROM scan_matching WHERE packet_id=?',(packet_id,))
            data=json.loads(prior[0]['data']) if prior else {}
            with self.connect() as db:
                self.event(db,'student-assignment-cleared',packet_id,{'previous':prior})
                db.execute('DELETE FROM scan_identities WHERE booklet_id=?',(b['id'],))
            self._save_match(packet_id,'unmatched',{'rosterHash':roster_hash,'proposal':data.get('proposal',{}),'manualHold':True,'reason':'Assignment cleared. Choose a roster student.'})
            return {'cleared':True}

    def review_student_matches(self,pid,payload):
        with self.lock:return self._review_student_matches_locked(pid,payload)

    def _review_student_matches_locked(self,pid,payload):
        self._matching_write_idle();self.require_gradescope_roster(pid)
        students,roster_hash=self._roster_students(pid);ids=payload.get('packetIds')
        if (set(payload)!={'packetIds','rosterHash','reviewed'} or payload.get('reviewed') is not True
            or payload.get('rosterHash')!=roster_hash or not isinstance(ids,list) or not ids or len(ids)>2000 or len(set(ids))!=len(ids)):
            raise ValueError('Review the current roster matches before confirming them.')
        roster={s['id']:s for s in students};updates=[]
        for packet_id in ids:
            p,s,b=self._match_packet(packet_id)
            if s['project_id']!=pid:raise ValueError('Choose exams from this project only.')
            state=self.rows('SELECT status,data FROM scan_matching WHERE packet_id=?',(packet_id,))
            if not state or state[0]['status'] not in ('auto','manual'):raise ValueError('Resolve unmatched exams before confirming.')
            data=json.loads(state[0]['data']);student=roster.get(data.get('rosterId'))
            identity=self.rows('SELECT name,netid FROM scan_identities WHERE booklet_id=?',(b['id'],))
            if data.get('rosterHash')!=roster_hash or not student or not identity or identity[0]['netid']!=student['netid'] or identity[0]['name']!=student['name']:
                raise ValueError('A student match changed. Review it again.')
            updates.append(b['id'])
        with self.connect() as db:
            for bid in updates:db.execute('UPDATE scan_identities SET reviewed=1 WHERE booklet_id=?',(bid,))
            self.event(db,'student-matches-reviewed',pid,{'count':len(updates),'rosterHash':roster_hash})
        return {'reviewed':len(updates)}

    def review_student_suggestions(self,pid,payload):
        with self.lock:
            self._matching_write_idle();self.require_gradescope_roster(pid)
            students,sha=self._roster_students(pid);choices=payload.get('suggestions')
            if (set(payload)!={'suggestions','rosterHash','reviewed'} or payload.get('reviewed') is not True
                or payload.get('rosterHash')!=sha or not isinstance(choices,list) or not 1<=len(choices)<=2000
                or any(not isinstance(c,dict) or set(c)!={'packetId','studentId'} or any(not isinstance(v,str) for v in c.values()) for c in choices)):
                raise ValueError('Refresh and explicitly confirm the current roster suggestions.')
            if len({c['packetId'] for c in choices})!=len(choices) or len({c['studentId'] for c in choices})!=len(choices):
                raise ValueError('Some suggestions use the same student. Resolve those exams individually before confirming all suggestions.')
            current={r['id']:r for r in self.matching_list(pid)['items']};by_id={s['id']:s for s in students};updates=[]
            for choice in choices:
                item=current.get(choice['packetId']);student=by_id.get(choice['studentId'])
                if not item or item['status']!='unmatched' or not student or not item.get('suggestion') or item['suggestion']['id']!=student['id']:
                    raise ValueError('A suggestion changed. Refresh and review the named students again.')
                packet,source,booklet=self._match_packet(item['id']);self._source_bytes(source)
                updates.append((packet,booklet,student,item))
            with self.connect() as db:
                for packet,booklet,student,item in updates:
                    data={'rosterId':student['id'],'section':student['section'],'rosterHash':sha,'proposal':item['proposal']}
                    db.execute('INSERT OR REPLACE INTO scan_identities VALUES(?,?,?,?,?)',(booklet['id'],student['name'],student['netid'],1,stamp()))
                    db.execute('INSERT OR REPLACE INTO scan_matching VALUES(?,?,?,?)',(packet['id'],'manual',packed(data),stamp()))
                self.event(db,'student-suggestions-reviewed',pid,{'count':len(updates),'rosterHash':sha})
            return {'reviewed':len(updates)}

    def matching_list(self,pid):
        intake=self.intake_list(pid);students,roster_hash=self._roster_students(pid);states={r['packet_id']:r for r in self.rows('SELECT m.* FROM scan_matching m JOIN scan_packets p ON p.id=m.packet_id JOIN scan_sources s ON s.id=p.source_id WHERE s.project_id=?',(pid,))};items=[];matched=set()
        for f in intake['sources']:
            if f['deleted']:continue
            for b in f['booklets']:
                state=states.get(b['id']);data=json.loads(state['data']) if state else {};identity=b['identity'] or {};status=state['status'] if state else 'manual' if identity.get('name') or identity.get('netid') else 'unmatched'
                if status in ('auto','manual') and state and data.get('rosterHash')!=roster_hash:status='unmatched';data['reason']='The roster changed. Match this exam again.'
                version=next((v for v in intake['versions'] if v['id']==b['versionId']),None);fields=version['layout']['fields'] if version else {}
                if status in ('auto','manual'):matched.add(data.get('rosterId'))
                items.append({'id':b['id'],'number':len(items)+1,'sourceId':f['id'],'startPage':b['startPage'],'pages':b['pages'],'versionId':b['versionId'],'versionLabel':version['label'] if version else '', 'name':identity.get('name',''),'netid':identity.get('netid',''),'status':status,'section':data.get('section',''),'reason':data.get('reason',''),'proposal':data.get('proposal',{}),'studentId':data.get('rosterId',''),'identityReviewed':bool(identity.get('reviewed') and status!='unmatched'),'attempted':bool(state and data.get('rosterHash')==roster_hash),'previewFields':[name for name in ('name','netid') if fields.get(name)],'available':f['available']})
        available=[s for s in students if s['id'] not in matched]
        for item in items:
            item['suggestion']=suggest_identity_reading(item['proposal'],available) if item['status']=='unmatched' else None
        job_status=self._submission_job(self.submission_jobs,pid);job=job_status['id'] if job_status else None
        version_status=self._submission_job(self.version_jobs,pid);version_job=version_status['id'] if version_status else None
        return {'projectId':pid,'items':items,'roster':[{**{k:s[k] for k in ('id','name','netid','section')},'emails':s.get('emails',[])} for s in students],'rosterHash':roster_hash,'versionJob':{'id':version_job,'status':version_status['status']} if version_job else None,'unmatchedStudents':[s['id'] for s in students if s['id'] not in matched],'job':{'id':job,'status':job_status['status']} if job else None}

    def start_student_matching(self,pid):
        self.require_gradescope_roster(pid)
        self.one('projects',pid);old=self._submission_job(self.submission_jobs,pid)
        if old and old['status'] in ('queued','running'):return {'id':old['id']}
        self._matching_idle();students,roster_sha=self._roster_students(pid)
        if not students:raise ValueError('Confirm the Gradescope exam roster before matching students.')
        listing=self.matching_list(pid);pending=[r for r in listing['items'] if r['versionId'] and r['status']=='unmatched' and r['available']]
        if not pending:return {'noWork':True}
        packets=[]
        for item in pending:
            p,s,b=self._match_packet(item['id']);layout=self.layout_get(b['version_id'])
            if not layout['approved'] or not any(layout['fields'].get(f) for f in ('name','netid')):continue
            packets.append((p,s,b,self._recognition_context(s,p,self.rows('SELECT id,label FROM versions WHERE length(archived)=0 AND project_id=? ORDER BY rowid',(pid,)))))
        if not packets:raise ValueError('Save and approve the name/NetID boxes in Exam outline before matching students.')
        model=local_ai.DEFAULT_MODEL
        def read_batch(checkpoint,cache):
            checkpoint('Checking local vision model; the first reading may load it into memory...')
            nonlocal model
            if self.complete is local_ai.complete:
                installed={m['name'] for m in local_ai.models()}
                model=next((m for m in ('G-Scope:9b','qwen3.5:9b-q4_K_M') if m in installed),model)
                local_ai.validate_model(model,True)
            counts={'matched':0,'unmatched':0}
            for index,(p,s,b,context) in enumerate(packets,1):
                checkpoint({'stage':'matching','message':f'Matching exam {index} of {len(packets)}…','completed':index-1,'total':len(packets)});proposal={}
                try:
                    with self.lock:
                        saved=self.rows('SELECT status,data FROM scan_matching WHERE packet_id=?',(p['id'],))
                        if saved and (saved[0]['status']=='manual' or json.loads(saved[0]['data']).get('manualHold')):continue
                    fields=self.layout_get(b['version_id'])['fields'];names=[n for n in ('name','netid') if fields.get(n)]
                    if cache.get('source')!=s['id']:
                        if cache.get('doc'):cache['doc'].close()
                        raw=self._source_bytes(s);cache['doc']=MarkerDocument(raw,self.lock);cache['source']=s['id']
                    rotation=json.loads(s['layout']).get('rotation',0)
                    crops=[(n,next(cache['doc'].crops(p['start']+fields[n]['page']-1,rotation,[fields[n]['rect']]))) for n in names]
                    actual=self.complete is local_ai.complete
                    images=[identity_sheet(crops)] if actual else [base64.b64encode(raw).decode('ascii') for _,raw in crops]
                    text=packed({'imageOrder':names})+'\nRead only the handwriting in the labeled name and NetID panels. Ignore printed labels, guide lines and example IDs. Never infer missing characters from a name or a roster. Return an empty string for an unreadable field. One clearly readable field is sufficient; needsReview is true if the identity cannot be read reliably. Keep reason empty unless ambiguous.'
                    result,_=self.complete(TRANSCRIPTION_SYSTEM,text,images=images,schema=IDENTITY_SCHEMA,model=model,max_tokens=140,context=2048,checked=True);checkpoint()
                    if not isinstance(result,dict) or set(result)!=set(IDENTITY_SCHEMA['required']) or type(result['needsReview']) is not bool:raise ValueError('The field reading needs review.')
                    proposal={n:short_text(result[n],160 if n=='name' else 40) for n in ('name','netid')};proposal['reason']=short_text(result['reason'],240);proposal['needsReview']=result['needsReview']
                    for field in ('name','netid'):
                        if field not in names:proposal[field]=''
                    student={**resolve_identity_reading({**proposal,'needsReview':result['needsReview']},students)}
                    with self.lock:
                        checkpoint();current,source,booklet=self._match_packet(p['id']);self._source_bytes(source)
                        saved=self.rows('SELECT status,data FROM scan_matching WHERE packet_id=?',(p['id'],))
                        if saved and (saved[0]['status']=='manual' or json.loads(saved[0]['data']).get('manualHold')):continue
                        if self._roster_students(pid)[1]!=roster_sha or self._recognition_context(source,current,self.rows('SELECT id,label FROM versions WHERE length(archived)=0 AND project_id=? ORDER BY rowid',(pid,)))!=context:raise ValueError('The roster or exam layout changed. Match this exam again.')
                        self._write_identity(p['id'],student,'auto',roster_sha)
                        saved=self.rows('SELECT data FROM scan_matching WHERE packet_id=?',(p['id'],))[0]
                        state=json.loads(saved['data']);state.update(proposal=proposal,recognitionContext=context,readerModel=model)
                        if proposal['needsReview'] or proposal.get('netid','').casefold()!=student.get('netid','').casefold():
                            state['reason']='Both fields support this roster student. Verify the handwritten characters before confirming.'
                        self._save_match(p['id'],'auto',state)
                    counts['matched']+=1
                except ValueError as error:
                    checkpoint()
                    with self.lock:
                        saved=self.rows('SELECT status,data FROM scan_matching WHERE packet_id=?',(p['id'],))
                        if saved and (saved[0]['status']=='manual' or json.loads(saved[0]['data']).get('manualHold')):continue
                        self._save_match(p['id'],'unmatched',{'reason':str(error),'proposal':proposal,'rosterHash':roster_sha})
                    counts['unmatched']+=1
                checkpoint({'stage':'matching','message':f'Read {index} of {len(packets)} exams','completed':index,'total':len(packets)})
            return counts
        def action(checkpoint):
            cache={}
            try:return read_batch(checkpoint,cache)
            finally:
                if cache.get('doc'):cache['doc'].close()
        job=self.jobs.submit(action,controlled=True,user_errors=True);self.submission_jobs[pid]=job['id'];self.scan_jobs.add(job['id']);return job

    def local_ai_settings_save(self,data):
        self._archive_idle()
        import local_ai_config,urllib.request
        registry=self.root.parent/'Integration/servers.json'
        if registry.is_file():
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for key,value in json.loads(registry.read_text('utf-8-sig')).items():
                if key not in ('recommendations','integrity') or not isinstance(value,dict):continue
                url=value.get('url','')
                if not re.fullmatch(r'http://127\.0\.0\.1:\d+',url):continue
                try:
                    with opener.open(url+'/api/health',timeout=2) as response:health=json.load(response)
                except OSError:continue
                if health.get('busy'):raise ValueError('Wait for active local AI jobs to finish before changing the shared connection.')
        return local_ai_config.save(data)
