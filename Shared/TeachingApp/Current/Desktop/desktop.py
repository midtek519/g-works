"""Windows desktop host for the installed teaching and records apps."""
from __future__ import annotations
from pathlib import Path
import argparse,ctypes,hashlib,json,logging,os,re,secrets,shutil,subprocess,sys,threading,time,urllib.request,webbrowser
from urllib.parse import urlsplit,urlunsplit,parse_qs

HERE=Path(__file__).resolve().parent
DEFAULT_ROOT=next((parent/'Apps/G-Vault' for parent in HERE.parents if (parent/'Apps').is_dir() and (parent/'Shared').is_dir()),HERE.parents[1])
ROOT=Path(os.environ.get('GWORKS_APP_ROOT',str(DEFAULT_ROOT))).resolve()
LIB=ROOT/'Dependencies/DesktopRuntime'
sys.path.insert(0,str(LIB))
sys.path.insert(0,str(HERE))
import appearance,script_dialogs,window_chrome,native_chrome
DATA=ROOT/'Data/Desktop'
TEMP=ROOT/'Temp/Desktop'
log=logging.getLogger('local.desktop')

def read_json(path,fallback=None):
    try:return json.loads(Path(path).read_text('utf-8-sig'))
    except (OSError,ValueError):return fallback

PROFILE=read_json(ROOT/'Data/edition.json',{})
MATERIALS=PROFILE.get('materials',True)
KIND='dnd' if (ROOT/'dnd-git').is_dir() else 'materials'
NAME=PROFILE.get('display_name','G-Vault')
PRIVATE=KIND=='materials' and PROFILE.get('edition','authoring') in ('authoring','personal','records') and (ROOT/'Data/PrivateModules').is_dir()
APP_ID='GWillikers' if KIND=='dnd' else 'GWhiz'
ICON='g-whiz-instructor.ico' if NAME=='G-Whiz' else 'g-vault.ico'
VERSION='1.0.0-beta.3'
BOOT_HTML='<!doctype html><html><head><meta charset="utf-8"><title>Opening app</title></head><body style="font:13px Segoe UI,sans-serif;background:#f3f7fc;color:#183957"><p>Opening your workspace…</p></body></html>'

def migrate_profile():
    # Copy once, retaining the earlier profile as a recovery copy. SingleInstance
    # is acquired first so the earlier desktop cannot still own these files.
    legacy=ROOT/'Data/Desktop Prototype'
    if legacy.is_dir() and not (DATA/'Browser Profile').exists():
        shutil.copytree(legacy,DATA,dirs_exist_ok=True,ignore=shutil.ignore_patterns('lockfile','LOCK','Singleton*'))

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value,indent=2)+'\n','utf-8');os.replace(temporary,path)

def local_origin(value):
    try:
        parsed=urlsplit(value)
        if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or parsed.username or parsed.password:return None
        return 'http://127.0.0.1:'+str(parsed.port)
    except (ValueError,TypeError):return None

def get_json(url,timeout=3):
    with urllib.request.urlopen(url,timeout=timeout) as response:return json.load(response)

def backend():
    status=ROOT/'Temp/server-status.json'
    def alive():
        value=read_json(status,{})
        origin=local_origin(value.get('url'))
        if not origin:return None
        try:
            health=get_json(origin+'/api/health')
            if health.get('app')==APP_ID and Path(health.get('root','')).resolve()==ROOT:return origin
        except (OSError,ValueError):pass
    origin=alive()
    if origin:return origin
    TEMP.mkdir(parents=True,exist_ok=True)
    # Keep the familiar origin if available, preserving browser recovery storage.
    previous=read_json(status,{})
    port=urlsplit(previous['url']).port if local_origin(previous.get('url')) else 0
    import socket
    if port:
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:port=0
    with (TEMP/'backend-output.log').open('ab') as output:
        process=subprocess.Popen([str(ROOT/'Dependencies/python/pythonw.exe'),'-I','-B',str(ROOT/'App/server.py'),'--root',str(ROOT),'--port',str(port or 0)],cwd=ROOT,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        origin=alive()
        if origin:return origin
        if process.poll() is not None:raise RuntimeError(f'The local {NAME} service could not start. See Temp/Desktop.')
        time.sleep(.2)
    raise RuntimeError(f'The local {NAME} service did not become ready.')

class SingleInstance:
    def __init__(self,namespace=''):
        suffix=hashlib.sha256((str(ROOT)+namespace).encode()).hexdigest()[:16]
        kernel=ctypes.windll.kernel32
        kernel.CreateMutexW.restype=ctypes.c_void_p;kernel.CreateEventW.restype=ctypes.c_void_p
        kernel.OpenEventW.restype=ctypes.c_void_p
        self.mutex=kernel.CreateMutexW(None,False,'Local\\GWorksDesktop-'+suffix)
        self.other=kernel.GetLastError()==183
        name='Local\\GWorksDesktopFocus-'+suffix
        if self.other:
            event=kernel.OpenEventW(0x0002,False,name)
            if event:kernel.SetEvent(ctypes.c_void_p(event));kernel.CloseHandle(ctypes.c_void_p(event))
            return
        self.event=kernel.CreateEventW(None,False,False,name)
    def listen(self,shell):
        kernel=ctypes.windll.kernel32
        while not shell.finished.is_set():
            if kernel.WaitForSingleObject(ctypes.c_void_p(self.event),700)==0:
                try:shell.main.restore();shell.main.show()
                except Exception:pass
    def close(self):
        for handle in [getattr(self,'event',None),getattr(self,'mutex',None)]:
            if handle:ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))

