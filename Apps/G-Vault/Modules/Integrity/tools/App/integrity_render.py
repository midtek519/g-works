"""Integrity openings over the existing MH letter class; all input text escaped."""
import unicodedata,re
from student_names import full_name
def render(shared,data,profile,case,party,base,final=False):
 data=dict(data);data['paragraphs']=list(data['paragraphs'])
 # PDF extraction can collapse a whole page into one paragraph. Introduce only
 # a sentence-boundary paragraph break so a bounded final block can stay intact.
 last=data['paragraphs'][-1]
 if len(last.split())>250:
  choices=[m.end()for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])',last)if 60<=len(last[m.end():].split())<=200]
  if choices:
   split=min(choices,key=lambda at:abs(len(last[at:].split())-90));data['paragraphs'][-1:]=[last[:split].strip(),last[split:].strip()]
 # Preserve mathematical glyphs found in historical Word/PDF text.
 shared.TEX.update({'\U0001d453':r'\ensuremath{f}','\u2032':r'\ensuremath{{}^{\prime}}'})
 for value in data['paragraphs']:
  for char in set(value):
   if unicodedata.name(char,'').startswith('MATHEMATICAL '):
    plain=unicodedata.normalize('NFKC',char)
    if len(plain)==1 and plain.isascii()and plain.isalnum():shared.TEX[char]=r'\ensuremath{'+plain+'}'
 e=shared.escape;lines=shared.lines;sender=profile['sender']
 if data.get('structured_outcome'):data['recipient_lines']=[]
 out=[r'\documentclass{mhletter}',r'\usepackage{mh-integrity}',r'\usepackage{needspace}',
      r'\widowpenalty=10000\clubpenalty=10000',
      r'\LetterSender{'+e(sender['name'])+'}{'+e(sender['title'])+'}{'+e(sender['department'])+'}',
      r'\LetterContact{'+lines(sender.get('contact_lines',[]))+'}',r'\LetterDate{'+e(data['date'])+'}',
      r'\LetterRecipient{'+lines(data['recipient_lines'])+'}',r'\LetterSubject{'+e(data['subject'])+'}']
 if not final:out.append(r'\LetterStatus{DRAFT -- for author review}')
 if final:
  signature=shared.asset(profile.get('signature_file'),base,shared_signature=True)
  if not signature:raise ValueError('Choose your signature image before creating a signed final.')
  out.append(r'\LetterSignatureFile{'+signature+'}')
 out += [r'\begin{document}',r'\MakeLetterOpening',r'\IntegrityInfo{'+e(full_name(party))+'}{'+e(party.get('ruid',''))+'}{'+e(party.get('email',''))+'}{'+e(('Math 135 — Calculus I for Life Sciences'if case['course']=='135'else 'Math '+case['course']if case['course'].isdigit()else case['course'])if data.get('structured_outcome')else case['course'])+'}{'+e(case['semester'])+'}{'+e(data.get('assessment',''))+'}',e(data['salutation'])+r'\par']
 tail=len(data['paragraphs'])-1;words=0
 for i in range(len(data['paragraphs'])-1,-1,-1):
  addition=len(data['paragraphs'][i].split())
  if words and words+addition>250:break
  tail=i;words+=addition
  if words>=70:break
 protect=words<=250
 for i,p in enumerate(data['paragraphs']):
  if i==tail:out.append(r'\par\noindent\begin{minipage}{\linewidth}\setlength{\parskip}{0.45em}'if protect else r'\Needspace{12\baselineskip}')
  headings={'Violations','Rationale','Recommended sanctions','Appeal information','Hearing and response options'}
  if data.get('structured_outcome')and p in headings:out.append(r'\LetterHeading{'+e(p)+'}')
  elif data.get('structured_outcome')and p.split('\n',1)[0]in data.get('sanction_labels',[])and'\n'in p:
   heading,rest=p.split('\n',1);out.append(r'\textbf{'+e(heading)+r'}\par '+shared.paragraph(rest)+'\n')
  elif data.get('structured_outcome')and all(line.startswith('- ')for line in p.splitlines()if line.strip()):
   out.append(r'\begin{itemize}\setlength{\itemsep}{0.15em}\setlength{\parskip}{0pt}')
   out.extend(r'\item '+shared.paragraph(line[2:])for line in p.splitlines()if line.strip())
   out.append(r'\end{itemize}')
  else:out.append(shared.paragraph(p)+'\n')
 out += [r'\par\nopagebreak[4]',r'\MakeLetterClosing']
 if protect:out.append(r'\end{minipage}\par')
 out += [r'\end{document}']
 return '\n'.join(out)+'\n'
