"""Loopback-only G-Whiz interface."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs,quote
import argparse,json,mimetypes,os,secrets,sys,threading
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent/'private_module_ui'))
import local_ai_config,general_ai,chatgpt_account
from core import Desk,save
from universal import Universal
from question_import import ImportWorkspace
from question_portable import export_questions,export_file
from authoring import CourseLibrary,preview_draft
from syllabus_builder import SyllabusBuilder
from support_documents import SupportDocuments
from folder_picker import browse_folder
from toolchain import open_folder
import course_workspaces,instructor_profile

def make_server(desk,port=0):
 previous_token=os.environ.get('GSPOT_SESSION_TOKEN','')
 token=previous_token if __import__('re').fullmatch(r'[A-Za-z0-9_-]{32,128}',previous_token) else secrets.token_urlsafe(32)
 static=Path(__file__).parent/'static';universal=Universal(desk) if desk.materials_enabled else None;course_library=CourseLibrary(desk,universal) if universal else None;syllabus=SyllabusBuilder(desk) if universal else None;support=SupportDocuments(desk) if universal else None
 imports=ImportWorkspace(desk,universal) if universal else None
 ai_path=local_ai_config.CONFIG_PATH
 account=chatgpt_account.Account(desk.root)
 private=None
 if desk.edition.get('edition') in ('authoring','personal','personal135'):
  from private_modules import PrivateModules
  private=PrivateModules(desk,lambda:'http://127.0.0.1:'+str(server.server_port))
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def guard(self,write=False):
   host='127.0.0.1:'+str(self.server.server_port)
   if self.headers.get('Host')!=host:raise PermissionError('Open the compiler through its local launcher.')
   if self.headers.get('Origin')and self.headers['Origin']!='http://'+host:raise PermissionError('Only the local app can access these files.')
   if self.headers.get('Sec-Fetch-Site')in('cross-site','same-site'):raise PermissionError('Open the local app directly.')
   if write and not secrets.compare_digest(self.headers.get('X-App-Token',''),token):raise PermissionError('Refresh the app before saving.')
  def headers_common(self):
   private_frames=private is not None and private.enabled
   self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'self'; frame-src 'self' http://127.0.0.1:*; frame-ancestors 'self'; base-uri 'none'" if private_frames else "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'")
  def reply(self,code,value):
   data=json.dumps(value,ensure_ascii=False).encode();self.send_response(code);self.headers_common();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def file(self,p,name=None,attachment=False):
   p=Path(p)
   if not p.is_file():raise ValueError('The preview is not available yet.')
   self.send_response(200);self.headers_common();mime=mimetypes.guess_type(p.name)[0]or'application/octet-stream';self.send_header('Content-Type',mime+('; charset=utf-8'if p.suffix in('.js','.css','.html','.txt')else''));self.send_header('Content-Length',str(p.stat().st_size))
   if name:self.send_header('Content-Disposition',("attachment" if attachment else "inline")+"; filename*=UTF-8''"+quote(name,safe=''))
   self.end_headers()
   with p.open('rb')as f:
    for block in iter(lambda:f.read(1024*1024),b''):self.wfile.write(block)
  def do_GET(self):
   try:
    self.guard();path=urlsplit(self.path);parts=path.path.strip('/').split('/');q={k:v[0]for k,v in parse_qs(path.query).items()}
    if path.path=='/api/vault-workspaces':
     if private is None:raise PermissionError('Course databases belong to G-Vault.')
     return self.reply(200,private.workspaces.inventory())
    if path.path=='/api/private-modules':return self.reply(200,{'modules':private.inventory() if private else []})
    if path.path=='/api/health':return self.reply(200,{'app':'GWhiz','root':str(desk.root),'selectedHandoutVersions':True,'active':desk.active,'busy':bool(desk.active or imports and imports.jobs),'materialsEnabled':desk.materials_enabled})
    if path.path=='/api/bootstrap':return self.reply(200,{'version':'2.0.0','materialsEnabled':desk.materials_enabled,'edition':desk.edition,'branding':desk.branding,'token':token,'courses':desk.courses(),'history':desk.history(),'active':desk.active,'universal_available':bool(universal and universal.available()),'private_modules':private.inventory() if private else []})
    if path.path=='/edition.css':return self.file(static/('instructor.css' if desk.branding['theme']=='rutgers' else 'edition-default.css'))
    if path.path=='/g-whiz.svg':return self.file(static/('g-whiz-instructor.svg' if desk.branding['theme']=='rutgers' else 'g-whiz.svg'))
    if path.path=='/privacy/ferpa.html':
     if private is None:return self.reply(404,{'error':'That page is unavailable.'})
     return self.file(Path(__file__).parent/'private_module_ui/ferpa.html')
    if not desk.materials_enabled and (path.path.startswith(('/api/syllabus','/api/support','/api/universal','/api/course-library','/api/catalog','/api/library','/api/builds'))):raise PermissionError('Open G-Whiz for teaching materials.')
    if path.path=='/api/syllabus/list':return self.reply(200,syllabus.list_drafts(q.get('course','135'),q.get('semester','fa26')))
    if path.path=='/api/syllabus/model':return self.reply(200,syllabus.model(q.get('course','135'),q.get('semester','fa26'),q.get('draft_id')))
    if path.path=='/api/support/source':return self.reply(200,support.model(q.get('course','135'),q.get('semester','fa26'),q.get('key','')))
    if path.path=='/api/temp-files':return self.reply(200,desk.temp_files())
    if path.path=='/api/local-ai/settings':
     return self.reply(200,local_ai_config.settings(ai_path))
    if path.path=='/api/general-ai/settings':
     return self.reply(200,{'configuration':general_ai.settings(desk.root),'account':account.status()})
    if path.path=='/api/general-ai/account':
     return self.reply(200,account.status())
    if path.path=='/api/system-check':return self.reply(200,desk.system_check())
    if path.path=='/api/configuration':return self.reply(200,desk.configuration())
    if path.path=='/api/instructor-profile':return self.reply(200,instructor_profile.read(desk.root))
    if path.path=='/api/universal/import':
     try:ai=general_ai.connection_info(desk.root)
     except ValueError:ai={'label':'Configure General AI in Settings.'}
     return self.reply(200,{'imports':imports.recent(),'ai':ai})
    if len(parts)==4 and parts[:3]==['api','universal','import']:return self.reply(200,imports.model(parts[3]))
    if len(parts)==6 and parts[:3]==['api','universal','import']:
     if parts[4]=='page':return self.file(imports.page(parts[3],parts[5]))
     if parts[4]=='file':
      session=imports.read(parts[3]);record=next((f for f in session['files'] if f['id']==parts[5]),None)
      if not record:raise ValueError('Choose an imported source file.')
      return self.file(imports.folder(parts[3])/'files'/record['disk_name'],record['name'])
    if len(parts)==4 and parts[:3]==['api','universal','assets']:return self.file(imports.asset(parts[3],q.get('import_session')))
    if len(parts)==4 and parts[:3]==['api','universal','export']:return self.file(export_file(desk.root,parts[3]),'questions.tex',attachment=True)
    if path.path=='/api/universal':return self.reply(200,universal.catalog())
    if len(parts)==4 and parts[:3]==['api','universal','assignments']:return self.reply(200,universal.assignment(parts[3]))
    if path.path=='/api/catalog':return self.reply(200,desk.catalog(q.get('course','135'),q.get('semester')))
    if path.path=='/api/course-library':return self.reply(200,course_library.catalog(q.get('course','135'),q.get('semester')))
    if len(parts)==5 and parts[:2]==['api','course-library']and parts[4]=='pdf':
     p=course_library.pdf(parts[2],parts[3]);return self.file(p,p.name)
    if len(parts)==5 and parts[:2]==['api','course-library']and parts[4]=='info':return self.reply(200,course_library.info(parts[2],parts[3]))
    if len(parts)==6 and parts[:2]==['api','course-library']and parts[4]=='page':return self.file(course_library.page(parts[2],parts[3],parts[5]))
    if path.path=='/api/library':return self.reply(200,{'banks':desk.banks(q.get('course','135'))})
    if path.path=='/api/builds':return self.reply(200,{'builds':desk.history(),'active':desk.active})
    if parts[:2]==['api','builds']:
     if len(parts)==3:return self.reply(200,desk.batch(parts[2]))
     if len(parts)==5 and parts[4]in('pdf','log'):
      b=desk.batch(parts[2]);i=int(parts[3]);return self.file(desk.artifact(parts[2],i,parts[4]),b['jobs'][i]['name']+'.pdf'if parts[4]=='pdf'else'Compile-log.txt')
     if len(parts)==6 and parts[4]=='page':return self.file(desk.artifact(parts[2],parts[3],'image',parts[5]))
    assets={'/vault-workspaces.js':'vault-workspaces.js','/':'index.html','/app.js':'app.js','/style.css':'style.css','/preview.html':'preview.html','/preview.js':'preview.js','/g-whiz.svg':'g-whiz.svg','/syllabus.js':'syllabus.js','/syllabus.css':'syllabus.css','/pretty.js':'pretty.js','/pretty.css':'pretty.css','/bank.js':'bank.js','/bank.css':'bank.css','/workflow.js':'workflow.js'}
    if path.path in assets:return self.file(static/assets[path.path])
    if path.path.startswith('/vendor/katex/'):
     vendor=(static/'vendor/katex').resolve();asset=(static/path.path.lstrip('/')).resolve()
     if not asset.is_relative_to(vendor) or asset.suffix not in ('.js','.css','.woff2'):raise PermissionError('Unavailable math asset.')
     return self.file(asset)
    return self.reply(404,{'error':'That page is unavailable.'})
   except PermissionError as e:self.reply(403,{'error':str(e)})
   except (ValueError,KeyError,IndexError,FileNotFoundError)as e:self.reply(400,{'error':str(e)[:500]})
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception as e:self.reply(500,{'error':'The local action could not finish. Your source files and published PDFs are unchanged.'})
  def do_POST(self):
   try:
    self.guard(True);request_path=urlsplit(self.path).path;length=int(self.headers.get('Content-Length','0'));maximum=64*1024*1024 if request_path in ('/api/universal/import/file','/api/universal/import/edit') else 2*1024*1024
    if not 0<length<=maximum:raise ValueError('The request is too large.')
    if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('Use the app controls.')
    data=json.loads(self.rfile.read(length));path=urlsplit(self.path).path;parts=path.strip('/').split('/')
    if not isinstance(data,dict):raise ValueError('Check the form fields.')
    if path=='/api/installer-stop':
     with desk.lock:
      if desk.active or account.pending or imports and imports.jobs:raise ValueError('Finish compilation, import extraction and account sign-in before updating.')
      if private:private.stop_idle()
      self.reply(200,{'stopped':True});threading.Thread(target=server.shutdown,daemon=True).start();return
    if path=='/api/vault-workspaces':
     if private is None:raise PermissionError('Course databases belong to G-Vault.')
     return self.reply(200,private.workspaces.update(data))
    if path=='/api/private-modules/open':
     if private is None:raise PermissionError('This module belongs to G-Vault.')
     return self.reply(200,private.open(data.get('module')))
    if not desk.materials_enabled and path.startswith(('/api/syllabus','/api/support','/api/universal','/api/compile','/api/questions','/api/documents','/api/builds','/api/output-folders')):raise PermissionError('Open G-Whiz for teaching materials.')
    code=data.get('course','135')
    if path=='/api/output-folders':
     scope=data.get('scope');kinds=list(desk.material_defaults(code))
     if scope=='assignment':kinds=[k for k in kinds if k.lower()==str(data.get('kind','')).lower() and k.lower() in ('exam','final exam','final','quiz','worksheet','groupwork')]
     elif scope=='handouts':kinds=[k for k in kinds if k.lower() in ('exam','final exam','final','quiz','worksheet','groupwork')]
     elif scope=='manual':kinds=[k for k in kinds if k.lower()=='manual']
     elif scope=='syllabus':kinds=[k for k in kinds if k=='Syllabus & Schedule']
     elif scope=='support':kinds=[k for k in kinds if k.lower() not in ('exam','final exam','final','quiz','worksheet','groupwork','manual','assessment manual','syllabus & schedule')]
     else:raise ValueError('Choose a builder to open its output folder.')
     folders={}
     for kind in kinds:
      folder=desk.publish_folder(code,data['semester'],kind,number=data.get('number',''),mode=data.get('mode','student'),version=data.get('version','A'))
      key=str(folder)
      if key not in folders:folders[key]={'path':key,'kinds':[],'exists':folder.is_dir()}
      folders[key]['kinds'].append(kind)
     chosen=data.get('open_kind')
     if chosen:
      if chosen not in kinds:raise ValueError('Choose a configured output folder.')
      folder=next(f for f in folders.values() if chosen in f['kinds'])
      if not folder['exists']:raise ValueError('This output folder does not exist yet. Publish a document first.')
      open_folder(folder['path'])
     result={'folders':list(folders.values())}
    elif path=='/api/support/save':result=support.save(data)
    elif path=='/api/support/preview':result=support.preview(data)
    elif path=='/api/syllabus/draft':result=syllabus.save_draft(data)
    elif path=='/api/syllabus/defaults':result=syllabus.save_defaults(data)
    elif path=='/api/syllabus/lookup':result=syllabus.lookup(data)
    elif path=='/api/syllabus/calendar':
     _,_,draft=syllabus.validate_draft(data);result=syllabus.calendar(draft)
    elif path=='/api/syllabus/compile':result=syllabus.compile(data)
    elif path=='/api/temp-files/clear':result=desk.clear_temp()
    elif path=='/api/local-ai/settings':
     result=local_ai_config.save(data,path=ai_path)
    elif path=='/api/local-ai/check':
     result=local_ai_config.check(data)
    elif path.startswith('/api/general-ai/'):
     command=path.removeprefix('/api/general-ai/')
     if command=='settings':result={'configuration':general_ai.save(data,desk.root)}
     elif command=='account/start' and set(data)<= {'profile'}:result=account.start(data.get('profile',''))
     elif command=='account/cancel' and not data:result=account.cancel()
     elif command=='account/select' and set(data)=={'profile'}:result=account.select(data['profile'])
     elif command=='account/signout' and not data:result=account.logout()
     elif command=='account/models' and not data:result=account.models()
     elif command=='account/welcome' and not data:result=account.acknowledge()
     elif command=='account/usage' and not data:
      import webbrowser
      result={'opened':bool(webbrowser.open('https://chatgpt.com/settings/usage'))}
     else:raise ValueError('Choose an AI settings action.')
    elif path=='/api/configuration/browse':result=browse_folder(desk,data)
    elif path=='/api/configuration':result=desk.save_configuration(data)
    elif path=='/api/courses/create':result=course_workspaces.create(desk,data)
    elif path=='/api/instructor-profile':result=instructor_profile.write(desk.root,data)
    elif path=='/api/universal/export':result=export_questions(universal,data)
    elif path=='/api/universal/questions':result=universal.save_question(data)
    elif path=='/api/universal/questions/save':result=universal.save_questions(data)
    elif path=='/api/universal/import/create':result=imports.create(data)
    elif path=='/api/universal/import/file':result=imports.upload(data)
    elif path=='/api/universal/import/extract':result=imports.start(data)
    elif path=='/api/universal/import/edit':result=imports.edit(data)
    elif path=='/api/universal/import/crop':result=imports.crop(data)
    elif path=='/api/universal/import/stop':result=imports.stop(data.get('id'))
    elif path=='/api/universal/import/save':result=imports.commit(data)
    elif path=='/api/universal/import/preview':result=imports.preview(data)
    elif path=='/api/universal/bank':result=universal.manage_questions(data)
    elif path=='/api/universal/assignments':result=universal.save_assignment(data)
    elif path=='/api/universal/assignments/delete':result=universal.delete_assignment(data)
    elif path=='/api/universal/compile':result=universal.compile(data)
    elif path=='/api/universal/preview':result=universal.preview(data)
    elif path=='/api/universal/preview-draft':result=preview_draft(universal,data)
    elif path=='/api/universal/taxonomy':result=universal.taxonomy(data)
    elif path=='/api/universal/manual-order':result=universal.reorder_manual_questions(data)
    elif path=='/api/universal/manuals':result=universal.manuals(data)
    elif path=='/api/compile':result=desk.start(code,data['semester'],data['keys'],data.get('mode','all'),data.get('version','all'))
    elif path=='/api/questions':result=desk.add_question(code,data)
    elif path=='/api/questions/preview':result=desk.preview_question(code,data)
    elif path=='/api/documents':result=desk.create_document(code,data)
    elif len(parts)==4 and parts[:2]==['api','builds']and parts[3]=='publish':result=desk.publish(parts[2])
    else:return self.reply(404,{'error':'That action is unavailable.'})
    return self.reply(200,result)
   except PermissionError as e:self.reply(403,{'error':str(e)})
   except (ValueError,KeyError,IndexError,FileNotFoundError)as e:self.reply(400,{'error':str(e)[:500]})
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception:self.reply(500,{'error':'The action could not finish. Check the fields and retry.'})
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(os.environ.get('GWORKS_APP_ROOT',str(Path(__file__).resolve().parent.parent))));p.add_argument('--repo');p.add_argument('--port',type=int,default=0);args=p.parse_args();desk=Desk(args.root,args.repo);server=make_server(desk,args.port);save(desk.temp/'server-status.json',{'app':'GWhiz','pid':os.getpid(),'root':str(desk.root),'url':'http://127.0.0.1:'+str(server.server_port)})
 try:server.serve_forever()
 finally:server.server_close()