class CloseCoordinator:
    """Bounded close checks; stale page callbacks cannot approve a later request."""
    def __init__(self,failed,delay=8,timer_factory=threading.Timer):
        self.failed=failed;self.delay=delay;self.timer_factory=timer_factory
        self.lock=threading.RLock();self.pending={};self.pauses={}
    def _arm(self,role,entry):
        if entry['timer']:entry['timer'].cancel()
        entry['timer']=None
        if self.pauses.get(role) or entry['recovering']:return
        timer=self.timer_factory(self.delay,lambda:self.expire(role,entry['id']))
        timer.daemon=True;entry['timer']=timer;timer.start()
    def begin(self,role):
        with self.lock:
            if role in self.pending:return self.pending[role]['id'],False
            entry={'id':secrets.token_urlsafe(18),'timer':None,'recovering':False}
            self.pending[role]=entry;self._arm(role,entry)
            return entry['id'],True
    def current(self,role,request_id,recovering=False):
        with self.lock:
            entry=self.pending.get(role)
            return bool(entry and entry['id']==request_id and entry['recovering']==recovering)
    def pause(self,role,source,waiting,request_id=None):
        with self.lock:
            if request_id is not None and not self.current(role,request_id):return False
            reasons=self.pauses.setdefault(role,set())
            if waiting:reasons.add(source)
            else:reasons.discard(source)
            entry=self.pending.get(role)
            if entry:self._arm(role,entry)
            return True
    def expire(self,role,request_id):
        with self.lock:
            if not self.current(role,request_id) or self.pauses.get(role):return
            entry=self.pending[role];entry['recovering']=True
            if entry['timer']:entry['timer'].cancel()
            entry['timer']=None
        self.failed(role,request_id)
    def resolve(self,role,request_id,recovering=False):
        with self.lock:
            if not self.current(role,request_id,recovering):return False
            entry=self.pending.pop(role)
            if entry['timer']:entry['timer'].cancel()
            self.pauses.get(role,set()).discard('page')
            return True
    def renderer_failed(self,role):
        with self.lock:
            self.pauses.get(role,set()).discard('page')
            entry=self.pending.get(role)
            if not entry:return
            request_id=entry['id']
        self.expire(role,request_id)
    def abandon(self,role):
        with self.lock:
            entry=self.pending.pop(role,None)
            if entry and entry['timer']:entry['timer'].cancel()
            self.pauses.pop(role,None)
    def clear(self):
        with self.lock:
            for role in list(self.pending):self.abandon(role)
            self.pauses.clear()


class Api:
    """Explicit desktop actions only; no generic filesystem, code or shell bridge."""
    def __init__(self,shell,role='main'):self._shell=shell;self._role=role
    def open_preview(self,url):return self._shell.preview(url)
    def toggle_preview_pin(self):return self._shell.toggle_preview_pin()
    def open_settings(self,section='appearance'):
        return self._shell.shared_settings()
    def open_folders(self):return self._shell.tools('folders','materials')
    def open_help(self,section='about'):return self._shell.tools('settings',section)
    def set_theme(self,theme):return self._shell.set_theme(theme)
    def menu_action(self,action):return self._shell.menu_action(action,self._role)
    def window_action(self,action):return self._shell.window_action(action,self._role)
    def toggle_fullscreen(self,leave=False):return self._shell.fullscreen(self._role,leave)
    def open_folder(self,name):return self._shell.open_folder(name)
    def signature_info(self):
        if self._role!='tools' or not PRIVATE:return {'error':'Open letterhead settings first.'}
        if str(HERE.parent/'private_module_ui') not in sys.path:sys.path.insert(0,str(HERE.parent/'private_module_ui'))
        import shared_signature
        return {'path':shared_signature.current()}
    def browse_signature(self):
        if self._role!='tools' or not PRIVATE:return {'error':'Open letterhead settings first.'}
        window=self._shell.window_for(self._role)
        if not window:return {'error':'The Settings window is unavailable.'}
        if str(HERE.parent/'private_module_ui') not in sys.path:sys.path.insert(0,str(HERE.parent/'private_module_ui'))
        import shared_signature
        initial=Path(shared_signature.current()).parent
        if not initial.is_dir():initial=ROOT/'Data/PrivateSource/img'
        files=window.create_file_dialog(self._shell.webview.FileDialog.OPEN,directory=str(initial),allow_multiple=False,file_types=('PNG signature (*.png)',))
        if not files:return {'cancelled':True}
        return {'cancelled':False,'path':shared_signature.validate(str(files[0]))}

    def tool_info(self,section='about'):
        result={'name':NAME,'desktop_version':VERSION,'app_version':get_json(self._shell.origin+'/api/bootstrap').get('version','Unknown'),
            'runtime':'pywebview 6.2.1 / Microsoft Edge WebView2'}
        if section=='changelog':result['changelog']=(HERE/'CHANGELOG.txt').read_text('utf-8')
        elif section=='technical':
            history=ROOT/'Maintenance/Instructor Updates/CHANGELOG.txt'
            result['app_history']=history.read_text('utf-8') if PRIVATE and history.is_file() else f'{NAME}\nWindows desktop host {VERSION}\nLocal engine: {APP_ID}\nSettings and generated files remain on this computer.'
        return result
    def state(self,value):
        if not isinstance(value,dict):return False
        shell=self._shell
        if self._role=='main':shell.dirty=bool(value.get('dirty'));shell.busy=bool(value.get('busy'))
        label=value.get('label','')
        if isinstance(label,str) and re.fullmatch(r'[A-Za-z0-9 &/–—:.-]{0,70}',label):
            window=shell.window_for(self._role)
            if window and self._role=='main':
                window.set_title(NAME+(' — '+label if label else ''))
                shell.set_chrome_workspace(label,bool(value.get('canBack')),bool(value.get('canForward')))
        return True
    def begin_close(self,nonce):
        if not secrets.compare_digest(str(nonce),self._shell.nonce):return None
        return self._shell.begin_close(self._role)
    def close_prompt(self,nonce,request_id,waiting):
        if not secrets.compare_digest(str(nonce),self._shell.nonce) or not isinstance(waiting,bool):return False
        if not self._shell.close_checks.current(self._role,request_id):return False
        return self._shell.close_checks.pause(self._role,'page',waiting,request_id=request_id)
    def approve_close(self,nonce,request_id=None):
        shell=self._shell
        if not secrets.compare_digest(str(nonce),shell.nonce):return False
        if not shell.close_checks.resolve(self._role,request_id):return False
        # Let pywebview resolve the calling JavaScript promise before disposing
        # its WebView. Immediate destruction races the bridge's return callback.
        timer=threading.Timer(.15,lambda:shell.approved_close(self._role));timer.daemon=True;timer.start()
        return True
    def close_cancelled(self,request_id=None):
        if not self._shell.close_checks.resolve(self._role,request_id):return False
        if self._role!='main':self._shell.closing_all=False
        return True

