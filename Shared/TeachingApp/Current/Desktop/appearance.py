"""Per-installation desktop palettes, without application data or record access."""
import ctypes, json, os, secrets
from pathlib import Path
CHOICES = (('signature', 'Signature', 'Smooth chrome, a polished frame and coordinated app accents.'), ('daylight', 'Daylight', 'A bright frame and workspace.'), ('dusk', 'Dusk', 'A dark app frame with a light document workspace.'), ('midnight', 'Midnight', 'A dark frame and workspace; PDF pages keep their own colors.'))
PALETTES = {'daylight': {'frame': '#edf1f7', 'frameInk': '#24364b', 'menu': '#e7edf5', 'paper': '#f4f7fc', 'surface': '#ffffff', 'ink': '#20334d', 'muted': '#586b85', 'line': '#cbd6e6', 'hover': '#dce8fa'}, 'dusk': {'frame': '#171d27', 'frameInk': '#e8edf7', 'menu': '#222b39', 'paper': '#f4f7fc', 'surface': '#ffffff', 'ink': '#20334d', 'muted': '#586b85', 'line': '#cbd6e6', 'hover': '#34445b'}, 'midnight': {'frame': '#171d27', 'frameInk': '#e8edf7', 'menu': '#222b39', 'paper': '#1d2430', 'surface': '#252e3e', 'ink': '#e4eaf5', 'muted': '#acb9cd', 'line': '#45546c', 'hover': '#34445b'}, 'signature': {'frame': '#c4d9ed', 'frameInk': '#17375b', 'menu': '#afcae4', 'paper': '#f3f7fc', 'surface': '#fcfdff', 'ink': '#183957', 'muted': '#55718a', 'line': '#bed1e3', 'hover': '#d9e8f5', 'accent': '#2465ab', 'secondary': '#138c8d', 'gold': '#ba8b2a', 'fuchsia': '#b13d8b', 'highlight': '#e6f1fc', 'shade': '#9dbbd6'}}
BRANDS = {'G-Works': ('#33435C', '#d8e0e8', '#c3cfdc', '#33435C', '#f5f7fa', '#c3cfdc'), 'G-Vault': ('#245FB6', '#dce5ef', '#c4d2e2', '#244365', '#f4f7fb', '#c7d5e4'), 'G-Whiz': ('#B72D49', '#eadde1', '#d8c2c9', '#5f2e3c', '#faf5f6', '#dfc9d0'), 'G-Scope': ('#A96A13', '#e9e2cf', '#d7cba9', '#5b461c', '#faf8f2', '#ddd2b8')}

def brand_colors(brand):
    if brand in BRANDS:
        return BRANDS[brand]
    app = os.environ.get('GWORKS_APP_ROOT')
    if app:
        for name in ('Data/edition.json', 'app.json'):
            try:
                values = json.loads((Path(app) / name).read_text('utf-8-sig')).get('palette', [])
                if len(values) == 6 and all((isinstance(v, str) and len(v) == 7 and v.startswith('#') for v in values)):
                    return tuple(values)
            except (OSError, ValueError, TypeError):
                pass
    return BRANDS['G-Vault']

def palette(theme, brand='G-Vault'):
    result = dict(PALETTES[validate(theme)])
    accent, frame, menu, ink, paper, line = brand_colors(brand)
    result.update(accent=accent, secondary=accent, gold=accent, fuchsia=accent)
    if theme == 'signature':
        result.update(frame=frame, frameInk=ink, menu=menu, paper=paper, surface='#ffffff', ink=ink, muted='#637080', line=line, hover=frame, highlight='#ffffff', shade=menu)
    return result

def validate(value):
    if not isinstance(value, str) or value not in PALETTES:
        raise ValueError('Choose a desktop theme.')
    return value

def load(root):
    try:
        return validate(json.loads((Path(root) / 'Data/Desktop/appearance.json').read_text('utf-8'))['theme'])
    except (OSError, ValueError, TypeError, KeyError):
        return 'daylight'

def save(root, value):
    validate(value)
    folder = Path(root) / 'Data/Desktop'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'appearance.json'
    temporary = folder / ('appearance-' + secrets.token_hex(6) + '.tmp')
    try:
        temporary.write_text(json.dumps({'theme': value}) + '\n', 'utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return value

def info(theme, brand='G-Vault'):
    return {'theme': validate(theme), 'brand': brand, 'choices': [{'id': i, 'name': n, 'description': d, 'palette': palette(i, brand)} for i, n, d in CHOICES]}

def colorref(value):
    value = value.lstrip('#')
    return int(value[0:2], 16) | int(value[2:4], 16) << 8 | int(value[4:6], 16) << 16

def style_native(form, theme, brand='G-Vault'):
    """Called only on the form's UI thread; standard resize/Snap controls remain native."""
    from System.Drawing import Color, Font
    from System.Windows.Forms import ToolStripRenderMode
    colors = palette(theme, brand)
    color = lambda key: Color.FromArgb(int(colors[key][1:3], 16), int(colors[key][3:5], 16), int(colors[key][5:7], 16))
    form.BackColor = color('paper')
    for control in form.Controls:
        if control.GetType().Name == 'MenuStrip':
            control.BackColor = color('frame')
            control.ForeColor = color('frameInk')
            control.Font = Font('Segoe UI', 9)
            control.RenderMode = ToolStripRenderMode.System

            def items(values):
                for item in values:
                    item.BackColor = color('frame')
                    item.ForeColor = color('frameInk')
                    if hasattr(item, 'DropDownItems') and item.DropDownItems.Count:
                        item.DropDown.BackColor = color('menu')
                        item.DropDown.ForeColor = color('frameInk')
                        items(item.DropDownItems)
            items(control.Items)
    caption(form, theme, brand)

def caption(form, theme, brand='G-Vault'):
    colors = palette(theme, brand)
    try:
        handle = ctypes.c_void_p(form.Handle.ToInt64())
        dwm = ctypes.windll.dwmapi
        dark = sum((int(colors['frame'][i:i + 2], 16) for i in (1, 3, 5))) < 384
        for attribute, value in ((20, int(dark)), (35, colorref(colors['frame'])), (36, colorref(colors['frameInk'])), (34, colorref(colors['menu']))):
            native_value = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(handle, attribute, ctypes.byref(native_value), ctypes.sizeof(native_value))
    except (AttributeError, OSError):
        pass
