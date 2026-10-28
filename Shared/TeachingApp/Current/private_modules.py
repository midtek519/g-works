"""Local-only launch boundary for personal student-record modules. No remote APIs."""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,os,secrets,subprocess,threading,time,urllib.request
from vault_workspaces import VaultWorkspaces
from vault_profile import initialize_library

DEFINITIONS={
 'grades':('Grades','Browse grades, imports, and local reports.','Math135','Math135Central'),
 'recommendations':('Recommendation Letters','Prepare and manage recommendation letters.','Recommendations','MHRecommendations'),
 'integrity':('Academic Integrity','Manage cases and prepare case correspondence.','Integrity','MHIntegrity'),
}

class PrivateModules:
    def __init__(self,desk,origin):
        self.desk=desk;self.origin=origin;self.root=desk.data/'PrivateModules';self.lock=threading.RLock();self.state_path=self.root/'Integration/servers.json'
        self.workspaces=VaultWorkspaces(desk.root)
        self.enabled=desk.edition.get('edition') in ('authoring','personal','records')

    def inventory(self):
        if not self.enabled:return []
        return [{'id':key,'name':value[0],'description':value[1],'installed':(self.root/value[2]).is_dir()} for key,value in DEFINITIONS.items()]

    def state(self):
        try:return json.loads(self.state_path.read_text('utf-8'))
        except (OSError,ValueError):return {}

    def save(self,value):
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.state_path.with_suffix('.new');temp.write_text(json.dumps(value,indent=2)+'\n','utf-8');os.replace(temp,self.state_path)

    def health(self,url,module,root,database=None):
        parsed=urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or parsed.path not in ('','/'):return False
        try:
            value=json.load(urllib.request.urlopen(url.rstrip('/')+'/api/health',timeout=2))
            wanted=Path(database) if module=='grades' and database else root/'Math_135_Central.sqlite' if module=='grades' else root
            actual=value.get('database') if module=='grades' else value.get('root')
            return value.get('app')==DEFINITIONS[module][3] and actual and Path(actual).resolve()==wanted.resolve()
        except (OSError,ValueError):return False

    def open(self,module):
        if not self.enabled or module not in DEFINITIONS:raise PermissionError('This module belongs to G-Vault.')
        candidate=self.root/DEFINITIONS[module][2]
        if candidate.is_symlink() or candidate.is_junction():raise ValueError('Use the installed local module folder.')
        installed=candidate.resolve()
        if not installed.is_relative_to(self.root.resolve()) or not installed.is_dir():raise ValueError('This local module is not installed.')
        course=self.workspaces.course() if module=='grades' else None
        database=course['database'] if course else None
        root=database.parent if course else self.workspaces.library(module)
        if not root.is_dir():raise ValueError('The selected local library is unavailable.')
        tools=installed if module=='grades' else installed/'tools'
        if module!='grades':initialize_library(root,module,self.desk.root)
        code=hashlib.sha256()
        for base in (tools/'App',Path(__file__).resolve().parent/'private_module_ui'):
            for path in sorted(base.glob('*.py')):code.update(path.name.encode());code.update(path.read_bytes())
        generation=code.hexdigest()
        with self.lock:
            state=self.state();entry=state.get(module,{})
            oldroot=Path(entry.get('root',str(installed)))
            olddatabase=entry.get('database')
            if entry and self.health(entry.get('url',''),module,oldroot,olddatabase):
                # Refresh older workers when the user next opens their module.
                # The existing stop handler refuses busy work. Loaded editors
                # are not reloaded here or when shared settings are saved.
                current=False
                try:
                    capabilities=json.load(urllib.request.urlopen(entry['url']+'/api/health',timeout=2))
                    current=capabilities.get('codeGeneration')==generation
                    if module in ('recommendations','integrity'):
                        current=current and capabilities.get('aiRouting')==1 and capabilities.get('generalAITransport')==2 and capabilities.get('signatureSettings')==1
                except (OSError,ValueError):pass
                if entry.get('parent')==self.origin() and current and oldroot==root and (not database or olddatabase==str(database)):return self.result(module,entry)
                req=urllib.request.Request(entry['url']+'/__gwhiz/stop',data=b'{}',headers={'X-GWhiz-Module-Key':entry['key'],'Content-Type':'application/json'})
                try:urllib.request.urlopen(req,timeout=3).read()
                except OSError:raise ValueError('The module is still busy. Finish its current action and retry.')
                for _ in range(30):
                    if not self.health(entry['url'],module,oldroot,olddatabase):break
                    time.sleep(.1)
            python=self.desk.root/'Dependencies/python/python.exe';script=tools/'App/server.py'
            if not python.is_file() or not script.is_file():raise ValueError('The local module runtime is incomplete.')
            key=secrets.token_urlsafe(32);env=os.environ.copy();env.update(GWHIZ_PARENT_ORIGIN=self.origin(),GWHIZ_EMBED_KEY=key,GWHIZ_MODULE_ID=module,GWHIZ_SHELL_ASSETS=str(Path(__file__).resolve().parent/'private_module_ui'),GWORKS_CODE_GENERATION=generation,GVAULT_APP_ROOT=str(self.desk.root))
            if course:env.update(GVAULT_COURSE_CODE=course['code'],GVAULT_COURSE_NAME=course['name'],GVAULT_POLICY_MODE=course.get('policy_mode','custom'))
            args=[str(python),'-I','-B',str(script)]
            status=self.root/'Integration/status'/ (module+'.json');status.parent.mkdir(parents=True,exist_ok=True)
            if module=='grades':args+=['--database',str(database),'--status-file',str(status),'--no-browser']
            else:args+=['--root',str(root)]
            logs=self.root/'Integration/logs';logs.mkdir(parents=True,exist_ok=True)
            with (logs/(module+'.log')).open('ab') as output:
                process=subprocess.Popen(args,cwd=root,env=env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if module!='grades':status=root/'tools/server-status.json'
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if process.poll() is not None:raise ValueError('The module could not start. Its diagnostic stays in the local module log.')
                try:
                    live=json.loads(status.read_text('utf-8-sig'))
                    if live.get('pid')==process.pid and self.health(live['url'],module,root,database):
                        entry={'url':live['url'].rstrip('/'),'pid':process.pid,'key':key,'parent':self.origin(),'root':str(root),'database':str(database) if database else None};state[module]=entry;self.save(state)
                        return self.result(module,entry)
                except (OSError,ValueError,KeyError):pass
                time.sleep(.15)
            # A timed-out launch has never been shown to the user. Do not leave
            # an untracked server that could open the same database a second time.
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            raise ValueError('The module is taking longer than expected to start. Try opening it again.')

    def result(self,module,entry):
        return {'id':module,'name':DEFINITIONS[module][0],'url':entry['url']+'/?gwhiz_embed='+entry['key'],'origin':entry['url']}

    def stop_idle(self):
        """Installer-only drain. Each child also checks its own lock and jobs."""
        with self.lock:
            live=[]
            for module,entry in self.state().items():
                if module not in DEFINITIONS:continue
                root=Path(entry.get('root',str(self.root/DEFINITIONS[module][2])));database=entry.get('database')
                if not self.health(entry.get('url',''),module,root,database):continue
                health=json.load(urllib.request.urlopen(entry['url']+'/api/health',timeout=2))
                if health.get('busy'):raise ValueError('Finish local processing before updating this app.')
                live.append((module,root,entry,database))
            for module,root,entry,database in live:
                request=urllib.request.Request(entry['url']+'/__gwhiz/stop',data=b'{}',headers={'X-GWhiz-Module-Key':entry['key'],'Content-Type':'application/json'})
                try:urllib.request.urlopen(request,timeout=3).read()
                except OSError:raise ValueError('A module is busy or cannot stop safely. Reopen it, finish its work, and close the app before retrying setup.')
                for _ in range(40):
                    if not self.health(entry['url'],module,root,database):break
                    time.sleep(.1)
                else:raise ValueError('A local module did not stop. No update was applied.')