class Shell:
    def __init__(self,origin,test=False):
        import webview
        self.webview=webview;self.origin=origin;self.nonce=secrets.token_urlsafe(24);self.theme=appearance.load(ROOT);self.native_dialog_handlers={}
        self.test=test;self.extra_origins=set();self.finished=threading.Event();self.ready=threading.Event()
        self.preview_window=None;self.tools_window=None;self.auxiliary=[];self.lock=threading.RLock()
        self.utility_windows={};self.utility_ready={};self.utility_allow_close=set();self.utility_opening=set();self.boot_targets={}
        self.preview_pinned=False;self.tools_allow_close=False;self.closing_all=False;self.tools_ready=threading.Event()
        self.tools_mode=('settings','materials');self.folder_actions=[]
        self.geometry_lock=threading.RLock()
        self.allow_close=False;self.dirty=False;self.busy=False
        self.close_checks=CloseCoordinator(self.close_fallback)
        self.blocked_external=0;self.blocked_navigations=0;self.native_bound=set();self.errors=[]
        self.state_path=(TEMP/'test-window-state.json') if test else DATA/'window-state.json'
        state=read_json(self.state_path,{})
        self.initial_layout=state;self.geometry_restored=set()
        main=self.geometry(state.get('main',{}),1440,930)
        self.chrome_host=None;self.chrome_attempted=False
        self.api=Api(self)
        self.main=self.create_app_window(NAME,origin+'/',js_api=self.api,min_size=(980,640),text_select=True,zoomable=True,background_color='#f4f7fc' if KIND=='materials' else '#f7f5fb',menu=[],frameless=False,easy_drag=False,shadow=True,**main)
        self.main.events.loaded+=self.loaded_main
        self.main.events.closing+=self.on_closing
        self.main.events.closed+=self.on_closed
        self.main.events.resized+=lambda *args:self.save_geometry()
        self.main.events.moved+=lambda *args:self.save_geometry()
        for event in (self.main.events.resized,self.main.events.maximized,self.main.events.restored):event+=lambda *args:self.notify_chrome()
    def create_app_window(self,title,url,**options):
        # WebView settings changed after NavigationStarting apply only to the
        # next document. Bind the native host on a tiny, inert startup document.
        window=self.webview.create_window(title,html=BOOT_HTML,**options)
        self.boot_targets[window.uid]=url
        return window
    def prepare_document(self,window):
        self.bind_native(window)
        target=self.boot_targets.pop(window.uid,None)
        if target is not None:
            window.load_url(target);return False
        window.run_js(script_dialogs.RESTORE_ALERT)
        return True
    def loaded_document(self,window):
        self.prepare_document(window)
    def offer_ai_setup(self):
        marker=ROOT/'Data/Setup/general-ai.json'
        if KIND!='materials' or getattr(self,'test',False) or not marker.is_file() or getattr(self,'setup_ai_opened',False):return
        self.setup_ai_opened=True
        def setup_ai():
            self.tools('settings','ai');marker.unlink(missing_ok=True)
        threading.Thread(target=setup_ai,daemon=True).start()
    def menu_action(self,action,role='main'):
        allowed={item['action'] for item in [item for item in window_chrome.folder_catalog(KIND,PRIVATE) if item['action']!='folder-grader' and (MATERIALS or item['action']!='folders')]}|{'preview','settings'}
        if not isinstance(action,str) or action not in allowed:return False
        if action=='folders':return self.tools('folders','materials')
        if action.startswith('folder-'):return self.open_folder(action[7:])
        if action=='settings':return self.shared_settings()
        if action=='preview':return self.focus_preview()
        return False
    def window_action(self,action,role='main'):
        if role!='main' or not isinstance(action,str) or action not in window_chrome.WINDOW_ACTIONS:return False
        self.window_command_trace(action,'received')
        if action=='maximize':self.save_geometry()
        done=threading.Event();result=[False]
        def apply():
            try:
                result[0]=bool(window_chrome.act(self.main.native,action));self.notify_chrome();self.window_command_trace(action,'changed' if result[0] else 'declined')
            except Exception as error:
                # Do not let an asynchronous form callback terminate the shell.
                # Log command/error types only; never renderer contents.
                try:
                    with (TEMP/'window-command-errors.log').open('a',encoding='utf-8') as log:log.write(action+': '+type(error).__name__+'\n')
                except OSError:pass
            finally:done.set()
        self.post_ui(self.main,apply)
        # This API worker may wait; the owning UI thread must remain free.
        done.wait(5);return result[0]
    @staticmethod
    def window_command_trace(action,status):
        # Fixed command/status identifiers only; no titles, records or form data.
        try:
            path=TEMP/'window-command-trace.log'
            if path.exists() and path.stat().st_size>32768:path.write_text('',encoding='utf-8')
            with path.open('a',encoding='utf-8') as stream:stream.write(action+': '+status+'\n')
        except OSError:pass
    def notify_chrome(self):
        if not self.main.events.loaded.is_set():return
        def send():
            value=window_chrome.state(self.main.native)
            # ExecuteScriptAsync is nonblocking on the owning UI thread.
            # window.run_js waits for a callback and must not run on that thread.
            core=self.main.native.webview.CoreWebView2
            if core:core.ExecuteScriptAsync('window.GWorksHeader?.state('+json.dumps(value)+');')
        # Window event handlers run outside the form thread. Do not inspect or
        # mutate its native state from those workers.
        self.post_ui(self.main,send)
    def set_chrome_workspace(self,label,back,forward):
        host=getattr(self,'chrome_host',None)
        if host is not None:self.post_ui(self.main,lambda:host.SetWorkspace(label,back,forward))
    def header_command(self,action):
        # Called by native controls on the form thread. Fixed app commands only;
        # window min/max/close and caption movement stay entirely inside Windows.
        scripts={'back':'window.GWorksDesktop?.back();','forward':'window.GWorksDesktop?.forward();','refresh':'window.GWorksDesktop?.refresh?.();'}
        if action not in {*scripts,'folders','fullscreen','leave-fullscreen','settings','preview'}:return False
        try:
            if action=='folders':
                inset=max(0,min(2000,int(self.chrome_host.FolderInset)))
                self.main.native.webview.Focus()
                self.main.native.webview.CoreWebView2.ExecuteScriptAsync('window.GWorksHeader?.folders('+str(inset)+');')
            elif action in scripts:
                self.main.native.webview.Focus()
                self.main.native.webview.CoreWebView2.ExecuteScriptAsync(scripts[action])
            elif action in {'fullscreen','leave-fullscreen'}:self.fullscreen('main',action=='leave-fullscreen')
            elif action=='settings':threading.Thread(target=self.shared_settings,daemon=True).start()
            elif action=='preview':threading.Thread(target=self.focus_preview,daemon=True).start()
            return True
        except Exception as error:
            self.window_command_trace('native-header-'+action,type(error).__name__)
            return False
    def window_for(self,role):
        if role=='main':return self.main
        if role=='preview':return self.preview_window
        return self.utility_windows.get(role)
    @staticmethod
    def post_ui(window,callback):
        # WinForms properties must be changed on their owner thread. In
        # particular, pywebview's on_top setter does not marshal this itself.
        from System import Action
        if window and not window.native.IsDisposed:window.native.BeginInvoke(Action(callback))
    def toggle_preview_pin(self):
        window=self.preview_window
        if not window:return False
        desired=not self.preview_pinned;self.preview_pinned=desired
        def apply():
            if not window.native.IsDisposed:
                window.native.TopMost=desired
                window.native.webview.CoreWebView2.ExecuteScriptAsync('window.GWorksPreviewChrome?.state('+json.dumps(desired)+');')
        self.post_ui(window,apply)
        return desired
    def fullscreen(self,role,leave=False):
        window=self.window_for(role)
        if not window:return False
        def apply():
            form=window.native
            if not leave or form.is_fullscreen:
                host=getattr(self,'chrome_host',None) if role=='main' else None
                if host is not None:host.SetFullscreen(not form.is_fullscreen)
                try:form.toggle_fullscreen()
                finally:
                    if host is not None:host.SetFullscreen(bool(form.is_fullscreen))
            for control in form.Controls:
                if str(control.GetType().Name)=='MenuStrip':control.Visible=not form.is_fullscreen
            if role=='main':self.notify_chrome()
        self.post_ui(window,apply);return True
    def edit(self,role,command):
        window=self.window_for(role)
        key={'undo':'Z','redo':'Y','cut':'X','copy':'C','paste':'V','select-all':'A'}.get(command)
        if not window or not key:return False
        def apply():
            core=window.native.webview.CoreWebView2
            window.native.Activate()
            window.native.webview.Focus()
            # Browser input is delivered to the focused editor, including a
            # cross-origin module iframe, without reading clipboard contents.
            for kind in ('rawKeyDown','keyUp'):
                core.CallDevToolsProtocolMethodAsync('Input.dispatchKeyEvent',json.dumps({'type':kind,'modifiers':2,'windowsVirtualKeyCode':ord(key),'key':key.lower(),'code':'Key'+key}))
        self.post_ui(window,apply);return True
    def open_folder(self,name):
        if KIND=='dnd' and name=='output':
            self.folder_actions.append(name)
            if self.test:return {'opened':True}
            token=get_json(self.origin+'/api/bootstrap')['token']
            request=urllib.request.Request(self.origin+'/api/open',data=json.dumps({'target':'output'}).encode(),headers={'Content-Type':'application/json','X-App-Token':token})
            with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
        if name in ('recommendations','integrity') and not PRIVATE:return {'opened':False,'error':'This module is unavailable in this edition.'}
        folders={'recommendations':ROOT/'Data/PrivateModules/Recommendations/Letters','integrity':ROOT/'Data/PrivateModules/Integrity/Cases','downloads':Path.home()/'Downloads'}
        folder=folders.get(name)
        if folder is None:return {'opened':False,'error':'Choose an available module folder.'}
        if not folder.is_dir() or folder.is_symlink() or folder.is_junction():return {'opened':False,'error':'This folder is not available yet.'}
        if name!='downloads' and not folder.resolve().is_relative_to(ROOT/'Data/PrivateModules'):return {'opened':False,'error':'The module folder is unavailable.'}
        self.folder_actions.append(name)
        if not self.test:os.startfile(str(folder))
        return {'opened':True}
    def shared_settings(self):
        root=next(p for p in ROOT.parents if (p/'Apps').is_dir() and (p/'Shared').is_dir())
        code=(ROOT/'Dependencies/TeachingApp').resolve() if (ROOT/'Dependencies/TeachingApp').is_dir() else root/'Shared/TeachingApp/Current'
        sys.path.insert(0,str(code))
        from settings_center import open_center
        return open_center(ROOT)

    def tools(self,mode='settings',section='materials'):
        if not MATERIALS and section=='materials':section='appearance'
        if section=='grader':return False
        if mode not in ('settings','folders','help'):return False
        if mode=='help' and section=='app-history':section='technical' # Older toolbar compatibility.
        if mode=='help':mode='settings' # All Help pages share the one Settings window.
        if mode=='settings' and section not in ('appearance','ai','temporary','materials','grades','recommendations','integrity','about','changelog','technical'):return False
        if mode=='settings' and section not in ('appearance','ai','temporary','materials','about','changelog','technical') and not PRIVATE:return False
        if mode=='help' and section not in ('about','changelog','technical'):return False
        role='tools' if mode=='settings' else 'folders' if mode=='folders' else section
        window=self.utility_windows.get(role)
        if window:
            window.restore();window.show()
            if role=='tools':window.run_js('window.GWorksTools?.show('+json.dumps(mode)+','+json.dumps(section)+');')
            return True
        with self.lock:
            if role in self.utility_opening:return True
            self.utility_opening.add(role)
        try:
            title,width,height,minimum={
                'tools':('Settings — '+NAME,1040 if PRIVATE else 900,760 if KIND=='materials' else 640,(820,580) if KIND=='materials' else (700,480)),
                'folders':('Output Folders — '+NAME,920 if KIND=='materials' else 760,690 if KIND=='materials' else 420,(740,520) if KIND=='materials' else (600,340)),
                'about':('About '+NAME,560,390,(480,340)),
                'changelog':('Changelog — '+NAME,760,650,(560,440)),
                'technical':('Technical Details — '+NAME,880,660,(620,460))}[role]
            event=self.tools_ready if role=='tools' else threading.Event()
            event.clear();self.utility_ready[role]=event;self.utility_allow_close.discard(role)
            if role=='tools':self.tools_allow_close=False;self.tools_mode=(mode,section)
            window=self.create_app_window(title,self.origin+'/',js_api=Api(self,role),width=width,height=height,min_size=minimum,resizable=role!='about',text_select=True,zoomable=True,background_color='#fafafa',menu=[])
            self.utility_windows[role]=window
            if role=='tools':self.tools_window=window
            window.events.loaded+=lambda:self.loaded_tools(window,role,mode,section)
            window.events.closing+=lambda:self.on_tools_closing(role)
            window.events.closed+=lambda:self.tools_closed(window,role)
        finally:
            with self.lock:self.utility_opening.discard(role)
        return True
    def loaded_tools(self,window,role,mode,section):
        try:
            if not self.prepare_document(window):return
            def owned():
                from System.Windows.Forms import CloseReason
                form=window.native;form.Owner=self.main.native;form.ShowInTaskbar=False;form.MinimizeBox=False
                if role=='about':form.MaximizeBox=False
                # WinForms closes owned forms before asking the owner to close.
                # Let the shell perform one coordinated save/close check instead
                # of starting a second child close request during that cascade.
                form.FormClosing-=form.on_closing
                def closing(sender,args):
                    if args.CloseReason==CloseReason.FormOwnerClosing and not self.allow_close:
                        args.Cancel=True;return
                    form.on_closing(sender,args)
                form.FormClosing+=closing
            self.post_ui(window,owned)
            # Make the local palette renderer an explicit settings dependency.
            # A recycled native binding or document-created callback must not
            # leave Appearance waiting for an unrelated application catalog.
            window.evaluate_js(self.theme_script())
            config=json.dumps({'nonce':self.nonce,'origin':self.origin,'role':role,'name':NAME,'private_modules':PRIVATE,'materials':MATERIALS})
            window.run_js((HERE/('desktop-dnd.js' if KIND=='dnd' else 'desktop.js')).read_text('utf-8').replace('__DESKTOP_CONFIG__',config))
            if KIND=='materials':window.evaluate_js((HERE/'system-settings.js').read_text('utf-8'))
            source=(HERE/('tools-dnd.js' if KIND=='dnd' else 'tools.js')).read_text('utf-8').replace('__TOOLS_INITIAL__',json.dumps([mode,section])).replace('__TOOLS_CONFIG__',json.dumps({'name':NAME,'private_modules':PRIVATE,'materials':MATERIALS}))
            if KIND=='dnd':
                dialog_css=(HERE/'tools.js').read_text('utf-8').split('style.textContent=`',1)[1].split('`;document.head.append(style);',1)[0]
                source=source.replace('__DIALOG_CSS__',json.dumps(dialog_css))
            window.run_js(source);self.utility_ready[role].set()
        except Exception:self.errors.append('settings-initialization');log.exception('Settings integration failed')
    def on_tools_closing(self,role='tools'):
        if role in self.utility_allow_close or (role=='tools' and self.tools_allow_close):return True
        return self.request_close(role)
    def tools_closed(self,window,role='tools'):
        self.close_checks.abandon(role)
        if self.utility_windows.get(role) is window:self.utility_windows.pop(role,None)
        if role in self.utility_ready:self.utility_ready[role].clear()
        if self.tools_window is window:self.tools_window=None;self.tools_ready.clear()
    def approved_close(self,role):
        if role=='main' and self.tools_window:
            self.closing_all=True;self.request_close('tools');return
        if role!='main':
            self.utility_allow_close.add(role)
            if role=='tools':self.tools_allow_close=True
            window=self.window_for(role)
            if window:window.destroy()
            if not self.closing_all:return
        self.allow_close=True;self.close_windows()
    @staticmethod
    def geometry(value,width,height):
        result={}
        for key,default,low,high in [('width',width,980,5000),('height',height,640,4000)]:
            number=value.get(key,default)
            result[key]=int(number) if isinstance(number,(int,float)) and low<=number<=high else default
        # Restore only sizes: invalid/off-screen positions must not hide the app.
        return result
    def allowed_origins(self):
        values={self.origin,*self.extra_origins}
        if not PRIVATE:return values
        state=read_json(ROOT/'Data/PrivateModules/Integration/servers.json',{})
        for name in ('grades','recommendations','integrity'):
            origin=local_origin(state.get(name,{}).get('url'))
            if origin:values.add(origin)
        return values
    def dialog_brand(self,uri):
        origin=local_origin(uri)
        if origin==self.origin:return {'name':NAME,'accent':'#2762a7' if PRIVATE else '#bf2140' if PROFILE.get('theme')=='rutgers' else '#34735c' if KIND=='dnd' else '#2762a7'}
        if PRIVATE:
            state=read_json(ROOT/'Data/PrivateModules/Integration/servers.json',{})
            for key,name,color in (('grades','Math 135 Grades','#2762a7'),('recommendations','Recommendation Letters','#2465ab'),('integrity','Academic Integrity','#2465ab')):
                if origin and origin==local_origin(state.get(key,{}).get('url')):return {'name':name,'accent':color}
        return None
    def theme_script(self):return (HERE/'themes.js').read_text('utf-8').replace('__DESKTOP_APPEARANCE__',json.dumps(appearance.info(self.theme,NAME)))
    def set_theme(self,value):
        self.theme=appearance.save(ROOT,value)
        with self.lock:windows=[self.main,*self.utility_windows.values(),*self.auxiliary,*([self.preview_window] if self.preview_window else [])]
        for window in windows:
            def style(window=window):
                appearance.style_native(window.native,self.theme,NAME)
                if window is self.main:native_chrome.apply_theme(getattr(self,'chrome_host',None),self.theme,NAME)
            self.post_ui(window,style)
            try:window.run_js('window.GWorksAppearance?.apply('+json.dumps(self.theme)+');')
            except Exception:pass # A closed utility window picks up the setting next time.
        return {'theme':self.theme,'saved':True}
    def preview_url(self,value):
        if not isinstance(value,str) or len(value)>4096:raise ValueError('Invalid preview reference.')
        parsed=urlsplit(value)
        if parsed.scheme or parsed.netloc:
            if local_origin(value)!=self.origin:raise ValueError('Preview must belong to this local app.')
        if parsed.path!='/preview.html':raise ValueError('Use the app preview window.')
        if parsed.fragment:
            args=parse_qs(parsed.fragment)
            if 'build' in args and not re.fullmatch('[a-f0-9]{32}' if KIND=='dnd' else '[a-f0-9]{16}',args['build'][0]):raise ValueError('Invalid build reference.')
            if 'pdf' in args and not re.fullmatch(r'/api/course-library/\d+/[a-f0-9]{32}/pdf',args['pdf'][0]):raise ValueError('Invalid PDF reference.')
            allowed={'build','title','pending','error','page'} if KIND=='dnd' else {'build','pdf','title'}
            if not set(args)<=allowed:raise ValueError('Invalid preview options.')
        return self.origin+urlunsplit(('', '',parsed.path,parsed.query,parsed.fragment))
    def preview(self,value):
        url=self.preview_url(value)
        with self.lock:
            window=self.preview_window
            if window is None:
                state=read_json(self.state_path,{})
                size=self.geometry(state.get('preview',{}),1060,850)
                window=self.create_app_window(NAME+' · PDF Preview',url,min_size=(700,500),text_select=True,zoomable=True,**size)
                self.preview_window=window
                window.events.loaded+=lambda:self.loaded_preview(window)
                window.events.closed+=lambda:self.preview_closed(window)
                window.events.resized+=lambda *args:self.save_geometry()
                window.events.moved+=lambda *args:self.save_geometry()
            else:
                # Every accepted preview lives in the same document. Updating
                # its hash through JS preserves WebView readiness; load_url()
                # clears it even for a same-document fragment navigation.
                if window.uid in self.boot_targets:self.boot_targets[window.uid]=url
                elif window.get_current_url()!=url:window.run_js('location.href='+json.dumps(url)+';')
                window.restore();window.show()
        return True
    def focus_preview(self):
        if self.preview_window:
            self.preview_window.restore();self.preview_window.show()
        else:self.preview('/preview.html')
    def preview_closed(self,window):
        with self.lock:
            if self.preview_window is window:self.preview_window=None;self.preview_pinned=False
        if not self.finished.is_set():
            try:self.main.run_js('window.GWorksDesktop?.previewClosed();')
            except Exception:pass
    def loaded_preview(self,window):
        if not self.prepare_document(window):return
        self.restore_position(window,'preview')
        window.expose(window.destroy)
        def preview_fullscreen(leave=False):return self.fullscreen('preview',leave)
        def preview_pin():return self.toggle_preview_pin()
        window.expose(preview_fullscreen,preview_pin)
        window.evaluate_js((HERE/'preview-chrome.js').read_text('utf-8'))
        if KIND=='dnd':
            def preview_job(value):
                if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):return False
                self.main.run_js('window.GWorksDesktop?.previewJob('+json.dumps(value)+');')
                return True
            window.expose(preview_job)
            window.run_js("Object.defineProperty(window,'opener',{configurable:true,value:{closed:false,postMessage(value,origin){if(origin===location.origin&&value?.type==='dnd-preview-job'&&/^[a-f0-9]{32}$/.test(value.id))window.pywebview.api.preview_job(value.id);}}});")
        window.run_js("document.addEventListener('keydown',e=>{if(e.key==='F11'||e.key==='Escape'){e.preventDefault();window.pywebview.api.preview_fullscreen(e.key==='Escape');}else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='w'){e.preventDefault();window.pywebview.api.destroy();}},true);")
        window.run_js("document.documentElement.dataset.gworksDesktop='preview';")
    def loaded_main(self):
        stage='document'
        try:
            if not self.prepare_document(self.main):return
            self.restore_position(self.main,'main')
            config=json.dumps({'nonce':self.nonce,'origin':self.origin,'name':NAME,'private_modules':PRIVATE,'materials':MATERIALS})
            source=(HERE/('desktop-dnd.js' if KIND=='dnd' else 'desktop.js')).read_text('utf-8').replace('__DESKTOP_CONFIG__',config)
            stage='workspace'
            self.main.evaluate_js(source)
            if not self.main.evaluate_js('!!window.GWorksDesktop'):raise RuntimeError('Desktop integration did not initialize')
            stage='header'
            # Native controls are installed before navigation. If that fails,
            # retain the tested standard Windows frame and the HTML app actions.
            header_config={'name':NAME,'folders':[item for item in window_chrome.folder_catalog(KIND,PRIVATE) if item['action']!='folder-grader' and (MATERIALS or item['action']!='folders')],'system_frame':True,'native_header':getattr(self,'chrome_host',None) is not None}
            self.main.evaluate_js((HERE/'header.js').read_text('utf-8').replace('__HEADER_CONFIG__',json.dumps(header_config)))
            if not self.main.evaluate_js('!!window.GWorksHeader && !!document.querySelector(".shell-actions")'):raise RuntimeError('Desktop header did not initialize')
            self.window_command_trace('header','loaded')
            host=getattr(self,'chrome_host',None)
            if host is not None:
                refresh=bool(self.main.evaluate_js('typeof window.GWorksDesktop?.refresh === "function"'))
                self.post_ui(self.main,lambda:host.SetReady(True,refresh))
            self.notify_chrome()
            self.ready.set()
            self.offer_ai_setup()
        except Exception as error:
            self.errors.append('desktop-initialization')
            # Fixed stages and exception types only; no page or editor contents.
            self.window_command_trace('initialization-'+stage,type(error).__name__)
            log.exception('Desktop UI integration failed')
    def bind_native(self,window):
        if window.uid in self.native_bound:return
        # Windows-specific events keep untrusted remote pages out of the shell.
        from System import Action
        form=window.native;pending_scripts=[]
        # Load the small bundled native assembly on this worker, before invoking
        # the UI thread. No runtime compilation or browser data is needed.
        chrome_loaded=False
        if window is self.main and not getattr(self,'chrome_attempted',False):
            self.chrome_attempted=True
            try:native_chrome.load();chrome_loaded=True
            except Exception as error:self.window_command_trace('native-header-load',type(error).__name__)
        def bind():
            core=form.webview.CoreWebView2
            core.Settings.AreDevToolsEnabled=False
            core.Settings.AreBrowserAcceleratorKeysEnabled=False
            appearance.style_native(form,self.theme,NAME)
            if chrome_loaded:
                try:
                    self.chrome_host=native_chrome.install(form,NAME,self.theme,self.header_command)
                    self.window_command_trace('native-header','installed')
                except Exception as error:
                    self.chrome_host=None
                    self.window_command_trace('native-header-install',type(error).__name__)
            self.native_dialog_handlers[window.uid]=script_dialogs.install(core,form,self.dialog_brand,lambda:self.theme,show_fn=lambda *args,**kwargs:self.show_script_dialog(window,*args,**kwargs),restore_focus=lambda:script_dialogs.restore_input_focus(form))
            if hasattr(core,'ProcessFailed'):
                def renderer_failed(sender,args):self.close_checks.renderer_failed(self.window_role(window))
                core.ProcessFailed+=renderer_failed
            core.NewWindowRequested-=form.browser.on_new_window_request
            def navigate(sender,args):
                uri=str(args.Uri)
                origin=local_origin(uri);path=urlsplit(uri).path
                allowed=origin in self.allowed_origins()
                if window is self.main or window in self.utility_windows.values():allowed=origin==self.origin and path=='/'
                elif window is self.preview_window:allowed=origin==self.origin and path=='/preview.html'
                if not allowed:
                    args.Cancel=True
                    self.blocked_navigations+=1
                    if bool(args.IsUserInitiated) and urlsplit(uri).scheme in ('https','http'):webbrowser.open(uri)
            def new_window(sender,args):
                args.Handled=True
                uri=str(args.Uri)
                if local_origin(uri) in self.allowed_origins():
                    if urlsplit(uri).path=='/preview.html' and local_origin(uri)==self.origin:
                        threading.Thread(target=lambda:self.preview(uri),daemon=True).start()
                    elif bool(args.IsUserInitiated):
                        def show():
                            other=self.create_app_window(NAME+' · Document',uri,width=1000,height=820,text_select=True,zoomable=True)
                            self.auxiliary.append(other);other.events.loaded+=lambda:self.loaded_document(other)
                        threading.Thread(target=show,daemon=True).start()
                elif bool(args.IsUserInitiated) and urlsplit(uri).scheme in ('https','http'):webbrowser.open(uri)
            def request(sender,args):
                uri=str(args.Request.Uri);scheme=urlsplit(uri).scheme
                if scheme in ('http','https') and local_origin(uri) not in self.allowed_origins():
                    from System.IO import MemoryStream
                    from System.Text import Encoding
                    args.Response=sender.Environment.CreateWebResourceResponse(MemoryStream(Encoding.UTF8.GetBytes('External content is unavailable inside '+NAME+'.')),403,'Blocked','Content-Type: text/plain')
                    self.blocked_external+=1
            core.NavigationStarting+=navigate
            core.NewWindowRequested+=new_window
            core.WebResourceRequested+=request
            pending_scripts.append(core.AddScriptToExecuteOnDocumentCreatedAsync(script_dialogs.CAPTURE_ALERT))
            pending_scripts.append(core.AddScriptToExecuteOnDocumentCreatedAsync((HERE/'dialogs.js').read_text('utf-8')))
            pending_scripts.append(core.AddScriptToExecuteOnDocumentCreatedAsync((HERE/'frame-guard.js').read_text('utf-8')))
            pending_scripts.append(core.AddScriptToExecuteOnDocumentCreatedAsync(self.theme_script()))
            # Only the inert startup document exists; app pages load after binding.
        form.Invoke(Action(bind))
        # Await registration from this worker while the UI thread remains free.
        for pending in pending_scripts:pending.GetAwaiter().GetResult()
        self.native_bound.add(window.uid)
        window.run_js(self.theme_script())
    def command(self,name,role='main'):
        if name=='close':return self.request_close(role)
        window=self.window_for(role)
        if window and name in {'back','forward'}:window.run_js('window.GWorksDesktop?.'+name+'();')
    def begin_close(self,role):
        if not self.window_for(role):return None
        return self.close_checks.begin(role)[0]
    def request_close(self,role):
        window=self.window_for(role)
        if not window:return False
        request_id,created=self.close_checks.begin(role)
        if not created:
            with self.close_checks.lock:paused=self.close_checks.pauses.get(role,set()).copy()
            if 'page' in paused and 'native' not in paused:self.close_checks.renderer_failed(role)
            return False
        def dispatch():
            try:
                # Do not wait for ExecuteScriptAsync or use run_js: a failed
                # renderer may never complete its callback. The watchdog owns
                # the timeout, independently of the WebView and its bridge.
                core=window.native.webview.CoreWebView2
                if core is None:raise RuntimeError('Renderer unavailable')
                core.ExecuteScriptAsync('window.GWorksDesktop?.close('+json.dumps(request_id)+');')
            except Exception:self.close_checks.expire(role,request_id)
        try:self.post_ui(window,dispatch)
        except Exception:self.close_checks.expire(role,request_id)
        return False
    def show_script_dialog(self,window,*args,**kwargs):
        role=self.window_role(window)
        self.close_checks.pause(role,'native',True)
        try:return script_dialogs.show(*args,**kwargs)
        finally:self.close_checks.pause(role,'native',False)
    def window_role(self,window):
        return 'main' if window is self.main else next((key for key,value in self.utility_windows.items() if value is window),window.uid)
    def close_fallback(self,role,request_id):
        window=self.window_for(role)
        if not window:self.close_checks.abandon(role);return
        def prompt():
            if not self.close_checks.current(role,request_id,recovering=True):return
            accepted=False
            try:
                all_windows=role=='main' or self.closing_all
                message=('The app window is not responding. Close '+NAME+(' and its open windows?' if all_windows else ' Settings?')+
                    '\n\nUnsaved changes may be lost. Local processing will continue.')
                accepted,_=script_dialogs.show(window.native,{'name':NAME},'Confirm',message,theme=self.theme)
            except Exception:self.window_command_trace('close-fallback','dialog-unavailable')
            if not self.close_checks.resolve(role,request_id,recovering=True):return
            if accepted:
                if role=='main':self.allow_close=True;self.close_windows()
                else:self.approved_close(role)
            else:self.closing_all=False
        try:self.post_ui(window,prompt)
        except Exception:
            self.close_checks.abandon(role);self.closing_all=False
            self.window_command_trace('close-fallback','window-unavailable')
    def on_closing(self):
        if self.allow_close:return True
        return self.request_close('main')

    def close_windows(self):
        self.save_geometry()
        self.utility_allow_close.update(self.utility_windows)
        for window in [self.preview_window,*list(self.utility_windows.values()),*self.auxiliary]:
            if window:
                if window is self.tools_window:self.tools_allow_close=True
                try:window.destroy()
                except Exception:pass
        self.main.destroy()
    def on_closed(self):self.close_checks.clear();self.finished.set()
    def save_geometry(self):
        if not self.main.events.shown.is_set():return
        # Never replace the remembered desktop size with monitor-sized bounds.
        if not window_chrome.normal(self.main.native):return
        try:
            # Do not hold a Python lock while asking the native UI thread for
            # dimensions. Window creation/pinning can synchronously raise events.
            preview=self.preview_window
            values={'version':1,'main':{'width':self.main.width,'height':self.main.height,'x':self.main.x,'y':self.main.y}}
            if preview and preview.events.shown.is_set():
                values['preview']={'width':preview.width,'height':preview.height,'x':preview.x,'y':preview.y}
            else:values['preview']=read_json(self.state_path,{}).get('preview',{})
            with self.geometry_lock:
                atomic_json(self.state_path,values)
        except Exception:pass
    def restore_position(self,window,role):
        if window.uid in self.geometry_restored:return
        self.geometry_restored.add(window.uid)
        value=self.initial_layout.get(role,{})
        x=value.get('x');y=value.get('y')
        if not all(type(v) in (int,float) and abs(v)<100000 for v in (x,y)):return
        for screen in self.webview.screens:
            if x+window.width>screen.x+150 and x<screen.x+screen.width-150 and y+window.height>screen.y+100 and y<screen.y+screen.height-100:
                window.move(int(x),int(y));break

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-only',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if (ROOT.parent.parent/'.gworks/install.lock').exists():raise RuntimeError('G-Works setup is updating this app. Wait for setup to finish before opening it.')
    TEMP.mkdir(parents=True,exist_ok=True)
    if args.service_only:print(backend());return
    if args.preflight:
        import webview
        print(json.dumps({'runtime':'pywebview','local_backend':backend(),'separate_profile':str(DATA/'Browser Profile')}));return
    guard=None if args.self_test else SingleInstance()
    if guard and guard.other:guard.close();return
    if not args.self_test:
        migrate_profile()
        def start_local_engine():
            try:
                sys.path.insert(0,str(HERE.parent/'private_module_ui'))
                import local_ai_config
                local_ai_config.startup_readiness()
            except Exception:pass
        threading.Thread(target=start_local_engine,daemon=True).start()
    DATA.mkdir(parents=True,exist_ok=True)
    import webview
    import webview.menu
    origin=backend();shell=Shell(origin,args.self_test)
    if guard:threading.Thread(target=guard.listen,args=(shell,),daemon=True).start()
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=False
    webview.settings['ALLOW_FILE_URLS']=False
    webview.settings['ALLOW_DOWNLOADS']=True
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG']=False
    if args.self_test:
        import faulthandler
        trace=(TEMP/'qa-stack.txt').open('w',encoding='utf-8')
        faulthandler.dump_traceback_later(18,file=trace)
        sys.path.insert(0,str(HERE/'Tests'))
        from desktop_test import run
        worker=lambda:run(shell,args.report)
    elif args.smoke_test:
        def worker():
            report=args.report or TEMP/'launcher-check.json'
            try:
                if not shell.ready.wait(20):raise RuntimeError('Desktop UI did not load')
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    if shell.main.run_js('window.GWorksDesktop?.status().ready'):break
                    time.sleep(.1)
                else:raise RuntimeError('Desktop workspace did not become ready')
                child=subprocess.run([sys.executable,'-I','-B',str(__file__)],timeout=5,capture_output=True)
                if child.returncode:raise RuntimeError('Second desktop launch failed')
                atomic_json(report,{'passed':True,'normal_launcher':True,'duplicate_launch_focuses_existing':True,'separate_profile':str(DATA/'Browser Profile')})
            except Exception:
                atomic_json(report,{'passed':False,'normal_launcher':True})
            finally:
                shell.allow_close=True;shell.close_windows()
    else:worker=None
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Guadagni.'+NAME.replace('-','')+'.Desktop')
        webview.start(worker,gui='edgechromium',debug=False,private_mode=False,storage_path=str((TEMP/'Test Browser Profile') if args.self_test else DATA/'Browser Profile'),icon=str(HERE.parent/'static'/ICON))
    finally:
        if args.self_test:faulthandler.cancel_dump_traceback_later();trace.close()
        shell.finished.set()
        if guard:guard.close()
    if args.self_test or args.smoke_test:
        report=args.report or TEMP/('native-test.json' if args.self_test else 'launcher-check.json')
        if not read_json(report,{}).get('passed'):raise RuntimeError('Native desktop QA failed; inspect its local test report.')

if __name__=='__main__':
    try:main()
    except Exception:
        TEMP.mkdir(parents=True,exist_ok=True)
        with (TEMP/'desktop-error.log').open('a',encoding='utf-8') as stream:
            import traceback;traceback.print_exc(file=stream)
        if '--self-test' in sys.argv or '--smoke-test' in sys.argv:raise
        ctypes.windll.user32.MessageBoxW(None,NAME+' could not open its desktop window. Use G-Works Setup to repair the desktop files.\n\nDiagnostics: Temp/Desktop/desktop-error.log',NAME,0x10)
        sys.exit(1)
