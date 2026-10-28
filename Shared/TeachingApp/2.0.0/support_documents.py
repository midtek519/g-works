"""Read and revise the course sources for Support Materials."""
from pathlib import Path
import hashlib,re,secrets
from core import term,replace_file

class SupportDocuments:
 def __init__(self,desk):self.desk=desk
 def _sources(self,code,tag,key):
  term(tag);m=self.desk.module(code)
  item=next((x for x in m.discover(tag) if x['key']==key),None)
  if not item or str(item['kind']).lower() in ('exam','quiz','worksheet','groupwork','manual','assessment manual','syllabus','schedule'):raise ValueError('Choose an available support or coordination document.')
  jobs=self.desk.plan(code,tag,[key],mode='all')
  files={};pending=[Path(j['source']) for j in jobs];roots=list(dict.fromkeys(p.relative_to(self.desk.repo).as_posix() for p in pending))
  while pending:
   p=pending.pop(0);relative=p.relative_to(self.desk.repo).as_posix()
   if relative in files:continue
   p=self.desk.source_path(code,relative)
   if len(files)>=40 or p.stat().st_size>250000:raise ValueError('This document is too large for the source editor.')
   raw=p.read_bytes();text=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n');inputs=[]
   for match in re.finditer(r'\\(input|include)\s*\{([^{}]+)\}',re.sub(r'(?<!\\)%[^\n]*','',text)):
    value=match[2]
    if '\\' in value or '#' in value:continue
    for candidate in [self.desk.repo/value,p.parent/value]:
     if not candidate.suffix:candidate=candidate.with_suffix('.tex')
     try:target=self.desk.source_path(code,candidate.relative_to(self.desk.repo).as_posix())
     except (ValueError,FileNotFoundError):continue
     target_relative=target.relative_to(self.desk.repo).as_posix();inputs.append({'command':match[1],'target':value,'file':target_relative});pending.append(target);break
   files[relative]={'path':relative,'tex':text,'revision':hashlib.sha256(raw).hexdigest(),'main':relative in roots,'inputs':inputs}
  return item,jobs,list(files.values())
 def model(self,code,tag,key):
  with self.desk.lock:
   item,jobs,files=self._sources(code,tag,key)
   return {'course':code,'semester':tag,'key':key,'label':item.get('label',item['kind']),'files':files}
 def _edit(self,data):
  code=data['course'];tag=data['semester'];key=data['key'];item,jobs,files=self._sources(code,tag,key)
  file=next((f for f in files if f['path']==data.get('source_file')),None)
  if file is None:raise ValueError('Choose a source belonging to this support document.')
  if data.get('expected_revision')!=file['revision']:raise ValueError('This source changed since you opened it. Keep your edits, then reload the source before saving.')
  text=data.get('tex')
  if not isinstance(text,str) or not text.strip() or len(text.encode('utf-8'))>250000 or '\0' in text:raise ValueError('Enter LaTeX source under 250 KB.')
  return code,tag,key,jobs,files,file,text
 def save(self,data):
  if data.get('confirmed') is not True:raise ValueError('Unlock editing before saving this course document.')
  with self.desk.lock:
   code,tag,key,jobs,files,file,text=self._edit(data);p=self.desk.source_path(code,file['path'])
   if text!=file['tex']:
    self.desk._history({p:p.read_bytes()},'Support document source edited in G-Whiz')
    tmp=p.with_name(p.name+'.partial');tmp.write_text(text,encoding='utf-8',newline='');replace_file(tmp,p)
   return self.model(code,tag,key)
 def preview(self,data):
  with self.desk.lock:
   if self.desk.active:raise ValueError('A compile is already running. Let it finish before starting another.')
   code,tag,key,jobs,files,file,text=self._edit(data)
   folder=self.desk.temp/'Drafts'/'support-preview'/secrets.token_hex(8);folder.mkdir(parents=True)
   targets={f['path']:folder/(str(i)+'.tex') for i,f in enumerate(files)}
   for f in files:
    body=text if f['path']==file['path'] else f['tex']
    for ref in f['inputs']:
     pattern=r'(\\'+ref['command']+r'\s*\{)'+re.escape(ref['target'])+r'(\})'
     body=re.sub(pattern,lambda m:m[1]+targets[ref['file']].as_posix()+m[2],body)
    targets[f['path']].write_text(body,encoding='utf-8')
   snapshots=[{**job,'source':targets[Path(job['source']).relative_to(self.desk.repo).as_posix()],'preview_only':True,'support_preview':True} for job in jobs]
   return self.desk.start(code,tag,[key],mode='all',custom=snapshots)
