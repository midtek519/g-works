"""Identify the running backend code and verify its interface is usable."""
from pathlib import Path
import hashlib
def revision():
 base=Path(__file__).resolve().parent;digest=hashlib.sha256(str(base).encode())
 for name in ('server.py','core.py','material_folders.py','toolchain.py','private_module_ui/shared_tex.py'):
  digest.update(name.encode());digest.update((base/name).read_bytes())
 return digest.hexdigest()
def current(health,root,app):
 return health.get('app')==app and Path(health.get('root','')).resolve()==Path(root).resolve() and health.get('runtimeRevision')==revision() and health.get('staticReady') is True
