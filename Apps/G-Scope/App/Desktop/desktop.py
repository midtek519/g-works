"""G-Scope desktop shell: fixed local navigation and bounded close/refresh checks."""
from __future__ import annotations
from pathlib import Path
import argparse,importlib.util,json,logging,os,secrets,socket,subprocess,sys,threading,time,urllib.request
from urllib.parse import urlsplit

ROOT=Path(os.environ.get('GWORKS_APP_ROOT',str(Path(__file__).resolve().parents[2]))).resolve()
NAME='G-Scope'
log=logging.getLogger('gscope.desktop')

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text('utf-8-sig'))
    except (OSError,ValueError):return default

def local_origin(value):
    try:
        p=urlsplit(value)
        if p.scheme!='http' or p.hostname!='127.0.0.1' or not p.port or p.username or p.password:return None
        return 'http://127.0.0.1:'+str(p.port)
    except (ValueError,TypeError):return None

def active_backend(root=ROOT):
    status=read_json(root/'Temp/server-status.json',{})
    origin=local_origin(status.get('url'))
    if not origin:return None
    try:
        with urllib.request.urlopen(origin+'/api/health',timeout=2) as response:value=json.load(response)
        if value.get('app')=='GScope' and Path(value.get('root','')).resolve()==root.resolve():return origin
    except (OSError,ValueError,TypeError):pass
    return None

