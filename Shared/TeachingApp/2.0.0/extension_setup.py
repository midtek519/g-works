"""User-controlled installation of the bundled G-Works Chrome extensions.

No Chrome profile, policy, extension preference or website form is modified.
"""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess,sys

ROOT=Path(os.environ.get('GWORKS_APP_ROOT',str(Path(__file__).resolve().parents[1]))).resolve()
EXTENSIONS={
    'course-organizer':('G-View','G-Whiz','Tools/Course Organizer/extension'),
    'rubric-lens':('G-Rater','G-Scope','Data/PrivateModules/Grader/tools/Rubric Lens/extension'),
    'integrity-helper':('G-Report','Integrity','Data/PrivateModules/Integrity/tools/Form Autofill/Chrome Extension'),
}
MAINTENANCE_FILES=('g-extension-setup.html','g-extension-setup.js','g-extension-setup.css')

def stage_maintenance_files(info):
    """Copy only reviewed program assets; never change Chrome's registration."""
    folder=Path(info['folder']).resolve()
    for name in MAINTENANCE_FILES:
        source=Path(__file__).resolve().parent/'extension-assets'/name
        destination=folder/name
        if destination.is_symlink():raise ValueError('Extension setup assets must be normal files.')
        if not destination.exists() or destination.read_bytes()!=source.read_bytes():
            pending=destination.with_suffix(destination.suffix+'.new')
            if pending.is_symlink():raise ValueError('Extension setup assets must be normal files.')
            shutil.copy2(source,pending);os.replace(pending,destination)

