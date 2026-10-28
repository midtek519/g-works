"""Native app header over the existing resizable WinForms host.

Only fixed action names, theme colors and validated workspace headings cross
this boundary. Native window buttons never use the WebView JavaScript bridge.
"""
from pathlib import Path
import appearance

_types=None
_brand_forms={}
_brand_type=None

def load():
    global _types
    if _types is None:
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System.Windows.Forms')
        clr.AddReference(str(Path(__file__).with_name('GWorks.Chrome.dll')))
        from GWorks.Desktop import AppFrame,ChromePalette
        _types=(AppFrame,ChromePalette)
    return _types

def palette(theme,brand):
    _,kind=load()
    from System import Array,String
    p=appearance.palette(theme,brand)
    values=[p['frame'],p['frameInk'],p['menu'],p.get('highlight',p['frame']),p.get('shade',p['frame']),p.get('gold',p['menu']),p.get('secondary',p['menu']),p.get('fuchsia',p['menu']),p.get('accent',p['frameInk'])]
    return kind.Create(Array[String](values),theme=='signature')

def install(form,brand,theme,command,icon_path=None,app_root=None):
    """Called on the owning UI thread; constructor rolls back on failure."""
    kind,_=load()
    from System import Action,String
    kind.SetDiagnosticsPath(str((Path(app_root) if app_root else Path(__file__).resolve().parents[2])/'Temp/Desktop/native-paint-errors.log'))
    frame=kind(form,form.webview,brand,Action[String](command),palette(theme,brand))
    global _brand_type
    try:
        if _brand_type is None:
            import clr
            clr.AddReference(str(Path(__file__).with_name('GWorks.Branding.dll')))
            from GWorks.Branding import BrandMark
            _brand_type=BrandMark
        name='g-whiz-instructor.png' if brand=='G-Whiz' else 'g-vault.png'
        _brand_type.Attach(form,brand,str(icon_path or Path(__file__).parents[1]/'static'/name),palette(theme,brand))
        _brand_forms[frame]=form
        def disposed(sender,args):_brand_forms.pop(frame,None)
        form.Disposed+=disposed
    except (ImportError,OSError):pass
    _startup_updates(form,app_root)
    return frame

def apply_theme(frame,theme,brand):
    if frame is not None:
        value=palette(theme,brand);frame.SetTheme(value)
        if _brand_type is not None and frame in _brand_forms:_brand_type.Apply(_brand_forms[frame],value)


def _startup_updates(form,app_root=None):
    # Direct app shortcuts share the hub's signed, nonblocking update check.
    import json,os
    app=Path(app_root or os.environ.get('GWORKS_APP_ROOT',str(Path(__file__).resolve().parents[2]))).resolve()
    root=app.parents[1]
    record=root/'.gworks/installation.json'
    if not record.is_file():return
    try:
        value=json.loads(record.read_text('utf-8-sig'))
        launcher=(root/value['launcher']).resolve()
        if not launcher.is_relative_to((root/'Shared/Launcher').resolve()) or launcher.suffix.lower()!='.exe' or not launcher.is_file():return
        import clr
        clr.AddReference(str(launcher))
        from GWorks import ReleaseUpdates
        ReleaseUpdates.CheckAndPromptAsync(form,str(root),str(value['release']))
    except Exception:
        pass # An absent or offline update service must never block app startup.
