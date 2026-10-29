"""Local compiler reports, including failures that produced no PDF or TeX log."""
from pathlib import Path
import os,secrets

def report(desk,identity,index=None):
 batch=desk.batch(identity);base=desk.temp/'Builds';folder=base/identity
 if not folder.resolve().is_relative_to(base.resolve()):raise ValueError('Choose a local build log.')
 if index is not None:
  index=int(index)
  if not 0<=index<len(batch['jobs']):raise ValueError('Choose an output in this build.')
 jobs=list(enumerate(batch['jobs'])) if index is None else [(index,batch['jobs'][index])]
 brand=getattr(desk,'branding',{}).get('name','G-Whiz')
 text=[brand+' compilation report','Build: '+identity,'Created: '+str(batch.get('created','')),'Course: '+str(batch.get('course','')),'Semester: '+str(batch.get('semester','')),'Status: '+str(batch.get('status','')),'TeX distribution: '+str(batch.get('tex_distribution','Not selected before compilation stopped')),'Compiler: '+str(batch.get('compiler','Not started')),'Message: '+str(batch.get('message',''))]
 if batch.get('log_error'):text+=['Build error: '+batch['log_error']]
 for number,job in jobs:
  work=folder/str(number)
  if not work.resolve().is_relative_to(folder.resolve()):raise ValueError('Choose a local output log.')
  text+=['','='*72,str(job.get('name','Output '+str(number+1))), 'Status: '+str(job.get('status','')),'Exit code: '+str(job.get('exit_code','Not recorded')),'Source: '+str(job.get('source','')),'Message: '+str(job.get('message',''))]
  for filename,label in [('console.txt','Compiler console'),('document.log','TeX log')]:
   source=work/filename
   if source.is_file():
    if not source.resolve().is_relative_to(folder.resolve()):raise ValueError('Choose a local output log.')
    text+=['','--- '+label+' ---',source.read_text('utf-8',errors='replace')]
  if not (work/'console.txt').is_file() and not (work/'document.log').is_file():text+=['','Compiler output is not available yet.' if batch.get('status') in ('queued','running') else 'The compiler produced no log output for this document. See the build message above.']
 target=folder/('Compile-log.txt' if index is None else 'Compile-log-'+str(index+1)+'.txt');temporary=target.with_name(target.name+'.'+secrets.token_hex(6)+'.tmp')
 try:temporary.write_text('\n'.join(text)+'\n','utf-8');os.replace(temporary,target)
 finally:temporary.unlink(missing_ok=True)
 return target
