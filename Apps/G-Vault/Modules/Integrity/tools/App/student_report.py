"""Match student emails only inside individual involved-party report blocks."""
import re, subprocess
from pathlib import Path

def matched_emails(text, party):
 section=re.split(r'Involved Parties',text,flags=re.I)
 if len(section)<2:return set()
 section=re.split(r'\bQuestions\b',section[1],maxsplit=1,flags=re.I)[0]
 blocks=re.split(r'(?im)(?=^\s*(?:Student(?:\s+full)?\s+name|Name)\s*:)',section)
 norm=lambda x:sorted(re.findall(r'[a-z]+',x.lower()))
 found=set()
 # Maxient's printed report can use table rows instead of labelled fields.
 rows=list(re.finditer(r'(?m)^\s*([^\n\r()]+?)\s*\((\d{9})\)[ \t]*',section))
 for i,row in enumerate(rows):
  if party.get('ruid'):
   if row[2]!=re.sub(r'\D','',party['ruid']):continue
  elif norm(row[1])!=norm(party.get('name','')):continue
  block=section[row.end():rows[i+1].start()if i+1<len(rows)else len(section)]
  found.update(x.lower()for x in re.findall(r'(?i)\b[A-Z0-9._%+-]+@(?:scarletmail\.)?rutgers\.edu(?![\w.-])',block))
 for block in blocks:
  name=re.search(r'(?im)^\s*(?:Student(?:\s+full)?\s+name|Name)\s*:\s*([^\n\r]+)',block)
  ids=re.findall(r'(?i)(?:RUID|Student\s*(?:ID|number)|ID\s*number)\s*[:#-]?\s*([\d-]{9,11})',block)
  ids={re.sub(r'\D','',x)for x in ids}
  ruid=re.sub(r'\D','',party.get('ruid',''))
  if ruid and ids:
   if ruid not in ids:continue
  elif not name or norm(name[1])!=norm(party.get('name','')):continue
  found.update(x.lower()for x in re.findall(r'(?i)\b[A-Z0-9._%+-]+@(?:scarletmail\.)?rutgers\.edu(?![\w.-])',block))
 return found

def fill_missing(store,case):
 candidates={p['id']:set()for p in case['parties']if not p.get('email')}
 if not candidates:return
 for f in case['files']:
  if f.get('kind')!='incident-report'and not re.search(r'(?:^|[- _])IR(?:\d|[- _])|complaint[ _-]*(?:received|report)|incident[ _-]*report',f.get('name',''),re.I):continue
  path=store.safe_path(f['path'])
  if path.suffix.lower()!='.pdf':continue
  try:
   result=subprocess.run(['C:/texlive/2026/bin/windows/pdftotext.exe','-layout',str(path),'-'],capture_output=True,timeout=30)
   if result.returncode:continue
   text=result.stdout.decode('utf-8',errors='replace')[:1000000]
   for p in case['parties']:
    if p['id']in candidates:candidates[p['id']].update(matched_emails(text,p))
  except (OSError,subprocess.TimeoutExpired):continue
 for p in case['parties']:
  values=candidates.get(p['id'],set())
  if len(values)==1:p['email']=next(iter(values))
