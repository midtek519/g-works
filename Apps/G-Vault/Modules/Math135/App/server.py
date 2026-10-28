"""Loopback-only course grades app. Standard library; no telemetry or remote calls."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gwhiz_embed as embed
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs,unquote
import argparse,csv,datetime,io,json,mimetypes,os,secrets,threading,traceback,webbrowser
import analytics
import teacher_links
from core import Store,safe_csv,one,values,label

def make_server(store,port=0):
    token=secrets.token_urlsafe(32);static=Path(__file__).with_name('static')
    class Handler(BaseHTTPRequestHandler):
        server_version='Math135Local/1.0'
        def log_message(self,*args):pass
        def trusted(self):
            host=self.headers.get('Host','')
            valid={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if host not in valid:return False
            if embed.navigation(self):return True
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://{h}'for h in valid}:return False
            if self.headers.get('Sec-Fetch-Site')in ['cross-site','same-site']and origin not in {f'http://{h}'for h in valid}:return False
            return True
        def respond(self,status,data,content_type='application/json; charset=utf-8',disposition=None):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')if content_type.startswith('application/json')else data if isinstance(data,bytes)else str(data).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');embed.send_frame_headers(self);self.send_header('Content-Security-Policy',embed.csp("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"))
            if disposition:self.send_header('Content-Disposition',disposition)
            self.end_headers()
            try:self.wfile.write(body)
            except(BrokenPipeError,ConnectionResetError):pass
        def error(self,status,message):self.respond(status,{'error':message})
        def do_OPTIONS(self):self.error(403,'Cross-origin requests are not allowed.')
        def do_GET(self):
            if not self.trusted():return self.error(403,'Open the app at its local address.')
            if embed.serve_ui(self,static):return
            parsed=urlparse(self.path);path=unquote(parsed.path);params=parse_qs(parsed.query,keep_blank_values=True)
            try:
                if path=='/api/health':return self.respond(200,{'codeGeneration':__import__('os').environ.get('GWORKS_CODE_GENERATION',''),'app':'Math135Central','database':str(store.path),'version':1})
                if path=='/api/bootstrap':return self.respond(200,{**store.bootstrap(),'token':token})
                if path=='/api/students':return self.respond(200,store.students(params))
                if path.startswith('/api/students/'):return self.respond(200,store.student(path.rsplit('/',1)[1]))
                if path=='/api/imports':return self.respond(200,{'rows':store.history()})
                if path=='/api/policy':return self.respond(200,store.policy(one(params,'semester','Fa26')))
                if path in ['/api/reports','/api/grade-review']:
                    with store.lock,store.connect()as d:result=analytics.report(d,params)if path.endswith('reports')else analytics.grade_review(d,params)
                    return self.respond(200,result)
                if path=='/api/export':return self.export(params)
                if path.startswith('/api/'):return self.error(404,'That page was not found.')
                allowed={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/record-filters.js':'record-filters.js','/style.css':'style.css'}
                if path=='/favicon.ico':return self.respond(204,b'','image/x-icon')
                if path not in allowed:return self.error(404,'That file is not available.')
                p=static/allowed[path]
                return self.respond(200,p.read_bytes(),mimetypes.guess_type(p.name)[0]or'application/octet-stream')
            except ValueError as e:self.error(400,str(e))
            except Exception:self.internal_error()
        def do_POST(self):
            if embed.stop_request(self,store):return
            if not self.trusted():return self.error(403,'This action must come from the local app.')
            if not secrets.compare_digest(self.headers.get('X-App-Token',''),token):return self.error(403,'Reload the app before making changes.')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.error(415,'Use the local app to upload files.')
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=36_000_000:return self.error(413,'This request is too large or empty.')
                payload=json.loads(self.rfile.read(size));path=urlparse(self.path).path
                if not isinstance(payload,dict):raise ValueError('Invalid request.')
                if path=='/api/imports/preview':result=store.preview(payload)
                elif path=='/api/imports/commit':result=store.commit(payload.get('preview_id'))
                elif path=='/api/imports/undo':result=store.undo(payload.get('import_id'))
                elif path=='/api/policy':result=store.save_policy(payload)
                elif path=='/api/instructors':result=store.save_instructors(payload)
                else:return self.error(404,'That action was not found.')
                self.respond(200,result)
            except(ValueError,KeyError,TypeError):self.error(400,'Please check the selected file, semester, and required fields.' if not isinstance(sys.exception(),ValueError)else str(sys.exception()))
            except Exception:self.internal_error()
        def internal_error(self):
            logs=store.root/'logs';logs.mkdir(exist_ok=True)
            with (logs/'private-errors.txt').open('a',encoding='utf-8')as f:f.write(datetime.datetime.now().isoformat()+'\n'+traceback.format_exc()+'\n')
            self.error(500,'The action could not be completed. Details were saved in the local error log.')
        def export(self,params):
            kind=one(params,'type','letters');filename='Math'+store.course_code+'-'+kind+'.csv'
            with store.lock,store.connect()as d:
                if kind=='students':
                    where,args=store.filter_sql(params)
                    rr=[dict(r)for r in d.execute('SELECT e.name,e.ruid,e.netid,e.semester,rs.section,e.official_grade,e.course_average,e.unit,e.class,e.curric,rs.active FROM enrollments e LEFT JOIN app_roster_state rs USING(ruid,semester) '+where+' ORDER BY e.name,e.semester',args)]
                    for record in rr:record.update(teacher_links.section_names(d,record['semester'],record['section']))
                    columns=['name','ruid','netid','semester','section','lecturer','recitation','official_grade','course_average','unit','class','curric','active']
                elif kind=='grade-review':
                    rr=analytics.grade_review(d,params)['rows'];columns=['name','ruid','netid','semester','section','instructor','lecturer','recitation','official_grade','proposed_grade','course_average','base_grade','final_exam_grade','anticipated_grade','status','reason']
                else:
                    report=analytics.report(d,params)
                    if kind=='letters':rr=report['letters'];columns=['grade','count','percent']
                    elif kind=='tz':rr=report['tz_rows'];columns=['name','ruid','netid','semester','section','instructor','lecturer','recitation','email']
                    elif kind=='assessment':
                        a=report.get('assessment')
                        if not a:raise ValueError('Choose an assessment first.')
                        rr=[{'statistic':k,'value':v}for k,v in a['stats'].items()if isinstance(v,(int,float))or v is None];rr+=[{'statistic':b['label'],'value':b['count']}for b in a['bins']];columns=['statistic','value']
                    elif kind=='summary':rr=[report['summary']];columns=list(report['summary'])
                    else:raise ValueError('Choose a report to export.')
            text=io.StringIO(newline='');w=csv.writer(text);w.writerow(columns)
            for r in rr:w.writerow([safe_csv(r.get(c))for c in columns])
            return self.respond(200,('\ufeff'+text.getvalue()).encode('utf-8'),'text/csv; charset=utf-8','attachment; filename="'+filename+'"')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server

def main():
    p=argparse.ArgumentParser();p.add_argument('--database',type=Path,default=Path(__file__).resolve().parent.parent/'Math_135_Central.sqlite');p.add_argument('--port',type=int,default=0);p.add_argument('--status-file',type=Path);p.add_argument('--no-browser',action='store_true',help=argparse.SUPPRESS);args=p.parse_args()
    store=Store(args.database);server=make_server(store,args.port);url=f'http://127.0.0.1:{server.server_port}';status=args.status_file or store.root/'server-status.json'
    status.write_text(json.dumps({'url':url,'pid':os.getpid(),'database':str(store.path),'app':'Math135Central'}),encoding='utf-8')
    print('Course grades app is ready at '+url,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
