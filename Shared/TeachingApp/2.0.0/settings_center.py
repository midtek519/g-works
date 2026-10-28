"""One loopback settings window for every installed G-Works app.

Only fixed settings documents and explicit AI/account actions are exposed.
No student database, arbitrary file browser endpoint, or generic command bridge.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import argparse,copy,hashlib,json,mimetypes,os,re,secrets,subprocess,sys,threading,time,urllib.request,webbrowser
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'private_module_ui'));sys.path.insert(0,str(HERE/'Desktop'))
import appearance,general_ai,local_ai_config,chatgpt_account,shared_signature
from runtime_paths import registered_suite as suite_root,canonical_settings_root as settings_root
# Keep the existing settings IDs while folders and public names evolve.
from app_catalog import catalog
APP_SPECS,SUITE_TITLES=catalog()
APPS={key:value['name'] for key,value in APP_SPECS.items()}
SUITE_APPS={suite:tuple(key for key,value in APP_SPECS.items() if value['suite']==suite) for suite in ('professional','personal')}

PAGES=('app','appearance','ai','storage')
SETTINGS_UI_VERSION=4
SECRET=re.compile(r'password|secret|credential|access_token|refresh_token|api_key',re.I)


FOLDER_KEYS=frozenset(('mh_git','library','current_publications','publication_metadata'))
FILE_KEYS=frozenset(('signature_file','grade_database','pdflatex','renderer','integrity_catalog','latexmk','pdftoppm','art_catalog'))
def setting_kind(path,value):
 if not isinstance(path,list) or not path or any(not isinstance(k,str) for k in path):return None
 if 'publish_patterns' in path:return None
 key=path[-1].lower()
 if key in FILE_KEYS:return 'file'
 if key in FOLDER_KEYS or any(re.search(r'(?:^|_)(?:folders?|directories|directory|dirs?|root|bin)$',k,re.I) for k in path):return 'folder'
 if isinstance(value,str) and (re.match(r'^(?:[A-Za-z]:[\\/]|\\\\|/)',value) or key.endswith('_path')):
  return 'file' if Path(value).suffix.lower() in ('.exe','.py','.png','.jpg','.jpeg','.json','.csv','.tsv','.sqlite','.sqlite3','.db','.pdf','.tex','.yaml','.yml') else 'folder'
 return None

def path_fields(value,prefix=None):
 prefix=prefix or [];result=[]
 if isinstance(value,dict):
  for key,item in value.items():result.extend(path_fields(item,prefix+[key]))
 elif isinstance(value,(str,list)):
  kind=setting_kind(prefix,value)
  if kind:result.append({'path':prefix,'kind':kind})
 return result

def pick_setting(settings,webview,app,document,path,current=None):
 if not isinstance(path,list) or not 1<=len(path)<=12 or any(not isinstance(k,str) or len(k)>100 or SECRET.search(k) for k in path):raise ValueError('Choose a displayed path setting.')
 config=settings.configuration(app);doc=next((d for d in config['documents'] if d['id']==document),None)
 if not doc:raise ValueError('Choose a displayed settings section.')
 value=doc['value']
 for key in path:
  if not isinstance(value,dict) or key not in value:raise ValueError('Choose a displayed setting.')
  value=value[key]
 kind=setting_kind(path,value)
 if not kind:raise ValueError('That setting is not a folder or file.')
 if current is not None and (not isinstance(current,str) or len(current)>2000 or '\x00' in current):raise ValueError('Use a valid path.')
 value=current if current is not None else value if isinstance(value,str) else ''
 initial=Path(value) if value else settings.app(app);suffix=()
 if kind=='folder':
  for i,part in enumerate(initial.parts):
   if re.search(r'\[(?:course|semester|term|year)\]|\{(?:course|semester|term|year)\}',part,re.I):suffix=initial.parts[i:];initial=Path(*initial.parts[:i]);break
 if not initial.is_absolute():initial=settings.app(app)/initial
 if kind=='file':initial=initial.parent
 for _ in range(30):
  if initial.is_dir() or initial==initial.parent:break
  initial=initial.parent
 kwargs={'directory':str(initial),'allow_multiple':False}
 if kind=='file' and path[-1]=='signature_file':kwargs['file_types']=('PNG images (*.png)',)
 result=settings.window.create_file_dialog(webview.FOLDER_DIALOG if kind=='folder' else webview.OPEN_DIALOG,**kwargs)
 if not result:return None
 selected=result if isinstance(result,str) else result[0]
 return str(Path(selected).joinpath(*suffix)) if suffix else str(selected)

def picker_api(settings,webview):
 # Keep settings/account/window objects out of the exposed JavaScript object.
 class Api:
  def browse_setting(self,app,document,path,current=None):return pick_setting(settings,webview,app,document,path,current)
  def browse_signature(self):return pick_setting(settings,webview,'spot','recommendations',['signature_file'])
 return Api()


def editable_settings(ident,key,value):
 """Expose new default folder rules without changing the stored settings on read."""
 value=copy.deepcopy(value)
 if ident=='whiz' and key=='app' and isinstance(value.get('publish_patterns'),dict):
  for patterns in value['publish_patterns'].values():
   if isinstance(patterns,dict):patterns.setdefault('Final Exam',str(Path('[root]')/'[semester]'))
 return value


def installed_app(path,ident):
 entry=APP_SPECS.get(ident,{}).get('entry')
 return (Path(path)/entry).is_file() if entry else (Path(path)/'App').is_dir()


def center_directory(root):
 # A previous UI can retain unsaved edits. New entry points must not reuse its
 # incompatible context protocol or terminate its process to perform an update.
 return settings_root(root)/'Shared/SettingsCenter'/('v'+str(SETTINGS_UI_VERSION))

def app_directory(root,ident):
 if ident not in APP_SPECS:raise ValueError('Choose an installed app.')
 spec=APP_SPECS[ident]
 base=Path(spec['root']) if spec['suite']=='personal' else settings_root(root)
 return base/'Apps'/spec['folder']


def install_root(app_root):
 for p in Path(app_root).resolve().parents:
  if suite_root(p):return settings_root(p)
 raise ValueError('Open Settings from an installed G-Works app.')

def open_center(app_root,selected=None,page='app'):
 root=install_root(app_root);selected=selected or next((k for k,v in APPS.items() if v==Path(app_root).name),'whiz')
 if selected not in APPS:raise ValueError('Choose a G-Works app.')
 if page not in PAGES:raise ValueError('Choose a settings page.')
 status=center_directory(root)/'status.json';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 try:
  saved=json.loads(status.read_text('utf-8'));origin=saved['url']
  if not re.fullmatch(r'http://127\.0\.0\.1:\d+',origin):raise ValueError('Invalid local settings address.')
  with opener.open(origin+'/api/bootstrap',timeout=2) as r:info=json.load(r)
  if info.get('service')!='GWorksSettings' or info.get('uiVersion')!=SETTINGS_UI_VERSION or Path(info.get('root','')).resolve()!=root:raise ValueError('Settings owner mismatch.')
  request=urllib.request.Request(origin+'/api/show',data=json.dumps({'app':selected,'page':page}).encode(),headers={'Content-Type':'application/json','X-App-Token':info['token']})
  with opener.open(request,timeout=3):pass
  return True
 except (OSError,ValueError,KeyError):pass
 candidates=[Path(app_root)/'Dependencies/python/pythonw.exe',*[app_directory(root,key)/'Dependencies/python/pythonw.exe' for key in APPS]]
 python=next((p for p in candidates if p.is_file()),None)
 if not python:raise ValueError('Repair the shared desktop runtime in G-Works Setup.')
 folder=center_directory(root);folder.mkdir(parents=True,exist_ok=True)
 with (folder/'startup.log').open('ab') as log:
  subprocess.Popen([str(python),'-I','-B',str(HERE/'settings_center.py'),'--root',str(root),'--app',selected,'--page',page],env={**os.environ,'GWORKS_APP_ROOT':str(Path(app_root))},stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 return True

class Settings:
 def __init__(self,root,selected=None,page='app'):
  selected=selected or 'whiz'
  if selected not in APPS or page not in PAGES:raise ValueError('Choose an app and settings page.')
  self.root=settings_root(root);self.selected=selected;self.selected_page=page;self.window=None;self.pending_app=None;self.pending_page=None;self.show_revision=0;self.mutex=threading.RLock()
  self.account=chatgpt_account.Account(app_directory(self.root,selected if not APP_SPECS[selected].get('entry') else 'whiz'))
 def context(self):
  suite='personal' if SUITE_APPS['personal'] else 'professional'
  return {'suite':suite,'title':SUITE_TITLES.get(suite,'G-Works')+' Settings','aiShared':True,'apps':[{'id':key,'name':APPS[key],'installed':installed_app(app_directory(self.root,key),key),'externalSettings':bool(APP_SPECS[key].get('external_settings'))} for key in APPS]}
 def app(self,ident):
  path=app_directory(self.root,ident)
  if not installed_app(path,ident):raise ValueError('That app is not installed.')
  return path
 def documents(self,ident):
  if APP_SPECS[ident].get('external_settings'):self.app(ident);return {}
  root=self.app(ident);items={'app':('General',root/'Data/settings.json')}
  if APP_SPECS[ident].get('folder_settings'):items['app']=('Folders',root/'Data/settings.json')
  if ident=='spot':
   for key,label,path in [('recommendations','Recommendations','Recommendations/tools/settings.json'),('integrity','Integrity','Integrity/tools/settings.json'),('grades','Grades','Math135/settings.json')]:
    p=root/'Data/PrivateModules'/path
    if p.is_file():items[key]=(label,p)
  return items
 def safe(self,value):
  if isinstance(value,dict):return {k:self.safe(v) for k,v in value.items() if not SECRET.search(k)}
  if isinstance(value,list):return [self.safe(v) for v in value]
  return value
 def configuration(self,ident):
  if APP_SPECS[ident].get('external_settings'):self.app(ident);return {'app':ident,'name':APPS[ident],'externalSettings':True,'appearance':None,'documents':[]}
  root=self.app(ident);docs=[]
  for key,(name,path) in self.documents(ident).items():
   raw=path.read_bytes() if path.is_file() else b'{}'
   if len(raw)>250000:continue
   value=editable_settings(ident,key,json.loads(raw.decode('utf-8-sig')))
   if ident=='spot' and key in ('recommendations','integrity'):value=shared_signature.apply(value,root)
   docs.append({'id':key,'name':name,'value':self.safe(value),'paths':path_fields(self.safe(value)),'hash':hashlib.sha256(raw).hexdigest()})
  return {'app':ident,'name':APPS[ident],'appearance':appearance.info(appearance.load(root),APPS[ident]),'documents':docs}
 def external_settings(self,ident):
  spec=APP_SPECS.get(ident,{})
  if not spec.get('external_settings') or not spec.get('entry'):raise ValueError('Choose an app with its own settings window.')
  root=self.app(ident);executable=(root/spec['entry']).resolve()
  if not executable.is_relative_to(root.resolve()):raise ValueError('Invalid app entry.')
  subprocess.Popen([str(executable),'--settings'],cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  return {'opened':True,'app':ident}

 def save_document(self,payload):
  ident=payload.get('app');documents=self.documents(ident);key=payload.get('document')
  if key not in documents:raise ValueError('Choose an existing settings section.')
  path=documents[key][1];raw=path.read_bytes() if path.is_file() else b'{}';old=editable_settings(ident,key,json.loads(raw.decode('utf-8-sig')));new=payload.get('value')
  if ident=='spot' and key in ('recommendations','integrity'):old=shared_signature.apply(old,self.app('spot'))
  if payload.get('hash')!=hashlib.sha256(raw).hexdigest():raise ValueError('Settings changed in another window. Reload this section before saving.')
  if not isinstance(new,dict) or len(json.dumps(new))>250000 or set(new)-set(self.safe(old)):raise ValueError('Use the displayed settings fields.')
  def merge(prior,value):
   if not isinstance(prior,dict):return value
   if not isinstance(value,dict):raise ValueError('Keep the settings structure.')
   result=copy.deepcopy(prior)
   for k,v in value.items():
    if k not in prior or SECRET.search(k):raise ValueError('That field is not editable here.')
    if type(v) is not type(prior[k]) and prior[k] is not None:raise ValueError('Use the expected field type.')
    result[k]=merge(prior[k],v)
   return result
  merged=merge(old,new)
  if APP_SPECS[ident].get('folder_settings') and key=='app' and (not isinstance(merged.get('media_root'),str) or not Path(merged['media_root']).is_absolute()):raise ValueError('Choose an absolute media folder.')
  if ident=='spot' and key in ('recommendations','integrity') and merged.get('signature_file')!=shared_signature.current(self.app('spot')):shared_signature.save(merged['signature_file'],self.app('spot'))
  path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
  try:temp.write_text(json.dumps(merged,indent=2,ensure_ascii=False)+'\n','utf-8');os.replace(temp,path)
  finally:temp.unlink(missing_ok=True)
  return self.configuration(ident)
 def scope_storage(self,action,data=None):
  routes={'options':'cleanup-options','preview':'cleanup-preview','execute':'cleanup'}
  if action not in routes:raise ValueError('Choose a scan storage action.')
  root=self.app('scope');opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  try:
   status=json.loads((root/'Temp/server-status.json').read_text('utf-8'));origin=status['url']
   if not re.fullmatch(r'http://127\.0\.0\.1:\d+',origin):raise ValueError('Invalid local G-Scope address.')
   with opener.open(origin+'/api/health',timeout=2) as r:health=json.load(r)
   if Path(health.get('root','')).resolve()!=root:raise ValueError('G-Scope owner mismatch.')
   with opener.open(origin+'/api/bootstrap',timeout=3) as r:token=json.load(r)['token']
   allowed={'projectIds','previewHash','confirmed'}
   if data is not None and (not isinstance(data,dict) or set(data)-allowed):raise ValueError('Use the displayed storage controls.')
   request=urllib.request.Request(origin+'/api/scans/'+routes[action],data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-App-Token':token,'Origin':origin})
   with opener.open(request,timeout=20) as r:return json.load(r)
  except urllib.error.HTTPError as e:
   try:message=json.load(e).get('error','The storage action did not finish.')
   except (ValueError,OSError):message='The storage action did not finish.'
   raise ValueError(message) from e
  except (OSError,KeyError) as e:raise ValueError('Open G-Scope first, then reload Scan storage here.') from e
 def ai(self):
  import local_ai
  local=local_ai_config.settings(self.root/'Shared/Settings/local-ai.json')
  return {'local':local,'localModelName':local_ai.model_display_name(local['model'],local['provider']),'general':general_ai.settings(self.root/'Apps/G-Whiz'),'account':self.account.status()}
 def local_models(self):
  import local_ai
  config=local_ai_config.settings(self.root/'Shared/Settings/local-ai.json');items=local_ai_config.request('/api/tags',timeout=3,config=config).get('models',[]);choices={}
  items.sort(key=lambda m:m.get('name')!=config['model'])
  for m in items:
   name=m.get('name','')
   if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',name) or 'cloud' in name.lower():continue
   key=m.get('digest') or name
   if key not in choices:choices[key]={'id':name,'label':local_ai.model_display_name(name,config['provider'])}
  if not any(m['id']==config['model'] for m in choices.values()):choices['configured']={'id':config['model'],'label':local_ai.model_display_name(config['model'],config['provider'])}
  return {'models':list(choices.values())}

 def idle(self):
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  for ident in APPS:
   app=app_directory(self.root,ident);status=app/'Temp/server-status.json'
   try:
    value=json.loads(status.read_text('utf-8'));origin=value.get('url','')
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+',origin):continue
    with opener.open(origin+'/api/health',timeout=1) as r:health=json.load(r)
    if Path(health.get('root','')).resolve()==app.resolve() and (health.get('busy') or health.get('active')):raise ValueError('Pause active app work before changing shared AI settings.')
   except (OSError,KeyError):pass

def make_server(settings,port=0):
 token=secrets.token_urlsafe(32)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,status,value,mime='application/json; charset=utf-8'):
   raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf-8')
   self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'");self.end_headers();self.wfile.write(raw)
  def guard(self,write=False):
   origin='http://127.0.0.1:'+str(self.server.server_port)
   if self.headers.get('Host')!=origin[7:] or self.headers.get('Origin',origin)!=origin or self.headers.get('Sec-Fetch-Site') in ('same-site','cross-site'):raise PermissionError('Use the local G-Works Settings window.')
   if write and not secrets.compare_digest(self.headers.get('X-App-Token',''),token):raise PermissionError('Reopen shared settings before saving.')
  def do_GET(self):
   try:
    self.guard();url=urlsplit(self.path);query=parse_qs(url.query)
    if url.path=='/api/bootstrap':return self.send(200,{'service':'GWorksSettings','uiVersion':SETTINGS_UI_VERSION,'root':str(settings.root),'token':token,'selected':settings.pending_app or settings.selected,'selectedPage':settings.pending_page or settings.selected_page,'requested':settings.pending_app,'requestedPage':settings.pending_page,'requestRevision':settings.show_revision,**settings.context()})
    if url.path=='/api/app':return self.send(200,settings.configuration(query.get('app',[settings.selected])[0]))
    if url.path=='/api/ai':return self.send(200,settings.ai())
    if url.path=='/api/local-models':return self.send(200,settings.local_models())
    if url.path=='/api/scan-storage':return self.send(200,settings.scope_storage('options'))
    assets={'/':'settings-center.html','/settings-center.js':'settings-center.js','/settings-center.css':'settings-center.css'}
    if url.path in assets:
     file=HERE/'Desktop'/assets[url.path];return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0]+'; charset=utf-8')
    self.send(404,{'error':'That settings page is unavailable.'})
   except PermissionError as e:self.send(403,{'error':str(e)})
   except (OSError,ValueError,KeyError) as e:self.send(400,{'error':str(e)[:220]})
  def do_POST(self):
   try:
    self.guard(True);size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=300000 or not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('Use the shared settings controls.')
    data=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
    if not isinstance(data,dict):raise ValueError('Use the displayed fields.')
    with settings.mutex:
     if path in ('/api/scan-storage/preview','/api/scan-storage/execute'):return self.send(200,settings.scope_storage(path.rsplit('/',1)[-1],data))
     if path=='/api/show':
      settings.app(data.get('app'));page=data.get('page','app')
      if page not in PAGES:raise ValueError('Choose a settings page.')
      settings.pending_app=data['app'];settings.pending_page=page;settings.show_revision+=1
      if settings.window:settings.window.restore();settings.window.show()
      return self.send(200,{'shown':True})
     if path=='/api/context':
      current=data.get('revision')==settings.show_revision
      if current and settings.window:settings.window.set_title(settings.context()['title'])
      return self.send(200,{'updated':current})
     if path=='/api/external-settings':return self.send(200,settings.external_settings(data.get('app')))
     if path=='/api/app':return self.send(200,settings.save_document(data))
     if path=='/api/appearance':
      if APP_SPECS.get(data.get('app'),{}).get('external_settings'):raise ValueError('Open this app’s settings to change its appearance.')
      appearance.save(settings.app(data.get('app')),data.get('theme'));return self.send(200,settings.configuration(data['app']))
     if path=='/api/local-ai':
      settings.idle();value=local_ai_config.save(data,settings.root/'Shared/Settings/local-ai.json');return self.send(200,{'saved':True,'configuration':value})
     if path=='/api/general-ai':settings.idle();return self.send(200,{'configuration':general_ai.save(data,settings.root/'Apps/G-Whiz')})
     if path.startswith('/api/account/'):
      settings.idle();op=path.rsplit('/',1)[-1]
      if op=='start':value=settings.account.start(data.get('profile',''))
      elif op=='cancel':value=settings.account.cancel()
      elif op=='select':value=settings.account.select(data['profile'])
      elif op=='models':value=settings.account.models()
      elif op=='logout':value=settings.account.logout()
      elif op=='acknowledge':value=settings.account.acknowledge()
      else:raise ValueError('Unavailable account action.')
      return self.send(200,value)
    self.send(404,{'error':'That settings action is unavailable.'})
   except PermissionError as e:self.send(403,{'error':str(e)})
   except (OSError,ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e)[:220]})
 return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--app',choices=APPS);parser.add_argument('--page',choices=PAGES,default='app');args=parser.parse_args()
 if not (args.root/'.gworks/root.json').is_file():raise ValueError('Choose the installed G-Works root.')
 args.app=args.app or 'whiz';args.root=settings_root(args.root)
 selected=app_directory(args.root,args.app);os.environ['GWORKS_APP_ROOT']=str(selected)
 runtimes=[selected/'Dependencies/DesktopRuntime',*[app_directory(args.root,key)/'Dependencies/DesktopRuntime' for key in APPS]]
 runtime=next((folder for folder in runtimes if (folder/'webview').is_dir()),runtimes[0]);sys.path.insert(0,str(runtime))
 import webview
 state=Settings(args.root,args.app,args.page);http=make_server(state);origin='http://127.0.0.1:'+str(http.server_port);folder=center_directory(args.root);folder.mkdir(parents=True,exist_ok=True)
 # OS-level lock prevents simultaneous launch requests from creating two centers.
 import msvcrt
 lock=(folder/'window.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
 try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
 except OSError:lock.close();open_center(selected,args.app,args.page);return
 (folder/'status.json').write_text(json.dumps({'url':origin,'pid':os.getpid()}),'utf-8')
 threading.Thread(target=http.serve_forever,daemon=True).start()
 state.window=webview.create_window(state.context()['title'],origin,js_api=picker_api(state,webview),width=1080,height=800,min_size=(840,580),background_color='#f3f7f7',text_select=True)
 def style_window():
  try:
   from System import Action
   from System.Drawing import Icon
   def apply():
    appearance.style_native(state.window.native,'signature','G-Works')
    personal=state.context()['suite']=='personal';owner=app_directory(state.root,state.pending_app or state.selected).parent.parent
    record=json.loads((owner/'.gworks/installation.json').read_text('utf-8-sig'));icon=owner/record['launcher']
    if icon.is_file():state.window.native.Icon=Icon.ExtractAssociatedIcon(str(icon))
   state.window.native.BeginInvoke(Action(apply))
  except Exception:pass
 state.window.events.loaded+=style_window
 state.window.events.closed+=lambda:http.shutdown()
 try:webview.start(gui='edgechromium',private_mode=True)
 finally:http.server_close();(folder/'status.json').unlink(missing_ok=True);lock.close()

if __name__=='__main__':main()
