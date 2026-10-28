"""One local signature-path setting shared by Recommendations and Integrity.

This module stores only a path. It never reads image bytes, sender identities,
student/case records, or either module's configuration.
"""
from pathlib import Path
import json,os,secrets

from runtime_paths import vault_root
ROOT=vault_root()

def default(root=None):
    path=Path(root or ROOT)/'Data/PrivateSource/img/signature.png'
    return str(path) if path.is_file() else ''
def config_path(root=None):return Path(root or ROOT)/'Data/PrivateModules/Integration/signature.json'
def current(root=None):
    path=config_path(root)
    if not path.exists():return default(root)
    try:value=json.loads(path.read_text('utf-8'))['signature_file']
    except (OSError,ValueError,KeyError,TypeError):raise ValueError('The shared signature setting could not be read. Choose the signature again in Settings.') from None
    if not isinstance(value,str) or value and (not Path(value).is_absolute() or Path(value).suffix.lower()!='.png'):raise ValueError('Choose a local PNG signature in Settings.')
    return value
def validate(value,root=None):
    if not isinstance(value,(str,type(None))) or value is not None and (len(value)>2000 or any(ord(c)<32 for c in value)):raise ValueError('Choose a local PNG signature file.')
    if not value or not value.strip():return ''
    path=Path(value.strip())
    if not path.is_absolute() or path.suffix.lower()!='.png' or not path.is_file():raise ValueError('Choose an existing local PNG signature file.')
    return str(path.resolve())
def save(value,root=None):
    value=validate(value,root);path=config_path(root);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        temporary.write_text(json.dumps({'signature_file':value},ensure_ascii=False,indent=2)+'\n','utf-8')
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return value
def apply(settings,root=None):return {**settings,'signature_file':current(root)}
