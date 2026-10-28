"""Installed app metadata; public builds contain only professional defaults."""
from pathlib import Path
import json,os,re

def _read(path):
 try:
  data=json.loads(path.read_text('utf-8-sig'));return data if isinstance(data,dict) else {}
 except (OSError,ValueError):return {}

def suite_for(start):
 start=Path(start).resolve()
 return next((p for p in (start,*start.parents) if (p/'.gworks/root.json').is_file()),None)

def catalog(start=None):
 owner=suite_for(start or os.environ.get('GWORKS_APP_ROOT',__file__))
 default=owner or Path(__file__).resolve().parents[3]
 registration=_read(default/'.gworks/root.json')
 professional=Path(registration.get('professional_root',default)).resolve()
 specs={ident:{'id':ident,'name':name,'folder':name,'root':str(professional),'suite':'professional'} for ident,name in [('whiz','G-Whiz'),('scope','G-Scope'),('spot','G-Vault')]}
 titles={'professional':'G-Works'}
 candidates=[default,professional]
 for base in tuple(candidates):
  for value in _read(base/'.gworks/root.json').get('linked_roots',[]):
   if isinstance(value,str) and Path(value).is_absolute() and suite_for(value)==Path(value).resolve():candidates.append(Path(value))
 for base in dict.fromkeys(candidates):
  data=_read(base/'.gworks/app-catalog.json');suite=data.get('suite','personal')
  if suite not in ('professional','personal'):continue
  title=data.get('title')
  if isinstance(title,str) and len(title)<80:titles[suite]=title
  for item in data.get('apps',[]):
   if not isinstance(item,dict):continue
   ident=item.get('id','');folder=item.get('folder','');name=item.get('name','')
   if not re.fullmatch('[a-z][a-z0-9-]{0,40}',ident) or not folder or Path(folder).name!=folder or not isinstance(name,str):continue
   if ident in specs:continue
   entry=item.get('entry','')
   if entry and (Path(entry).is_absolute() or '..' in Path(entry).parts):continue
   specs[ident]={**item,'root':str(base.resolve()),'suite':suite}
 return specs,titles