def ensure_backend(root=ROOT,timeout=40):
    origin=active_backend(root)
    if origin:return origin
    status=read_json(root/'Temp/server-status.json',{})
    port=urlsplit(status['url']).port if local_origin(status.get('url')) else 0
    if port:
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:port=0
    folder=root/'Temp/Desktop';folder.mkdir(parents=True,exist_ok=True)
    environment={**os.environ,'GWORKS_APP_ROOT':str(root)}
    for name in ('GWHIZ_PARENT_ORIGIN','GWHIZ_EMBED_KEY'):environment.pop(name,None)
    python=root/'Dependencies/python/pythonw.exe'
    if not python.is_file():python=root/'Dependencies/python/python.exe'
    with (folder/'backend-output.log').open('ab') as output:
        child=subprocess.Popen([str(python),'-I','-B',str(root/'App/server.py'),'--root',str(root),'--port',str(port or 0)],cwd=root,env=environment,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        origin=active_backend(root)
        if origin:return origin
        if child.poll() is not None:raise RuntimeError('G-Scope could not start its local service. See Temp/Desktop/backend-output.log.')
        time.sleep(.15)
    raise RuntimeError('The local G-Scope service did not become ready. Reopen G-Scope to retry.')

def load_common(root=ROOT):
    # This is an installer-owned runtime link, never a client-supplied code path.
    code=(root/'Dependencies/TeachingApp').resolve();desktop=code/'Desktop'
    if not (desktop/'desktop.py').is_file():raise RuntimeError('Shared desktop support is missing. Repair G-Works in Setup.')
    os.environ['GWORKS_APP_ROOT']=str(root)
    for folder in (root/'Dependencies/DesktopRuntime',desktop,code):sys.path.insert(0,str(folder))
    spec=importlib.util.spec_from_file_location('gscope_shared_desktop',desktop/'desktop.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class Api:
    """No generic navigation, file access, command execution or record API."""
    def __init__(self,shell):self._shell=shell
    def open_settings(self):return self._shell.settings()
    def request_waiting(self,nonce,kind,request_id):
        s=self._shell
        if kind not in ('close','refresh') or not secrets.compare_digest(str(nonce),s.nonce):return False
        log.info('Desktop %s confirmation reached page',kind)
        return s.requests.pause(kind,'page',True,request_id=request_id)
    def request_result(self,nonce,kind,request_id,approved):
        s=self._shell
        if kind not in ('close','refresh') or type(approved) is not bool or not secrets.compare_digest(str(nonce),s.nonce):return False
        if not s.requests.resolve(kind,request_id):return False
        log.info('Desktop %s approved: %s',kind,approved)
        if approved:
            timer=threading.Timer(.15,lambda:s.apply(kind));timer.daemon=True;timer.start()
        return True

class Shell:
    def __init__(self,origin,common,webview,root=ROOT):
        self.origin=origin;self.common=common;self.root=root;self.webview=webview;self.nonce=secrets.token_urlsafe(24)
        self.finished=threading.Event();self.allow_close=False;self.requests=common.CloseCoordinator(self.recover,delay=8)
        self.chrome_host=None;self.chrome_attempted=False;self.initial_activation=False
        self.geometry=root/'Data/Desktop/geometry.json'
        value=read_json(self.geometry,{})
        dimension=lambda key,default,low,high:max(low,min(high,value.get(key,default))) if type(value.get(key,default)) is int else default
        self.main=webview.create_window(NAME,origin,js_api=Api(self),width=dimension('width',1400,900,2800),height=dimension('height',950,600,1800),min_size=(980,640),confirm_close=False,background_color='#f6f4ee',text_select=True)
        self.main.events.closing+=self.on_closing
        self.main.events.closed+=self.on_closed
        self.main.events.loaded+=self.on_loaded

    def post_ui(self,callback):
        from System import Action
        form=self.main.native
        if form is None or form.IsDisposed:raise RuntimeError('Window is unavailable.')
        form.BeginInvoke(Action(callback))

    def execute(self,source,on_error=None):
        def dispatch():
            try:
                core=self.main.native.webview.CoreWebView2
                if core is None:raise RuntimeError('Renderer unavailable')
                # Never wait on the WebView's script task. Its callback may never
                # resolve after a renderer hang; the independent watchdog owns it.
                core.ExecuteScriptAsync(source)
            except Exception:
                if on_error:on_error()
        try:self.post_ui(dispatch)
        except Exception:
            if on_error:on_error()

    def request(self,kind):
        if kind not in ('close','refresh'):return False
        request_id,fresh=self.requests.begin(kind)
        if not fresh:
            self.requests.renderer_failed(kind)
            return False
        method='requestClose' if kind=='close' else 'requestRefresh'
        args=','.join(json.dumps(x) for x in (self.nonce,kind,request_id))
        source='''(async()=>{const api=window.pywebview?.api;const fn=window.GScopeDesktop?.METHOD;
if(!api||!fn)return;Promise.resolve(api.request_waiting(ARGS)).catch(()=>{});
try{const yes=await fn();Promise.resolve(api.request_result(ARGS,yes===true)).catch(()=>{});}catch{Promise.resolve(api.request_result(ARGS,false)).catch(()=>{});}})();'''.replace('METHOD',method).replace('ARGS',args)
        log.info('Dispatching desktop %s',kind)
        self.execute(source,lambda:self.requests.expire(kind,request_id));return False

    def settings(self):
        sys.path.insert(0,str((self.root/'Dependencies/TeachingApp').resolve()))
        from settings_center import open_center
        return open_center(self.root,'scope')
    def header_command(self,action):
        if action=='refresh':self.request('refresh');return True
        if action=='settings':self.settings();return True
        if action in ('back','forward','preview'):
            method={'back':'back','forward':'forward','preview':'preview'}[action]
            self.execute('void window.GScopeDesktop?.'+method+'?.();');return True
        if action=='folders':os.startfile(str(self.root/'Data/Projects'));return True
        if action in ('fullscreen','leave-fullscreen') and self.chrome_host is not None:
            self.chrome_host.SetFullscreen(action=='fullscreen');return True
        return False

    def install_chrome(self,form,core):
        self.common.appearance.style_native(form,self.common.appearance.load(self.root),NAME)
        self.chrome_host=self.common.native_chrome.install(form,NAME,self.common.appearance.load(self.root),self.header_command,icon_path=self.root/'App/static/g-scope.png',app_root=self.root)
        self.chrome_host.SetWorkspace('Grading workspace',True,False)
        self.chrome_host.SetReady(True,True)
        core.ExecuteScriptAsync("document.documentElement.dataset.gscopeNativeHeader='true';")

    def on_loaded(self):
        try:
            theme=self.common.appearance.load(self.root)
            self.execute((self.root/'Dependencies/TeachingApp/Desktop/themes.js').read_text('utf-8').replace('__DESKTOP_APPEARANCE__',json.dumps(self.common.appearance.info(theme,NAME))))
        except Exception:log.exception('G-Scope appearance could not initialize; keeping the native frame usable')
        loaded=False
        if not self.chrome_attempted:
            self.chrome_attempted=True
            try:self.common.native_chrome.load();loaded=True
            except Exception:log.exception('G-Scope native header could not load')
        def install():
            form=self.main.native;core=form.webview.CoreWebView2
            if loaded:
                try:self.install_chrome(form,core)
                except Exception:log.exception('G-Scope native header could not install')
            elif self.chrome_host is not None:
                core.ExecuteScriptAsync("document.documentElement.dataset.gscopeNativeHeader='true';")
            if not self.initial_activation:
                self.initial_activation=True
                form.Show();form.Activate()
            if not getattr(self,'navigation_guard_installed',False):
                def navigation(sender,event):
                    if local_origin(str(event.Uri))!=self.origin:event.Cancel=True
                core.NavigationStarting+=navigation
                self.navigation_guard=navigation;self.navigation_guard_installed=True
        try:self.post_ui(install)
        except Exception:log.exception('G-Scope native setup could not dispatch')
    def on_closing(self):return True if self.allow_close else self.request('close')
    def on_closed(self):self.requests.clear();self.finished.set()

    def apply(self,kind):
        if self.finished.is_set():return
        if kind=='close':
            self.allow_close=True;self.save_geometry();self.main.destroy()
        elif kind=='refresh':
            # Setting WebView.Source to its current URL may not navigate, but
            # pywebview.load_url clears its loaded/bridge events unconditionally.
            # Reload on the owning UI thread so a real navigation always occurs.
            def reload_page():
                try:
                    form=self.main.native
                    core=form.webview.CoreWebView2
                    if core is None:raise RuntimeError('Renderer unavailable')
                    log.info('Reloading native WebView')
                    core.Reload()
                except Exception:log.exception('G-Scope could not reload its renderer')
            self.post_ui(reload_page)

    def recover(self,kind,request_id):
        def prompt():
            if not self.requests.current(kind,request_id,recovering=True):return
            accepted=False
            try:
                verb='Close' if kind=='close' else 'Refresh'
                accepted,_=self.common.script_dialogs.show(self.main.native,{'name':NAME},'Confirm',verb+' the unresponsive G-Scope window?\n\nUnsaved edits may be lost. Saved work is retained and local processing continues.',theme='daylight')
            except Exception:log.exception('G-Scope recovery confirmation could not open')
            finally:
                if self.requests.resolve(kind,request_id,recovering=True) and accepted:
                    timer=threading.Timer(.1,lambda:self.apply(kind));timer.daemon=True;timer.start()
        try:self.post_ui(prompt)
        except Exception:self.requests.abandon(kind)

    def save_geometry(self):
        try:
            value={'width':int(self.main.width),'height':int(self.main.height)}
            self.common.atomic_json(self.geometry,value)
        except Exception:pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--service-only',action='store_true');args=parser.parse_args()
    folder=ROOT/'Temp/Desktop';folder.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=str(folder/'desktop-actions.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    common=load_common();guard=None if args.service_only else common.SingleInstance(':gscope-window');startup=None
    try:
        if guard and guard.other:return
        startup=common.SingleInstance(':gscope-service-start')
        if startup.other:
            deadline=time.monotonic()+40;origin=None
            while time.monotonic()<deadline:
                origin=active_backend()
                if origin:break
                time.sleep(.15)
            if not origin:raise RuntimeError('The other G-Scope startup did not become ready.')
        else:origin=ensure_backend()
        startup.close();startup=None
        if args.service_only:print(json.dumps({'url':origin,'app':NAME}));return
        import webview
        webview.settings['ALLOW_DOWNLOADS']=True
        shell=Shell(origin,common,webview)

        def worker():threading.Thread(target=guard.listen,args=(shell,),daemon=True).start()
        icon=ROOT/'App/static/g-scope.ico'
        kwargs={'icon':str(icon)} if icon.is_file() else {}
        webview.start(worker,gui='edgechromium',debug=False,private_mode=False,storage_path=str(ROOT/'Data/Desktop/Browser Profile'),menu=[],**kwargs)
    finally:
        if startup:startup.close()
        if guard:guard.close()

if __name__=='__main__':
    try:main()
    except Exception as error:
        folder=ROOT/'Temp/Desktop';folder.mkdir(parents=True,exist_ok=True)
        (folder/'startup-error.log').write_text(str(error)+'\n','utf-8')
        if '--service-only' in sys.argv:raise
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(error),NAME,0x10)
        except Exception:pass
