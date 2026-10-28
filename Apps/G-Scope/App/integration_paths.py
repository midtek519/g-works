"""Trusted installed program locations; never accept a renderer-supplied path."""
from pathlib import Path
import json,os,re,subprocess,sys,urllib.request

def installation():
    for p in Path(__file__).resolve().parents:
        if (p/'Apps').is_dir() and (p/'Shared').is_dir():return p
    return None

def app_root():
    here=Path(__file__).resolve().parent
    return here.parent if here.parent.name=='G-Scope' else None

def materials_root():
    base=installation()
    return base/'Apps/G-Whiz' if base else Path(__file__).resolve().parents[5]

def spot_root():
    base=installation()
    return base/'Apps/G-Vault' if base else Path(__file__).resolve().parents[5]

def teaching_code(root=None):
    root=Path(root) if root else (app_root() or spot_root())
    dependency=root/'Dependencies/TeachingApp'
    if dependency.is_dir():
        target=dependency.resolve();allowed=root.parent.parent/'Shared/TeachingApp'
        if not target.is_relative_to(allowed.resolve()):raise ValueError('Repair the shared teaching runtime.')
        return target
    return root/'App'

def ensure_materials_service(root):
    root=Path(root).resolve();state=root/'Temp/server-status.json'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def current():
        try:
            value=json.loads(state.read_text('utf-8-sig'));origin=value.get('url','')
            if not re.fullmatch(r'http://127\.0\.0\.1:\d+',origin):return None
            health=json.load(opener.open(origin+'/api/health',timeout=3))
            return value if health.get('app')=='GWhiz' and Path(health.get('root','')).resolve()==root else None
        except (OSError,ValueError):return None
    value=current()
    if value:return value
    launcher=root/'App/Desktop/desktop.py';python=root/'Dependencies/python/python.exe'
    if not launcher.is_file() or not python.is_file():raise ValueError('Install G-Whiz to use saved handout builds.')
    process=subprocess.run([str(python),'-I','-B',str(launcher),'--service-only'],cwd=root,capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    value=current()
    if process.returncode or not value:raise ValueError('G-Whiz could not start. Open G-Whiz and retry the handout build.')
    return value
