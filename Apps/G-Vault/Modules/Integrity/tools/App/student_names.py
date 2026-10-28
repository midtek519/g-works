"""Student name components. Never guess compound family names from word positions."""
import re

def parts(value):
 value=value.strip()
 if value.count(',')==1:
  last,first=(x.strip()for x in value.split(',',1))
  if first and last:return {'first_name':first,'last_name':last}
 return {}

def full_name(p):
 first=p.get('first_name','').strip();last=p.get('last_name','').strip()
 return ' '.join(x for x in (first,last)if x) if first and last else p.get('name','').strip()

def normalize_case(c):
 for p in c.get('parties',[]):
  old=p.get('name','');found={}
  if not(p.get('first_name')and p.get('last_name')):
   found=parts(old)
   title_parts=parts(c.get('title',''))
   tokens=lambda v:sorted(re.findall(r'\w+',v.lower()))
   if not found and title_parts and tokens(old)==tokens(c['title']):found=title_parts
   if found:p.update(found)
  display=full_name(p)
  if display and display!=old:
   p.setdefault('original_name',old);p['name']=display
  if len(c.get('parties',[]))==1 and sorted(re.findall(r'\w+',c.get('title','').lower()))==sorted(re.findall(r'\w+',old.lower())):c['title']=display
 return c
