"""Resolve installed G-Works paths without reading personal records."""
from pathlib import Path
import os,json

def installation(root=None):
    start=Path(root or __file__).resolve()
    for parent in (start,*start.parents):
        if (parent/'Apps').is_dir() and (parent/'Shared').is_dir():return parent
    return None

def registered_suite(root):
    root=Path(root).resolve()
    return (root/'.gworks/root.json').is_file() and (root/'Apps').is_dir() and (root/'Shared').is_dir()

def canonical_settings_root(root):
    """Both registered suites use the professional shared AI/credential store."""
    root=Path(root).resolve()
    try:professional=Path(json.loads((root/'.gworks/root.json').read_text('utf-8-sig')).get('professional_root',root)).resolve()
    except (OSError,ValueError,TypeError):return root
    return professional if registered_suite(professional) else root

def application_root():
    explicit=os.environ.get('GWORKS_APP_ROOT')
    if explicit:return Path(explicit).resolve()
    base=installation()
    return canonical_settings_root(base)/'Apps/G-Vault' if base else Path(__file__).resolve().parents[2]

def settings_directory(root=None):
    base=installation(root)
    return canonical_settings_root(base)/'Shared/Settings' if base else Path(root or application_root())/'Data/PrivateModules/Integration'

def vault_root():
    explicit=os.environ.get('GVAULT_APP_ROOT') or os.environ.get('GWORKS_APP_ROOT')
    if explicit:return Path(explicit).resolve()
    base=installation()
    return canonical_settings_root(base)/'Apps/G-Vault' if base else application_root()
