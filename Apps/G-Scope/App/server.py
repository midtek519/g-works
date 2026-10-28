"""Private Grader HTTP service. Loopback, same-origin writes and fixed assets."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import argparse,json,mimetypes,os,secrets,sys,threading

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import integration_paths
APP_ROOT=integration_paths.app_root()
if APP_ROOT:os.environ['GWORKS_APP_ROOT']=str(APP_ROOT)
sys.path.insert(0,str(APP_ROOT/'Dependencies/ScopeVendor' if APP_ROOT else HERE.parent/'vendor'))
GVAULT=integration_paths.vault_root()
TEACHING=integration_paths.teaching_code()
AI_ASSETS=TEACHING/'private_module_ui'
sys.path.insert(0,str(AI_ASSETS));sys.path.insert(0,str(HERE))
from grader import Store
import local_ai

def make_server(store,port=0):
    previous_token=os.environ.get('GSCOPE_SESSION_TOKEN','')
    token=previous_token if __import__('re').fullmatch(r'[A-Za-z0-9_-]{32,128}',previous_token) else secrets.token_urlsafe(32)
    parent=os.environ.get('GWHIZ_PARENT_ORIGIN','');embed_key=os.environ.get('GWHIZ_EMBED_KEY','')
    if not __import__('re').fullmatch(r'http://127\.0\.0\.1:\d+',parent):parent=''
    static=HERE/'static'
    public_root=APP_ROOT if APP_ROOT and store.root==APP_ROOT/'Data' else store.root
    account=__import__('chatgpt_account').Account(APP_ROOT or GVAULT)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def guard(self,write=False):
            expected='127.0.0.1:'+str(self.server.server_port);origin=self.headers.get('Origin','');parsed=urlsplit(self.path)
            if self.headers.get('Host')!=expected:raise PermissionError('Use the local G-Scope address.')
            if not write and parsed.path=='/' and parent and embed_key and self.headers.get('Sec-Fetch-Dest')=='iframe' and self.headers.get('Referer','').rstrip('/')==parent and secrets.compare_digest(parse_qs(parsed.query).get('gwhiz_embed',[''])[0],embed_key):return
            if origin and origin!='http://'+expected:raise PermissionError('Only the local G-Scope can access its records.')
            if self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site'):raise PermissionError('Open the local G-Scope directly.')
            if write and not secrets.compare_digest(self.headers.get('X-App-Token',''),token):raise PermissionError('Refresh G-Scope before changing this project.')
        def respond(self,status,value,mime='application/json; charset=utf-8',download=None):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"+(' '+parent if parent else ''))
            if download:self.send_header('Content-Disposition','attachment; filename="'+download+'"')
            self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_OPTIONS(self):self.respond(403,{'error':'Cross-origin requests are not allowed.'})
        def do_GET(self):
            try:
                self.guard();url=urlsplit(self.path);parts=url.path.strip('/').split('/');query=parse_qs(url.query)
                if url.path=='/api/health':return self.respond(200,{'reviewedOnlineGrading':1,'codeGeneration':__import__('os').environ.get('GWORKS_CODE_GENERATION',''),'app':'GScope','responseGrading':3,'answerGrouping':1,'choiceMarkReader':1,'questionVersionBatch':1,'assignmentWorkflow':1,'root':str(public_root),'dataRoot':str(store.root),'aiRouting':1,'generalAITransport':2,'draftingContext':2,'projectTrashClear':1,'busy':store.archive_busy(),'version':'1.0.0-beta.3'})
                if url.path=='/online-grading.js':return self.respond(200,(static/'online-grading.js').read_bytes(),'text/javascript; charset=utf-8')
                if url.path=='/api/general-ai/settings':return self.respond(200,{'configuration':__import__('general_ai').settings(),'account':account.status()})
                if url.path=='/api/general-ai/account':return self.respond(200,account.status())
                if url.path=='/api/answer-groups':return self.respond(200,store.answer_groups(query.get('questionId',[''])[0],project_id=query.get('projectId',[None])[0]))
                if url.path=='/api/crop':return self.respond(200,store.crop(query.get('bookletId',[''])[0],query.get('questionId',[''])[0]),'image/png')
                if url.path=='/api/bootstrap':return self.respond(200,{'token':token,'projects':store.projects(),'projectTrash':store.project_trash(),'projectTrashClear':1,'projectTrashCleanup':store.project_trash_cleanup(),'active':store.active,'parentOrigin':parent,'rubrics':store.library_list(),'projectOptions':store.project_options(),'defaultModel':local_ai.DEFAULT_MODEL,'localAIProvider':__import__('local_ai_config').settings()['provider'],'generalAI':__import__('general_ai').connection_info()})
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='exam-sources':return self.respond(200,store.project_exam_sources(parts[2]))
                if url.path=='/api/local-ai/readiness':return self.respond(200,__import__('local_ai_config').readiness())
                if url.path=='/api/local-ai/settings':return self.respond(200,__import__('local_ai_config').settings())
                if url.path=='/api/models':return self.respond(200,{'models':local_ai.models(),'default':local_ai.DEFAULT_MODEL})
                if parts==['api','scans','cleanup-options']:return self.respond(200,store.scan_cleanup_options())
                if len(parts)==4 and parts[:2]==['api','questions'] and parts[3]=='template-crop':return self.respond(200,store.blank_question_crop(parts[2]),'image/png')
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='grading-status':return self.respond(200,store.grading_status(parts[2],thinking=query.get('thinking',['0'])[0]!='0'))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='export':
                    value=store.export_version(parts[2]);label=__import__('re').sub(r'[^A-Za-z0-9_-]','',value['exam']['version'])[:30] or 'Exam';return self.respond(200,value,download='G-Scope-Version-'+label+'.json')
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='answer-keys':return self.respond(200,store.answer_keys_list(parts[2]))
                if parts==['api','rubrics']:return self.respond(200,store.library_list())
                if len(parts)==3 and parts[:2]==['api','rubrics']:return self.respond(200,store.library_get(parts[2]))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='box-copy-options':return self.respond(200,store.box_copy_options(parts[2]))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='identity-layout':return self.respond(200,store.layout_get(parts[2]))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='decisions':return self.respond(200,store.consistency_list(parts[2]))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='handout-builds':return self.respond(200,store.handout_builds(parts[2]))
                if len(parts)>=4 and parts[:2]==['api','versions'] and parts[3]=='materials':
                    if len(parts)==4:return self.respond(200,store.materials_list(parts[2]))
                    if len(parts)==5 and parts[4]=='catalog':return self.respond(200,store.materials_catalog(parts[2]))
                    if len(parts)==7 and parts[4]=='source' and parts[6]=='pdf':return self.respond(200,store.materials_source_pdf(parts[2],parts[5]),'application/pdf')
                    if len(parts)==6 and parts[4]=='source':return self.respond(200,store.materials_source(parts[2],parts[5]))
                    if len(parts)==6 and parts[4]=='reference':return self.respond(200,store.materials_reference(parts[2],parts[5]))
                    if len(parts)==7 and parts[4]=='reference' and parts[6]=='pdf':return self.respond(200,store.materials_pdf(parts[2],parts[5]),'application/pdf')
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='matching':return self.respond(200,store.matching_list(parts[2]))
                if len(parts)==5 and parts[:2]==['api','intake-booklets'] and parts[3]=='identity':return self.respond(200,store.matching_crop(parts[2],parts[4]),'image/png')
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='roster-sources':return self.respond(200,store.roster_sources(parts[2]))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='roster':return self.respond(200,store.roster_get(parts[2]))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='intake':return self.respond(200,store.intake_list(parts[2]))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='workflow-status':return self.respond(200,store.assignment_progress(parts[2]))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='batch':return self.respond(200,store.project_batch(parts[2]))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='export':return self.respond(200,store.export_project(parts[2]),download='G-Scope-student-suggestions.json')
                if len(parts)==5 and parts[:2]==['api','intake-files'] and parts[3]=='page':return self.respond(200,store.intake_page(parts[2],int(parts[4]),rotation=int(query['rotation'][0]) if 'rotation' in query else None),'image/png')
                if len(parts)==5 and parts[:2]==['api','intake-files'] and parts[3]=='thumbnail':return self.respond(200,store.intake_thumbnail(parts[2],int(parts[4])),'image/png')
                if len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='consistency':return self.respond(200,store.consistency_report(parts[2]))
                if parts==['api','projects']:return self.respond(200,{'projects':store.projects(),'trash':store.project_trash(),'trashCleanup':store.project_trash_cleanup()})
                if len(parts)==3 and parts[:2]==['api','versions']:return self.respond(200,store.version(parts[2]))
                if len(parts)==5 and parts[:2]==['api','files'] and parts[3]=='page':return self.respond(200,store.page(parts[2],int(parts[4]),rotation=int(query['rotation'][0]) if 'rotation'in query else None),'image/png')
                if len(parts)==5 and parts[:2]==['api','booklets'] and parts[3]=='crop':return self.respond(200,store.crop(parts[2],parts[4]),'image/png')
                if len(parts)==3 and parts[:2]==['api','runs']:return self.respond(200,store.run(parts[2]))
                if len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='export':return self.respond(200,store.export(parts[2]),download='Rubric-Lens-suggestions.json')
                if len(parts)==6 and parts[:2]==['api','runs'] and parts[3]=='proposals' and parts[5]=='crop':return self.respond(200,store.run_crop(parts[2],parts[4]),'image/png')
                if len(parts)==3 and parts[:2]==['api','jobs']:return self.respond(200,store.jobs.get(parts[2]))
                if url.path.startswith('/vendor/katex/'):
                    from materials_links import safe_file
                    relative=url.path[len('/vendor/katex/'):];vendor=TEACHING/'static/vendor/katex'
                    if relative not in ('katex.min.js','katex.min.css') and not __import__('re').fullmatch(r'fonts/KaTeX_[A-Za-z0-9_-]+\.woff2',relative):return self.respond(404,{'error':'Unavailable preview asset.'})
                    file=safe_file(vendor/relative,[vendor],{'.js','.css','.woff2'});return self.respond(200,file.read_bytes(),'font/woff2' if file.suffix=='.woff2' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                assets={'/grading-workspace.js':'grading-workspace.js','/grading-workspace.css':'grading-workspace.css','/g-scope.svg':'g-scope.svg','/response-editor.js':'response-editor.js','/grading.js':'grading.js','/progress.js':'progress.js','/':'index.html','/index.html':'index.html','/app.js':'app.js','/latex-editor.js':'latex-editor.js','/tex-editors.js':'tex-editors.js','/solution-preview.js':'solution-preview.js','/local-ai-settings.js':'local-ai-settings.js','/style.css':'style.css','/workflow.js':'workflow.js','/consistency.js':'consistency.js','/materials.js':'materials.js','/answer-keys.js':'answer-keys.js','/rosters.js':'rosters.js','/matching.js':'matching.js','/outline.js':'outline.js','/outline-tree.js':'outline-tree.js'}
                if url.path in assets:
                    file=static/assets[url.path];raw=file.read_bytes()
                    if file.suffix=='.html' and parent:raw=raw.replace(b'<script defer src="/app.js"',('<script data-gwhiz-module="grader" data-gwhiz-parent="'+parent+'" defer src="/app.js"').encode())
                    return self.respond(200,raw,mimetypes.guess_type(file.name)[0]+('; charset=utf-8' if file.suffix in ('.html','.js','.css') else ''))
                return self.respond(404,{'error':'This local page is unavailable.'})
            except PermissionError as error:self.respond(403,{'error':str(error)})
            except (ValueError,KeyError,StopIteration):self.respond(400,{'error':str(sys.exception()) if isinstance(sys.exception(),ValueError) else 'Check the selected item.'})
            except Exception:self.respond(500,{'error':'This local item could not be opened. Saved sources are unchanged.'})
        def do_POST(self):
            with store.lock:return self.post_action()
        def post_action(self):
            self._post_body_read=False
            try:
                url=urlsplit(self.path);parts=url.path.strip('/').split('/');query=parse_qs(url.query)
                if url.path=='/__gwhiz/stop':
                    if not embed_key or self.headers.get('Host')!='127.0.0.1:'+str(self.server.server_port) or self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site') or not secrets.compare_digest(self.headers.get('X-GWhiz-Module-Key',''),embed_key):raise PermissionError('Unavailable action.')
                    if store.archive_busy():return self.respond(409,{'error':'Local processing is active. Finish or pause it first.'})
                    self.respond(200,{'stopped':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
                self.guard(True);length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=200_000_000:raise ValueError('Choose a nonempty request up to 200 MB.')
                raw=self.rfile.read(length)
                self._post_body_read=True
                if len(raw)!=length:raise ValueError('The upload did not finish.')
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='roster-upload':return self.respond(200,store.roster_upload(parts[2],query.get('name',[''])[0],raw))
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='intake-files':
                    fresh=query.get('freshRemoved',['0'])
                    if fresh not in (['0'],['1']):raise ValueError('Choose whether a removed scan should start a fresh import.')
                    return self.respond(200,store.intake_upload(parts[2],query.get('name',[''])[0],raw,fresh_removed=fresh==['1']))
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='files':return self.respond(200,store.upload(parts[2],query.get('kind',[''])[0],query.get('name',[''])[0],raw))
                if len(parts)==7 and parts[:2]==['api','versions'] and parts[3:5]==['materials','reference'] and parts[6]=='replace':return self.respond(200,store.materials_replace(parts[2],parts[5],query.get('name',[''])[0],raw,query.get('sha256',[''])[0]))
                if len(parts)==5 and parts[:2]==['api','versions'] and parts[3:]==['materials','upload']:return self.respond(200,store.materials_upload(parts[2],query.get('name',[''])[0],raw,query.get('role',[''])[0]))
                if length>2_000_000 or not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('Use the local project controls.')
                data=json.loads(raw)
                if not isinstance(data,dict):raise ValueError('Check the supplied fields.')
                if len(parts)==4 and parts[:2]==['api','versions'] and parts[3] in ('online-preview','online-start'):
                    method={'online-preview':store.online_preview,'online-start':store.online_start}[parts[3]]
                    return self.respond(200,method(parts[2],data))
                if url.path=='/api/installer-stop':
                    if store.archive_busy() or account.pending:raise ValueError('Finish local processing and account sign-in before updating.')
                    self.respond(200,{'stopped':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
                if url.path.startswith('/api/general-ai/'):
                    command=url.path.removeprefix('/api/general-ai/')
                    if command=='settings':result={'configuration':__import__('general_ai').save(data)}
                    elif command=='account/start' and set(data)<= {'profile'}:result=account.start(data.get('profile',''))
                    elif command=='account/cancel' and not data:result=account.cancel()
                    elif command=='account/select' and set(data)=={'profile'}:result=account.select(data['profile'])
                    elif command=='account/signout' and not data:result=account.logout()
                    elif command=='account/models' and not data:result=account.models()
                    elif command=='account/welcome' and not data:result=account.acknowledge()
                    else:raise ValueError('Choose an AI settings action.')
                elif url.path=='/api/answer-groups':result=store.change_answer_groups(data.get('questionId'),data)
                elif len(parts)==4 and parts[:2]==['api','questions'] and parts[3]=='grading-setup':result=store.grading_setup(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','intake-files'] and parts[3]=='layout':result=store.intake_layout(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','intake-files'] and parts[3]=='reimport':result=store.intake_reimport_removed(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','projects'] and parts[3]=='roster' and parts[4] in ('pull','apply','clear','check'):result={'pull':store.roster_pull,'apply':store.roster_apply,'clear':store.roster_clear,'check':store.roster_check}[parts[4]](parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','projects'] and parts[3:] == ['roster','student']:result=store.roster_student_save(parts[2],data)
                elif len(parts)==6 and parts[:2]==['api','projects'] and parts[3:] == ['roster','student','remove']:result=store.roster_student_remove(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='review-scans':result=store.review_scans(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='prepare-scans':result=store.prepare_scans(parts[2])
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='review-student-matches':result=store.review_student_matches(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='roster-reuse':result=store.roster_reuse(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='review-student-suggestions':result=store.review_student_suggestions(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='match-students':result=store.start_student_matching(parts[2])
                elif len(parts)==4 and parts[:2]==['api','intake-files'] and parts[3]=='confirm-splits':result=store.confirm_scan_splits(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','intake-files'] and parts[3]=='review-versions':result=store.review_packet_versions(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','intake-files'] and parts[3]=='version':result=store.set_source_version(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','intake-booklets'] and parts[3]=='version':result=store.set_packet_version(parts[2],data.get('versionId'))
                elif len(parts)==4 and parts[:2]==['api','intake-booklets'] and parts[3]=='student':result=store.match_manually(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','intake-booklets'] and parts[3:]==['student','clear']:result=store.clear_student_match(parts[2],data)
                elif parts==['api','local-ai','start-engine']:result=__import__('local_ai_config').start_engine(confirmed=data.get('confirmed'))
                elif parts==['api','local-ai','check']:result=__import__('local_ai_config').check(data)
                elif parts==['api','local-ai','settings']:result=store.local_ai_settings_save(data)
                elif parts==['api','scans','cleanup-preview']:result=store.scan_cleanup_preview(data)
                elif parts==['api','scans','cleanup']:result=store.scan_cleanup_execute(data)
                elif len(parts)==4 and parts[:2]==['api','intake-booklets'] and parts[3]=='assign':result=store.intake_assign(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='cancel':
                    if set(data)-{'immediate'} or not isinstance(data.get('immediate',False),bool):raise ValueError('Choose a stop action.')
                    result=store.jobs.cancel(parts[2],immediate=data.get('immediate',False))
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3] in ('recognize','cleanup-preview','cleanup','share-rubric','process','pause'):
                    action=parts[3];pid=parts[2]
                    if action=='recognize':result=store.intake_recognize(pid,data)
                    elif action=='cleanup-preview':result=store.cleanup_preview(pid,data)
                    elif action=='cleanup':result=store.cleanup_execute(pid,data)
                    elif action=='share-rubric':result=store.share_rubric(pid,data)
                    elif action=='process':result=store.start_project(pid,data)
                    elif action=='pause':result=store.pause_project(pid)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3:] == ['decisions','discuss']:result=store.consistency_discuss(parts[2],data)
                elif len(parts)==6 and parts[:2]==['api','versions'] and parts[3]=='decisions' and parts[5]=='deactivate':result=store.consistency_deactivate(parts[2],parts[4],data)
                elif len(parts)==7 and parts[:2]==['api','versions'] and parts[3:5]==['materials','reference'] and parts[6]=='remove':result=store.materials_remove(parts[2],parts[5],data)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3]=='materials':
                    if parts[4]=='link':result=store.materials_link(parts[2],data)
                    elif parts[4]=='solutions':result=store.materials_solutions(parts[2],data)
                    elif parts[4]=='use-handout':result=store.materials_use_handout(parts[2],data)
                    else:raise ValueError('Choose a Materials source action.')
                elif len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='response-keys':result=store.response_keys(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','versions'] and parts[3]=='response-suggestions':result=store.response_suggestions(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3:]==['answer-keys','draft']:result=store.draft_answer_keys(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3:]==['answer-keys','manual']:result=store.save_manual_answer(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3:]==['answer-keys','discard']:result=store.discard_answer_keys(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','versions'] and parts[3:]==['answer-keys','approve-all']:result=store.approve_answer_keys(parts[2],data)
                elif len(parts)==6 and parts[:2]==['api','versions'] and parts[3]=='answer-keys' and parts[5]=='approve':result=store.approve_answer_key(parts[2],parts[4],data)
                elif parts==['api','rubrics','open-folder']:
                    if data:raise ValueError('Use the fixed rubric folder button.')
                    result=store.open_rubric_folder()
                elif parts==['api','rubrics']:result=store.library_import(data)
                elif len(parts)==4 and parts[:2]==['api','rubrics'] and parts[3] in ('rename','delete'):result=store.library_rename(parts[2],data) if parts[3]=='rename' else store.library_delete(parts[2],data)
                elif parts==['api','projects','trash','clear']:result=store.clear_project_trash(data)
                elif parts==['api','projects']:result=store.create(data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='delete':result=store.delete_project(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='restore':result=store.restore_project(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='rename-versions':result=store.rename_versions(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='versions':result=store.add_version(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','files'] and parts[3]=='layout':result=store.layout(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','versions']:
                    vid,action=parts[2:]
                    if action=='remove':result=store.remove_version(vid,data)
                    elif action=='restore':result=store.restore_version(vid,data)
                    elif action=='identity-layout':result=store.layout_save(vid,data)
                    elif action=='outline-suggestions':result=store.outline_suggest(vid)
                    elif action=='copy-boxes':result=store.copy_boxes(vid,data)
                    elif action=='outline-tree':result=store.save_outline_tree(vid,data)
                    elif action=='generate-rubric':result=store.generate_rubric(vid,data.get('model',local_ai.DEFAULT_MODEL))
                    elif action=='setup-handout-build':result=store.setup_handout_build(vid,data)
                    elif action=='approve-all-crops':result=store.approve_all_crops(vid,data)
                    elif action=='decisions':result=store.consistency_save(vid,data)
                    elif action=='rubric':result=store.import_rubric(vid,data)
                    elif action=='rubric-export':result=store.import_export(vid,data)
                    elif action=='normalize':result=store.normalize(vid,data.get('model',local_ai.DEFAULT_MODEL))
                    elif action=='questions':result=store.save_questions(vid,data)
                    elif action=='approve':result=store.approve_rubric(vid,data)
                    elif action=='runs':result=store.start(vid,data)
                    elif action=='use-rubric':result=store.library_use(vid,data)
                    elif action=='save-library-rubric':result=store.library_save_version(vid,data)
                    elif action=='handout-link':result=store.handout_link(vid,data)
                    else:raise ValueError('Choose a version action.')
                elif len(parts)==4 and parts[:2]==['api','questions'] and parts[3]=='approve-crop':result=store.approve_crop(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','booklets'] and parts[3]=='link':result=store.link(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='abandon':result=store.abandon_run(parts[2],data)
                elif len(parts)==5 and parts[:2]==['api','projects'] and parts[3:]==['grading','reset-preview']:result=store.grading_reset_preview(parts[2])
                elif len(parts)==5 and parts[:2]==['api','projects'] and parts[3:]==['grading','reset']:result=store.grading_reset(parts[2],data)
                elif len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='pause':result=store.pause(parts[2])
                elif len(parts)==4 and parts[:2]==['api','proposals'] and parts[3]=='review':result=store.review(parts[2],data)
                else:return self.respond(404,{'error':'This local action is unavailable.'})
                return self.respond(200,result)
            except PermissionError as error:
                self.close_connection=True
                timeout=self.connection.gettimeout()
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not self._post_body_read and 0<length<=64*1024:
                        self.connection.settimeout(.25);self.rfile.read(length)
                except (OSError,ValueError):pass
                finally:self.connection.settimeout(timeout)
                self.respond(403,{'error':str(error)})
            except ValueError as error:
                message=str(error)
                self.respond(400,{'error':message if len(message)<250 and '\\' not in message and '\n' not in message else 'Check the local project fields and retry.'})
            except Exception:self.respond(500,{'error':'The local action could not finish. Saved sources and existing recorded grades are unchanged.'})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
    data_root=args.root/'Data' if APP_ROOT and args.root.resolve()==APP_ROOT else args.root
    store=Store(data_root);server=make_server(store,args.port);status=args.root/'Temp/server-status.json' if data_root!=args.root else store.tools/'server-status.json';status.parent.mkdir(parents=True,exist_ok=True)
    status.write_text(json.dumps({'pid':os.getpid(),'url':'http://127.0.0.1:'+str(server.server_port),'root':str(args.root),'app':'GScope'}),'utf-8')
    try:server.serve_forever()
    finally:server.server_close()
