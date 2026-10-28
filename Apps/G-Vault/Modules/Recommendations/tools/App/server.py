"""Loopback-only letters application; all content and files remain local."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gwhiz_embed as embed
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,unquote
import json,secrets,mimetypes,argparse,traceback,os,datetime
from store import Store,atomic_json,text
import grades
AI_ASSETS=(Path(__file__).resolve().parents[5]/'Dependencies/TeachingApp').resolve()/'private_module_ui'
sys.path.insert(0,str(AI_ASSETS))
import local_ai

def make_server(store,port=0):
    token=secrets.token_urlsafe(32);static=Path(__file__).with_name('static');drafting=local_ai.ApprovedDrafting(store,'recommendations')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def trusted(self):
            hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if self.headers.get('Host')not in hosts:return False
            if embed.navigation(self):return True
            origin=self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site')in ('cross-site','same-site')and origin not in {'http://'+h for h in hosts}:return False
            return not origin or origin in {'http://'+h for h in hosts}
        def respond(self,status,data,kind='application/json; charset=utf-8',name=None):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf8')if kind.startswith('application/json')else data if isinstance(data,bytes)else str(data).encode('utf8')
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            for k,v in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',**embed.frame_headers(),'Content-Security-Policy':embed.csp("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")}.items():self.send_header(k,v)
            if name:self.send_header('Content-Disposition','inline; filename="'+name.replace('"','')+'"')
            self.end_headers()
            try:self.wfile.write(body)
            except(BrokenPipeError,ConnectionResetError):pass
        def file(self,path):
            p=Path(path);kind=mimetypes.guess_type(p.name)[0]or'application/octet-stream'
            if p.suffix.lower()=='.txt':kind='text/plain; charset=utf-8'
            # Stable ASCII response filenames avoid leaking names into headers.
            self.respond(200,p.read_bytes(),kind,'local-document'+p.suffix.lower())
        def fail(self,status,message):self.respond(status,{'error':message})
        def internal(self):
            (store.tools/'logs'/'private-errors.txt').write_text(traceback.format_exc(),encoding='utf8')
            self.fail(500,'The action could not finish. Details stay in the local error log; your saved originals are preserved.')
        def do_OPTIONS(self):self.fail(403,'Cross-origin requests are not allowed.')
        def do_GET(self):
            if not self.trusted():return self.fail(403,'Open the app at its local address.')
            if embed.serve_ui(self,static):return
            url=urlsplit(self.path);path=unquote(url.path);query=parse_qs(url.query)
            try:
                if path=='/local-ai.js':return self.file(AI_ASSETS/'local_ai_ui.js')
                if path=='/local-ai.css':return self.file(AI_ASSETS/'local_ai_ui.css')
                if path=='/api/local-ai/models':return self.respond(200,{'models':local_ai.models()})
                if path=='/api/local-ai/connection':return self.respond(200,__import__('general_ai').connection_info())
                if __import__('re').fullmatch(r'/api/local-ai/jobs/[a-f0-9]{32}',path):return self.respond(200,drafting.jobs.get(path.rsplit('/',1)[1]))
                if path=='/api/health':return self.respond(200,{'codeGeneration':__import__('os').environ.get('GWORKS_CODE_GENERATION',''),'app':'MHRecommendations','root':str(store.root),'version':1,'aiRouting':1,'generalAITransport':2,'signatureSettings':1,'busy':drafting.jobs.busy()})
                if path=='/api/bootstrap':return self.respond(200,{**store.bootstrap(),'token':token})
                if path=='/api/archive':return self.respond(200,store.archive_data())
                if path=='/api/profile':return self.respond(200,store.bootstrap()['profile'])
                if path=='/api/letters':return self.respond(200,{'letters':store.letters()})
                if path=='/api/people/by-ruid':return self.respond(200,{'person':store.person_by_ruid(query.get('ruid',[''])[0])})
                if path=='/api/grades/search':return self.respond(200,grades.search_students(store.grade_database(query.get('course',[''])[0]),query.get('q',[''])[0]))
                if path=='/api/grades/records':
                    ruid=query.get('ruid',[''])[0]
                    if not __import__('re').fullmatch(r'\d{9}',ruid):raise ValueError('Use a nine-digit RUID to load local course records.')
                    return self.respond(200,grades.student_records(store.grade_database(query.get('course',[''])[0]),ruid,store.settings.get('academic_year_start_month',9)))
                if __import__('re').fullmatch(r'/api/students/REC-\d{4,8}/course-suggestions',path):return self.respond(200,store.course_suggestions(path.split('/')[3]))
                if path.startswith('/api/students/'):return self.respond(200,store.student(path.rsplit('/',1)[1]))
                if path.startswith('/api/letters/'):return self.respond(200,store.letter(path.rsplit('/',1)[1]))
                if path.startswith('/api/files/'):return self.file(store.archive_file(path.rsplit('/',1)[1])[0])
                if path.startswith('/api/notes/'):
                    parts=path.split('/')
                    if len(parts)==6 and parts[5]=='text':return self.respond(200,store.extract_note_text(parts[3],parts[4]))
                    if len(parts)!=5:raise ValueError('The local note was not found.')
                    return self.file(store.note_attachment_path(parts[3],parts[4]))
                if path.startswith('/api/pdfs/'):
                    parts=path.split('/')
                    if len(parts)!=5:raise ValueError('PDF unavailable.')
                    return self.file(store.pdf_path(parts[3],parts[4]))
                if path.startswith('/api/briefs/'):
                    name=path.rsplit('/',1)[1]
                    if not __import__('re').fullmatch(r'REC-\d+-L-\d+-[A-Za-z0-9-]+\.txt',name):raise ValueError('Approved brief unavailable.')
                    p=store.tools/'Approved Briefs'/name
                    if not p.is_file():raise ValueError('Approved brief unavailable.')
                    return self.file(p)
                if path.startswith('/api/'):return self.fail(404,'That page was not found.')
                allowed={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/wizard.js':'wizard.js','/style.css':'style.css','/interview-form.html':'interview-form.html','/interview-form.js':'interview-form.js'}
                if path not in allowed:return self.fail(404,'That page was not found.')
                return self.file(static/allowed[path])
            except grades.GradesUnavailableError as exc:self.fail(400,str(exc))
            except(ValueError,KeyError):self.fail(400,str(sys.exception())if isinstance(sys.exception(),ValueError)else'Check the selected record.')
            except Exception:self.internal()
        def do_POST(self):
            if embed.stop_request(self,store,busy=drafting.jobs.busy):return
            if not self.trusted()or not secrets.compare_digest(self.headers.get('X-App-Token',''),token):return self.fail(403,'Reopen the app before making changes.')
            try:
                url=urlsplit(self.path);path=unquote(url.path)
                n=int(self.headers.get('Content-Length','0'))
                note_route=__import__('re').fullmatch(r'/api/students/(REC-\d{4,8})/notes',path)
                if path=='/api/archive/upload':
                    if not 0<n<=50*1024*1024:raise ValueError('Choose a letter no larger than 50 MiB.')
                    data=self.rfile.read(n)
                    if len(data)!=n:raise ValueError('The upload did not finish. Try again.')
                    return self.respond(200,store.import_source(parse_qs(url.query).get('name',[''])[0],data))
                if note_route:
                    if not 0<n<=50*1024*1024:raise ValueError('Upload a nonempty file no larger than 50 MiB.')
                    data=self.rfile.read(n)
                    if len(data)!=n:raise ValueError('The upload did not finish. Try again.')
                    name=parse_qs(url.query).get('name',[''])[0]
                    return self.respond(200,store.save_note_attachment(note_route[1],name,data))
                if n<1 or n>4_000_000:return self.fail(400,'The request is too large or empty.')
                payload=json.loads(self.rfile.read(n))
                if not isinstance(payload,dict):raise ValueError('Check the supplied information.')
                path=unquote(urlsplit(self.path).path)
                if path=='/api/local-ai/brief':result=drafting.brief(payload)
                elif path=='/api/local-ai/jobs':result=drafting.start(payload)
                elif path=='/api/local-ai/apply':result=drafting.apply(payload)
                elif __import__('re').fullmatch(r'/api/local-ai/jobs/[a-f0-9]{32}/cancel',path):result=drafting.jobs.cancel(path.split('/')[-2])
                elif path=='/api/output-folder':result=store.open_output_folder()
                elif path=='/api/students':result=store.save_student(payload)
                elif __import__('re').fullmatch(r'/api/students/REC-\d{4,8}/delete',path):result=store.delete_person(path.split('/')[3],payload)
                elif path.startswith('/api/students/'):result=store.save_student(payload,path.rsplit('/',1)[1])
                elif path=='/api/letters':result=store.save_letter(payload)
                elif path.startswith('/api/letters/'):
                    parts=path.split('/');identity=parts[3]
                    if len(parts)==4:result=store.save_letter(payload,identity)
                    elif len(parts)==5 and parts[4]=='delete':result=store.delete_letter(identity,payload)
                    elif len(parts)==5 and parts[4]=='brief':result=store.brief(identity,payload)
                    elif len(parts)==5 and parts[4]=='build':result=store.build(identity,payload)
                    else:return self.fail(404,'Action not found.')
                elif path=='/api/archive/link':result=store.link_archive(payload)
                elif path=='/api/archive/import-letter':result=store.import_letter(payload)
                elif path=='/api/archive/refresh':result=store.refresh_archive()
                elif path=='/api/profile':result=store.save_profile(payload)
                elif path=='/api/style-guide':
                    (store.tools/'writing-preferences.txt').write_text(text(payload.get('text',''))+'\n',encoding='utf8');result={'message':'Writing preferences saved locally.'}
                else:return self.fail(404,'Action not found.')
                self.respond(200,result)
            except(ValueError,KeyError,TypeError):self.fail(400,str(sys.exception())if isinstance(sys.exception(),ValueError)else'Check the supplied information.')
            except Exception:self.internal()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
    store=Store(args.root);server=make_server(store,args.port)
    atomic_json(store.tools/'server-status.json',{'url':f'http://127.0.0.1:{server.server_port}','pid':os.getpid(),'root':str(store.root),'started':datetime.datetime.now().astimezone().isoformat()})
    try:server.serve_forever()
    finally:server.server_close()
