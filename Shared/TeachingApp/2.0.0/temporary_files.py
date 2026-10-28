"""Bounded cleanup of disposable app caches, excluding saved data and live hosts."""
from pathlib import Path
from contextlib import closing
import json,os,sqlite3,stat

CACHE_NAMES=('Builds','Drafts','PreviewCache')

def protected_caches(root):
 """Old linked TeX wrappers can reference Drafts; inspect metadata only."""
 root=Path(root).resolve()
 databases=[root/'Data/PrivateModules/Grader/grader.sqlite']
 # Teaching caches moved to Whiz; their older linked solutions belong to Scope.
 # Do not lose this guard merely because the apps no longer share a data folder.
 if root.name in ('G-Whiz','G-Vault','G-Scope') and root.parent.name=='Apps' and (root.parent.parent/'Shared').is_dir():
  databases.append(root.parent/'G-Scope/Data/grader.sqlite')
 for database in databases:
  if not database.exists():continue
  try:
   if any(_linked(path) for path in (database,*database.parents)):
    raise ValueError('Linked grading metadata cannot be used for cache cleanup.')
   with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=2)) as connection:
    rows=connection.execute("SELECT metadata FROM material_references WHERE active=1 AND role='solutions' AND format='tex'")
    for (raw,) in rows:
     metadata=json.loads(raw or '{}')
     if not isinstance(metadata,dict) or not metadata.get('solutionSnapshotSha256'):
      return {'Drafts':'Retained for older linked TeX solutions. Relink those solutions before clearing this cache.'}
  except (OSError,sqlite3.Error,ValueError,TypeError):
   return {'Drafts':'Retained because linked-solution metadata could not be checked.'}
 return {}

def _linked(path):return path.is_symlink() or path.is_junction()

def _bases(root):
 root=Path(root).resolve();temp=root/'Temp'
 if _linked(temp) or temp.resolve()!=root/'Temp':raise ValueError('The temporary folder is not a normal app folder.')
 result=[]
 for name in CACHE_NAMES:
  base=temp/name
  if _linked(base) or base.resolve().parent!=temp:raise ValueError('A preview cache is outside the app temporary folder.')
  if base.exists() and not base.is_dir():raise ValueError('A preview cache is not a folder.')
  result.append(base)
 return temp,result

def _contained(path,base):return not _linked(path) and path.resolve().is_relative_to(base)

def summary(root):
 temp,bases=_bases(root);files=0;size=0;unavailable=0
 for base in bases:
  pending=[base] if base.exists() else []
  while pending:
   folder=pending.pop()
   try:
    for path in folder.iterdir():
     if not _contained(path,base):unavailable+=1;continue
     if path.is_dir():pending.append(path)
     elif path.is_file():size+=path.stat().st_size;files+=1
   except OSError:unavailable+=1
 return {'bytes':size,'files':files,'unavailable':unavailable,'path':str(temp),'protected_caches':protected_caches(root)}

def _writable(path):
 info=path.stat(follow_symlinks=False)
 if getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_READONLY or not info.st_mode&stat.S_IWRITE:path.chmod(info.st_mode|stat.S_IWRITE|stat.S_IREAD)

def clear(root):
 _,bases=_bases(root);before=summary(root);skipped=0;protected=before['protected_caches']
 def remove(path,base,keep=False):
  nonlocal skipped
  try:
   if not _contained(path,base):skipped+=1;return
   if path.is_dir():
    _writable(path)
    for child in list(path.iterdir()):remove(child,base)
    if not keep:path.rmdir()
   else:
    try:path.unlink()
    except PermissionError:_writable(path);path.unlink()
  except FileNotFoundError:pass
  except OSError:skipped+=1 # In-use or inaccessible cache entries stay in place.
 for base in bases:
  if base.name not in protected and base.exists():remove(base,base,keep=True)
 after=summary(root)
 return {**after,'cleared_bytes':max(0,before['bytes']-after['bytes']),'cleared_files':max(0,before['files']-after['files']),'skipped_entries':skipped}
