"""Compressed, hash-verified SQLite snapshots with legacy-path compatibility."""
from pathlib import Path
from contextlib import contextmanager
import tempfile,sqlite3,hashlib,json,zipfile,shutil

def checksum(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()

def available_snapshot(path):
 p=Path(path)
 return p if p.is_file() else Path(str(p)+'.zip')if p.suffix.lower()=='.sqlite'and Path(str(p)+'.zip').is_file()else p

def compress_snapshot(source,target=None):
 source=Path(source);target=Path(target)if target else Path(str(source)+'.zip')
 if target.exists():raise ValueError('A backup with this name already exists.')
 expected=checksum(source);size=source.stat().st_size;temp=target.with_name(target.name+'.tmp')
 try:
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
   z.write(source,'database.sqlite');z.writestr('Manifest.json',json.dumps({'format':'math135-sqlite-backup','version':1,'sha256':expected,'bytes':size}))
  with zipfile.ZipFile(temp)as z:
   h=hashlib.sha256()
   with z.open('database.sqlite')as f:
    for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
   if h.hexdigest()!=expected:raise ValueError('The compressed backup did not verify.')
  temp.replace(target);return target
 finally:
  if temp.exists():temp.unlink()

def create_snapshot(connection,folder,name):
 folder=Path(folder)
 if Path(name).name!=name or not name.endswith('.sqlite'):raise ValueError('Choose a simple database backup name.')
 target=folder/(name+'.zip')
 if target.exists()or(folder/name).exists():raise ValueError('A backup with this name already exists.')
 with tempfile.TemporaryDirectory(prefix='snapshot-',dir=folder)as tmp:
  raw=Path(tmp)/'database.sqlite';b=sqlite3.connect(raw)
  try:connection.backup(b)
  finally:b.close()
  return compress_snapshot(raw,target)

@contextmanager
def snapshot_database(path,allowed):
 allowed=Path(allowed).resolve();p=available_snapshot(path).resolve()
 if p.parent!=allowed or not p.is_file()or p.is_symlink():raise ValueError('The backup for this import is unavailable.')
 if p.suffix.lower()!='.zip':
  yield p;return
 try:
  with tempfile.TemporaryDirectory(prefix='restore-',dir=allowed)as tmp:
   raw=Path(tmp)/'database.sqlite'
   with zipfile.ZipFile(p)as z:
    if set(z.namelist())!={'database.sqlite','Manifest.json'}:raise ValueError('The backup archive is invalid.')
    manifest=json.loads(z.read('Manifest.json'))
    if manifest.get('format')!='math135-sqlite-backup'or z.getinfo('database.sqlite').file_size>2*1024**3:raise ValueError('The backup archive is invalid.')
    with z.open('database.sqlite')as src,raw.open('wb')as dst:shutil.copyfileobj(src,dst)
   if raw.stat().st_size!=manifest.get('bytes')or checksum(raw)!=manifest.get('sha256'):raise ValueError('The backup hash did not verify.')
   d=sqlite3.connect('file:'+raw.as_posix()+'?mode=ro',uri=True)
   try:
    if d.execute('pragma quick_check').fetchone()[0]!='ok':raise ValueError('The backup database is invalid.')
   finally:d.close()
   yield raw
 except (zipfile.BadZipFile,KeyError,json.JSONDecodeError):raise ValueError('The backup archive could not be read.')from None
