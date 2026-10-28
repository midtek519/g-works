"""Bounded extraction of explicit choice keys from local reviewed academic text."""
import re

def plain(text):
    text=text[:16000].replace('\u2013','-').replace('\u2014','-').replace('--','-')
    text=text.replace(r'\textendash','-').replace(r'\textemdash','-')
    for _ in range(8):
        value=re.sub(r'\\(?:textbf|textit|text|mathbf|mathrm|boxed|emph|mbox)\s*\{([^{}]*)\}',r'\1',text)
        if value==text:break
        text=value
    for token in (r'\(',r'\)',r'\[',r'\]','$'):text=text.replace(token,'')
    return re.sub(r'[ \t]+',' ',text).strip()

def option_set(text,options):
    text=text.strip().strip('()[]{}').strip()
    text=re.sub(r'^(?:options?|choices?|answers?)\s*[:=]?\s*','',text,flags=re.I)
    parts=[p.strip().strip('()[]{}').strip() for p in re.split(r'\s*(?:,|\+|&|\band\b)\s*',text,flags=re.I)]
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9]{1,8}',p) or p.upper() not in options for p in parts):return None
    return tuple(sorted(set(p.upper() for p in parts),key=options.index))

def explicit_keys(text,version,options,multiple):
    """Return explicit candidates and a flag when an applicable mapping is malformed."""
    text=plain(text);version=re.sub(r'^version\s+','',version,flags=re.I).strip().upper()
    found=[];bad=False;bound=False
    # A range/list maps by position only when its complete length is exact.
    pattern=r'\bVersions\s+([A-Z]\s*-\s*[A-Z]|[A-Z](?:\s*,\s*[A-Z])+(?:\s*(?:,?\s*and|&)\s*[A-Z])?)\s*[:=]\s*([^.;\n]+)'
    for match in re.finditer(pattern,text,re.I):
        bound=True;labels=match[1].upper()
        if '-' in labels:
            a,b=re.split(r'\s*-\s*',labels);versions=[chr(i) for i in range(ord(a),ord(b)+1)]
        else:versions=re.findall(r'\b[A-Z]\b',labels)
        if version not in versions:continue
        values=re.sub(r'[, ]*\brespectively\b.*$','',match[2],flags=re.I).strip()
        # Brackets group the selected set for one version in a select-all mapping.
        groups=re.findall(r'\[[^\]]*\]|\([^)]*\)|[^,\s][^,]*',values)
        parsed=[option_set(value,options) for value in groups]
        if len(versions)!=len(parsed) or len(set(versions))!=len(versions) or any(p is None or (not multiple and len(p)!=1) for p in parsed):bad=True
        else:found.append(parsed[versions.index(version)])
    # Explicit per-version entries: Version B: D; Version C: A.
    for match in re.finditer(r'\bVersion\s+([A-Z])\s*[:=]\s*([^.;\n]+)',text,re.I):
        bound=True
        if match[1].upper()!=version:continue
        value=re.split(r'\bVersion\b',match[2],flags=re.I)[0].strip().rstrip(', ')
        key=option_set(value,options)
        if key and (multiple or len(key)==1):found.append(key)
        else:bad=True
    # Never treat one version's explicit mapping as a generic answer.
    if bound or re.search(r'\bVersions?\s+[A-Z](?:\b|\s*-)',text,re.I):return found,bad
    label='(?:'+'|'.join(re.escape(x) for x in sorted(options,key=len,reverse=True))+')'
    atom=r'[\[(]?\s*'+label+r'\s*[\])]?'
    answer=atom+(r'(?:\s*(?:,|\+|&|and)\s*'+atom+r')*' if multiple else '')
    patterns=[r'\b(?:correct\s+(?:answers?|options?|choices?)|(?:final\s+)?answer|select\s+all\s+that\s+apply)\s*(?:(?:is|are)\s*|[:=]\s*)(?:options?\s*)?[\[(]?('+answer+r')[\])]?(?![A-Za-z0-9])',r'\b(?:options?|choices?)\s+[\[(]?('+answer+r')[\])]?\s+(?:is|are)\s+(?:the\s+)?correct\b']
    for pattern in patterns:
        for match in re.finditer(pattern,text,re.I):
            prefix=re.split(r'[.;\n]',text[:match.start()])[-1]
            if re.search(r'\b(?:not|incorrect|wrong)\b',prefix,re.I):continue
            tail=text[match.end():]
            if re.match(r'\s+(?:is|are)\s+not\s+correct\b',tail,re.I):continue
            if re.match(r'\s*(?:,|/|\bor\b|\band\b|\+|&)\s*[\[(]?[A-Za-z0-9]{1,8}\b',tail,re.I):bad=True;continue
            key=option_set(match[1],options)
            if key:found.append(key)
    # An entire reviewed-key line may be simply B, (B), or a formatted B.
    for line in text.splitlines():
        key=option_set(line.strip().rstrip('.'),options)
        if key and (multiple or len(key)==1):found.append(key)
    return found,bad

def resolve(q,version,normalize,blocks,hash_fn):
    c=normalize(q.get('response'))
    if not c or c['type'] not in ('single_choice','multiple_choice'):return c,None
    manual=c.get('correctOrigin')=='manual' or ('correctOrigin' not in c and bool(c['correct']))
    texts=[];letter=re.sub(r'^version\s+','',version,flags=re.I).strip().upper()
    for label,text in blocks.findall(q.get('guidance','')):
        if re.sub(r'^version\s+','',label,flags=re.I).strip().upper()==letter:texts.append(('Reviewed answer key',text))
    texts.extend(('Rubric',i.get('description','')) for i in q.get('items',[]))
    candidates={};ambiguous=False
    for source,text in texts:
        found,bad=explicit_keys(text,letter,c['options'],c['type']=='multiple_choice');ambiguous|=bad
        for key in found:candidates.setdefault(key,set()).add(source)
    info={'version':letter,'candidates':[{'correct':list(key),'sources':sorted(sources)} for key,sources in candidates.items()],'sourceHash':hash_fn({'version':letter,'sources':texts,'options':c['options'],'type':c['type']})}
    if manual:
        info.update(status='manual',correct=c['correct'],message='Entered key for Version '+letter+'.')
        if ambiguous or len(candidates)>1 or (candidates and not any(set(c['correct'])==set(key) for key in candidates)):info['warning']='Entered option preserved. Reviewed sources differ or need clarification.'
        return c,info
    c['correctOrigin']='source'
    if len(candidates)==1 and not ambiguous:
        key,sources=next(iter(candidates.items()));c['correct']=list(key)
        info.update(status='resolved',correct=list(key),message='From '+('reviewed answer key and rubric' if len(sources)>1 else next(iter(sources)).lower())+' for Version '+letter+'.')
    else:
        c['correct']=[]
        status='conflict' if len(candidates)>1 else 'ambiguous' if ambiguous else 'missing'
        message={'conflict':'Reviewed sources contain conflicting correct options.','ambiguous':'The version-specific option mapping is ambiguous.','missing':'No explicit correct option was found for this version.'}[status]
        info.update(status=status,correct=[],message=message+' Enter a reviewed option or correct the source.')
    return c,info