def chrome_installations(user_data=None):
    """Read only extension IDs/paths/state from Chrome's saved registration.

    No history, cookies, passwords, profile preferences or policies are changed.
    Chrome 156 omits the old `state` field for enabled unpacked extensions.
    """
    if user_data is None:
        local=os.environ.get('LOCALAPPDATA')
        if not local:return []
        user_data=Path(local)/'Google/Chrome/User Data'
    user_data=Path(user_data)
    if not user_data.is_dir():return []
    def read(path):
        try:
            value=json.loads(path.read_text('utf-8-sig'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}
    last=read(user_data/'Local State').get('profile',{}).get('last_used','Default')
    profiles=[p for p in user_data.iterdir() if p.is_dir() and re.fullmatch(r'Default|Profile \d+',p.name)]
    profiles.sort(key=lambda p:(p.name!=last,p.name!='Default',p.name))
    result=[]
    for profile in profiles:
        settings={}
        for filename in ('Preferences','Secure Preferences'):
            entries=read(profile/filename).get('extensions',{}).get('settings',{})
            if isinstance(entries,dict):settings.update(entries)
        for ident,item in settings.items():
            if not re.fullmatch('[a-p]{32}',ident) or not isinstance(item,dict):continue
            folder=item.get('path')
            if not isinstance(folder,str) or not Path(folder).is_absolute():continue
            result.append({'id':ident,'folder':str(Path(folder).resolve()),'profile':profile.name,
                           'enabled':item.get('state',1)==1 and not item.get('disable_reasons')})
    return result

def installed_extension(info,installations=None):
    folder=Path(info['folder']).resolve()
    for item in chrome_installations() if installations is None else installations:
        if Path(item['folder']).resolve()==folder:return item
    return None

def maintenance_companions():
    """Registered professional companions; no browser registration is changed."""
    suite=Path(__file__).resolve().parents[3]
    return [suite/'Apps/G-Whiz/Tools/Course Organizer/extension',
            suite/'Apps/G-Scope/Tools/Rubric Lens/extension',
            suite/'Apps/G-Vault/Data/PrivateModules/Integrity/tools/Form Autofill/Chrome Extension']

def extension_info(root,ident):
    name,module,relative=EXTENSIONS[ident]
    if ident=='rubric-lens' and Path(root).name=='G-Scope':relative='Tools/Rubric Lens/extension'
    path=Path(root)/relative
    if not path.resolve().is_relative_to(Path(root).resolve()):raise ValueError('The extension must stay inside its G-Works app.')
    manifest=json.loads((path/'manifest.json').read_text('utf-8-sig'))
    if manifest.get('manifest_version')!=3:raise ValueError('This extension needs an update.')
    return {'id':ident,'name':name,'module':module,'folder':str(path.resolve()),'version':manifest['version']}
def chrome_path():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for flag in (0,winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',0,winreg.KEY_READ|flag) as key:
                    candidate=Path(winreg.QueryValue(key,None).strip('"'))
                    if candidate.is_file():return candidate
            except OSError:pass
    for variable in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
        base=os.environ.get(variable)
        if base:
            candidate=Path(base)/'Google/Chrome/Application/chrome.exe'
            if candidate.is_file():return candidate
    return None

def stage_local_defaults(root,ident):
    """Stage this installation's optional profile without bundling it in releases."""
    if ident!='course-organizer':return
    root=Path(root).resolve();source=root/'Data/G-View/local-defaults.json'
    if not source.is_file():return
    if source.is_symlink() or not source.resolve().is_relative_to(root/'Data'):raise ValueError('The local course profile must remain inside app Data.')
    data=json.loads(source.read_text('utf-8-sig'))
    if data.get('app')!='G-View local defaults' or data.get('schema')!=1 or data.get('host')!='rutgers.instructure.com' or not isinstance(data.get('courses'),dict):raise ValueError('Invalid local G-View profile.')
    folder=Path(extension_info(root,ident)['folder']);destination=folder/'local-defaults.json'
    if destination.is_symlink():raise ValueError('The local course profile destination must be a normal file.')
    pending=destination.with_suffix('.json.new');shutil.copy2(source,pending);os.replace(pending,destination)
def open_chrome(info=None,action='manager'):
    if action not in ('manager','reload'):raise ValueError('Unknown extension setup action.')
    chrome=chrome_path()
    if chrome is None:
        os.startfile('https://www.google.com/chrome/')
        return 'Install Chrome, then return here and choose Open Chrome extensions.'
    installations=chrome_installations()
    target=installed_extension(info,installations) if info else None
    if action=='reload' and target and target['enabled']:
        stage_maintenance_files(info)
        url='chrome-extension://'+target['id']+'/g-extension-setup.html?action=reload'
        subprocess.Popen([str(chrome),'--profile-directory='+target['profile'],url],close_fds=True)
        return 'Reload requested. Chrome will show the result; refresh any open pages where you use the extension.'
    # Chrome filters chrome://extensions out of external command lines. An
    # installed extension can open it through the supported tabs API instead.
    helpers=[target] if target and target['enabled'] else []
    for folder in maintenance_companions():
        candidate=installed_extension({'folder':str(folder)},installations)
        if candidate and candidate['enabled'] and candidate not in helpers:helpers.append(candidate)
    for helper in helpers:
        if target and helper['profile']!=target['profile']:continue
        stage_maintenance_files({'folder':helper['folder']})
        url='chrome-extension://'+helper['id']+'/g-extension-setup.html?action=manager'
        if target:url+='&extension='+target['id']
        subprocess.Popen([str(chrome),'--profile-directory='+helper['profile'],url],close_fds=True)
        return 'Chrome extensions requested. Use Reload, or Developer mode → Load unpacked for a first installation.'
    command=[str(chrome)]
    if target:command.append('--profile-directory='+target['profile'])
    subprocess.Popen([*command,'--new-window','about:blank'],close_fds=True)
    return 'Enter chrome://extensions/ in Chrome’s address bar, then Developer mode → Load unpacked. Chrome requires this first installation step.'
def create_form(info):
    sys.path.insert(0,str(ROOT/'Dependencies/DesktopRuntime'))
    import clr
    clr.AddReference('System.Windows.Forms');clr.AddReference('System.Drawing')
    from System.Drawing import Size,Point,Font,Icon,Bitmap
    from System.Windows.Forms import Application,Form,Label,Button,TextBox,FormStartPosition,FormBorderStyle,Clipboard
    Application.EnableVisualStyles()
    form=Form();form.Text=info['name']+' · Extension setup';form.ClientSize=Size(640,350);form.StartPosition=FormStartPosition.CenterScreen;form.FormBorderStyle=FormBorderStyle.FixedDialog;form.MaximizeBox=False
    form.Font=Font('Segoe UI',10)
    icon=Path(info['folder'])/'icons/icon-32.png'
    if icon.exists():
        import ctypes
        bitmap=Bitmap(str(icon));handle=bitmap.GetHicon()
        try:form.Icon=Icon.FromHandle(handle).Clone()
        finally:ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(handle.ToInt64()));bitmap.Dispose()
    def label(text,x,y,w,h):
        c=Label();c.Text=text;c.Location=Point(x,y);c.Size=Size(w,h);form.Controls.Add(c);return c
    label(info['name']+'  ·  '+info['module']+'  ·  '+info['version'],22,20,596,30).Font=Font('Segoe UI',14)
    installed=installed_extension(info)
    label('Reload uses the latest G-Works extension files and keeps your extension settings.\n\nFirst installation: Chrome extensions → Developer mode → Load unpacked. Select the folder below, then pin the extension.',22,65,596,108)
    path=TextBox();path.Text=info['folder'];path.ReadOnly=True;path.Location=Point(22,176);path.Size=Size(596,30);form.Controls.Add(path)
    status=label('Installed in Chrome. Ready to reload.' if installed and installed['enabled'] else 'Chrome approval is required to install or enable the extension.',22,267,596,61)
    def button(text,x,w,action):
        b=Button();b.Text=text;b.Location=Point(x,220);b.Size=Size(w,34)
        def clicked(sender,args):
            try:action()
            except Exception:status.Text='Could not open that option. Use the folder path above in Chrome’s Load unpacked dialog.'
        b.Click+=clicked;form.Controls.Add(b);return b
    def reload():status.Text=open_chrome(info,'reload')
    def chrome():status.Text=open_chrome(info)
    button('Reload extension' if installed and installed['enabled'] else 'Install / enable',22,152,reload)
    button('Chrome extensions',182,152,chrome)
    button('Copy folder path',342,144,lambda:Clipboard.SetText(info['folder']))
    button('Open folder',494,124,lambda:os.startfile(info['folder']))
    return form

def show(info):
    form=create_form(info)
    from System.Windows.Forms import Application
    Application.Run(form)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--extension',choices=EXTENSIONS,required=True);parser.add_argument('--describe',action='store_true');parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args()
    info=extension_info(args.root,args.extension)
    if args.describe:print(json.dumps(info));return
    stage_local_defaults(args.root,args.extension)
    stage_maintenance_files(info)
    sys.path.insert(0,str(ROOT/'Dependencies/DesktopRuntime'))
    import clr
    clr.AddReference('System.Windows.Forms')
    from System.Threading import Thread,ThreadStart,ApartmentState
    ui=Thread(ThreadStart(lambda:show(info)));ui.SetApartmentState(ApartmentState.STA);ui.Start();ui.Join()
if __name__=='__main__':main()
