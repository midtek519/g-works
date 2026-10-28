"""Loopback HTTP interface. General AI receives only approved redacted text briefs."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,quote
from pathlib import Path
import argparse,json,secrets,mimetypes,os,threading
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gwhiz_embed as embed
from casebook import Store,save
AI_ASSETS=(Path(__file__).resolve().parents[5]/'Dependencies/TeachingApp').resolve()/'private_module_ui'
sys.path.insert(0,str(AI_ASSETS))
import local_ai

def make_server(store,port=0):
 token=secrets.token_urlsafe(32);static=Path(__file__).parent/'static';drafting=local_ai.ApprovedDrafting(store,'integrity');rationale_ai=local_ai.ApprovedRationale(store)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def headers_common(self):
   self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
   self.send_header('Content-Security-Policy',embed.csp("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"))
  def json(self,status,value):
   b=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.headers_common();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def serve_file(self,path,name=None,static_asset=False):
   size=path.stat().st_size;ext=path.suffix.lower();mime=mimetypes.guess_type(path.name)[0]or'application/octet-stream'
   inline=ext in ('.pdf','.png','.jpg','.jpeg','.webp','.mp4','.txt')
   if static_asset:inline=True
   self.send_response(200);self.headers_common();self.send_header('Content-Type',mime+('; charset=utf-8'if ext in('.html','.js','.css','.txt')else''));self.send_header('Content-Length',str(size))
   if not static_asset:self.send_header('Content-Disposition',('inline'if inline else'attachment')+('; filename*=UTF-8\'\''+quote(name,safe='') if name and ext in('.json','.zip') else '; filename="document'+ext+'"'))
   self.end_headers()
   with path.open('rb')as f:
    for block in iter(lambda:f.read(1024*1024),b''):self.wfile.write(block)
  def guard(self,write=False):
   expected='127.0.0.1:'+str(self.server.server_port)
   if self.headers.get('Host')!=expected:raise PermissionError('Use this app through its local launcher.')
   if not write and embed.navigation(self):return
   origin=self.headers.get('Origin')
   if origin and origin!='http://'+expected:raise PermissionError('Only the local app may access these records.')
   if self.headers.get('Sec-Fetch-Site')in('cross-site','same-site'):raise PermissionError('Open the local app directly.')
   if write and not secrets.compare_digest(self.headers.get('X-App-Token',''),token):raise PermissionError('Refresh the local app before saving.')
  def do_GET(self):
   try:
    attachment_parts=urlsplit(self.path).path.strip('/').split('/')
    if len(attachment_parts)==6 and attachment_parts[:2]==['api','report-attachment']:
     expected='127.0.0.1:'+str(self.server.server_port)
     if self.headers.get('Host')!=expected:raise PermissionError('Invalid local host.')
     origin=self.headers.get('Origin','')
     if origin and not (origin.startswith('chrome-extension://')and len(origin.split('/')[-1])==32):raise PermissionError('Use the form helper for attachments.')
     p=store.report_attachment(*attachment_parts[2:]);return self.serve_file(p)
    self.guard()
    if embed.serve_ui(self,static):return
    path=urlsplit(self.path).path;parts=path.strip('/').split('/')
    if path=='/local-ai.js':return self.serve_file(AI_ASSETS/'local_ai_ui.js',static_asset=True)
    if path=='/local-ai.css':return self.serve_file(AI_ASSETS/'local_ai_ui.css',static_asset=True)
    if path=='/api/local-ai/models':return self.json(200,{'models':local_ai.models()})
    if path=='/api/local-ai/connection':return self.json(200,__import__('general_ai').connection_info())
    if __import__('re').fullmatch(r'/api/local-ai/jobs/[a-f0-9]{32}',path):return self.json(200,drafting.jobs.get(parts[-1]))
    if path=='/api/local-rationale/models':return self.json(200,{'models':local_ai.models()})
    if __import__('re').fullmatch(r'/api/local-rationale/jobs/[a-f0-9]{32}',path):return self.json(200,rationale_ai.jobs.get(parts[-1]))
    if len(parts)==4 and parts[:2]==['api','cases']and parts[3]=='handoff':
     import rationale_handoff as rh
     return self.json(200,rh.resume_latest(store,parts[2]))
    if len(parts)>=6 and parts[:2]==['api','cases']and parts[3]=='handoff':
     import rationale_handoff as rh
     if len(parts)==8 and parts[5]=='image':return self.serve_file(rh.get_file(store,parts[2],parts[4],'image',parts[6],parts[7]))
     if len(parts)==7 and parts[5]=='review':return self.serve_file(rh.get_file(store,parts[2],parts[4],'review',parts[6]))
     if len(parts)==6 and parts[5]=='download':return self.serve_file(rh.get_file(store,parts[2],parts[4],'download'),'Rationale-handoff.zip')
    if path=='/api/health':return self.json(200,{'codeGeneration':__import__('os').environ.get('GWORKS_CODE_GENERATION',''),'app':'MHIntegrity','aiRouting':1,'generalAITransport':2,'signatureSettings':1,'root':str(store.root),'busy':drafting.jobs.busy() or rationale_ai.jobs.busy()})
    if path=='/api/bootstrap':return self.json(200,{**store.bootstrap(),'token':token})
    if path=='/api/cases':return self.json(200,{'cases':store.cases()})
    if path=='/api/archive':return self.json(200,store.archive())
    if path=='/api/template-review':return self.json(200,store.template_review())
    if len(parts)==3 and parts[:2]==['api','archive']:return self.serve_file(store.archive_file(parts[2]))
    if len(parts)==3 and parts[:2]==['api','cases']:return self.json(200,{'case':store.decorate(store.case(parts[2]))})
    if len(parts)==4 and parts[:2]==['api','cases']and parts[3]=='contacts':return self.json(200,store.contact_review(parts[2]))
    if len(parts)==4 and parts[:2]==['api','cases']and parts[3]=='rationales':return self.json(200,{'rationales':store.saved_rationales(parts[2],parse_qs(urlsplit(self.path).query).get('party_id',[''])[0])})
    if len(parts)==5 and parts[:2]==['api','cases']and parts[3]=='files':
     p,name=store.file_path(parts[2],parts[4]);return self.serve_file(p,name)
    if len(parts)==6 and parts[:2]==['api','cases']and parts[3]=='pdfs':return self.serve_file(store.pdf(parts[2],parts[4],parts[5]))
    if len(parts)==6 and parts[:2]==['api','cases']and parts[3]=='reports':
     p=store.report_file(parts[2],parts[4],parts[5]);return self.serve_file(p,store.report_download_name(parts[2],parts[4]))
    assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
    if path in assets:return self.serve_file(static/assets[path],static_asset=True)
    return self.json(404,{'error':'Page not found.'})
   except PermissionError as exc:self.json(403,{'error':str(exc)})
   except (ValueError,FileNotFoundError):self.json(404,{'error':'The local item was not found.'})
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception:self.json(500,{'error':'The local item could not be opened. Your saved records are unchanged.'})
  def do_POST(self):
   if embed.stop_request(self,store,busy=lambda:drafting.jobs.busy() or rationale_ai.jobs.busy()):return
   try:
    self.guard(True);parsed=urlsplit(self.path);parts=parsed.path.strip('/').split('/');query=parse_qs(parsed.query)
    try:length=int(self.headers.get('Content-Length','0'))
    except ValueError:raise ValueError('Invalid request size.')
    if not 0<length<=50*1024*1024:raise ValueError('Choose a nonempty request up to 50 MB.')
    raw=self.rfile.read(length)
    if len(raw)!=length:raise ValueError('The upload was incomplete.')
    if len(parts)==4 and parts[:2]==['api','cases']and parts[3]=='files':result=store.upload(parts[2],query.get('name',[''])[0],raw,query.get('party_id',[''])[0],query.get('kind',['evidence'])[0])
    else:
     if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('Use the local app form to save this item.')
     payload=json.loads(raw)
     if not isinstance(payload,dict):raise ValueError('Check the request fields.')
     if parts==['api','local-ai','brief']:result=drafting.brief(payload)
     elif parts==['api','local-rationale','brief']:result=rationale_ai.brief(payload)
     elif parts==['api','local-rationale','jobs']:result=rationale_ai.start(payload)
     elif __import__('re').fullmatch(r'/api/local-rationale/jobs/[a-f0-9]{32}/cancel',parsed.path):result=rationale_ai.jobs.cancel(parts[-2])
     elif parts==['api','local-ai','jobs']:result=drafting.start(payload)
     elif parts==['api','local-ai','apply']:result=drafting.apply(payload)
     elif __import__('re').fullmatch(r'/api/local-ai/jobs/[a-f0-9]{32}/cancel',parsed.path):result=drafting.jobs.cancel(parts[-2])
     elif parts==['api','cases']:result=store.new(payload)
     elif parts==['api','settings']:result=store.save_settings(payload)
     elif parts==['api','templates']:result=store.save_template(payload)
     elif len(parts)>=3 and parts[:2]==['api','cases']:
      identity=parts[2]
      if len(parts)==3:result=store.update(identity,payload)
      elif len(parts)==4 and parts[3]=='parties':result=store.party(identity,payload)
      elif len(parts)==5 and parts[3]=='parties':result=store.party(identity,payload,parts[4])
      elif len(parts)==4 and parts[3]=='steps':result=store.step(identity,payload)
      elif len(parts)==4 and parts[3]=='meeting-response':result=store.meeting_response(identity,payload)
      elif len(parts)==4 and parts[3]=='events':result=store.event(identity,payload)
      elif len(parts)==4 and parts[3]=='meetings':result=store.meeting(identity,payload)
      elif len(parts)==4 and parts[3]=='intake':result=store.report_intake(identity,payload.get('file_id',''),payload.get('ruid'),payload.get('apply')is True,payload.get('overwrite')is True)
      elif len(parts)==4 and parts[3]=='contacts':result=store.save_contacts(identity,payload)
      elif len(parts)==5 and parts[3]=='files':result=store.manage_evidence(identity,parts[4],payload)
      elif len(parts)==4 and parts[3]=='handoff':
       import rationale_handoff as rh
       result=rh.prepare(store,identity,payload)
      elif len(parts)==6 and parts[3]=='handoff':
       import rationale_handoff as rh
       if parts[5]=='review':result=rh.review(store,identity,parts[4],payload)
       elif parts[5]=='export':result=rh.export(store,identity,parts[4],payload)
       else:raise ValueError('Choose a handoff action.')
      elif len(parts)==4 and parts[3]=='extract':result=store.extract(identity,payload)
      elif len(parts)==4 and parts[3]=='communications':result=store.communication(identity,payload)
      elif len(parts)==5 and parts[3]=='communications':result=store.communication(identity,payload,parts[4])
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='abandon':result=store.abandon_draft(identity,parts[4])
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='delete':result=store.delete_letter(identity,parts[4],payload)
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='email-preview':result=store.email_preview(identity,parts[4])
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='email-open':result=store.open_email(identity,parts[4],payload)
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='email-sent':result=store.confirm_email_sent(identity,parts[4],payload)
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='build':result=store.build(identity,parts[4],payload)
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='report':result=store.export_report(identity,parts[4],payload)
      elif len(parts)==6 and parts[3]=='communications'and parts[5]=='brief':result=store.brief(identity,parts[4],payload)
      else:return self.json(404,{'error':'Action not found.'})
     else:return self.json(404,{'error':'Action not found.'})
    self.json(200,result)
   except PermissionError as exc:self.json(403,{'error':str(exc)})
   except ValueError as exc:
    message=str(exc)
    # Our validation messages contain guidance; never expose parser traces or paths.
    if len(message)>220 or any(c in message for c in ('\\','/','\n')):message='Check the request fields and local file, then retry.'
    self.json(400,{'error':message})
   except (KeyError,StopIteration):self.json(400,{'error':'Check the request: required details may be missing.'})
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception:self.json(500,{'error':'The action could not finish. Saved records remain available; check the fields and retry.'})
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;store.local_url='http://127.0.0.1:'+str(server.server_port);return server

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path);parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
 store=Store(args.root);server=make_server(store,args.port);status={'pid':os.getpid(),'url':'http://127.0.0.1:'+str(server.server_port),'root':str(store.root)}
 save(store.tools/'server-status.json',status)
 try:server.serve_forever()
 finally:server.server_close()
