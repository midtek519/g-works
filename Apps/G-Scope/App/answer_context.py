"""Bounded academic TeX and parent-question context. Never execute source TeX."""
import re

SUPER=str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱ','0123456789+-()ni')
SUB=str.maketrans('₀₁₂₃₄₅₆₇₈₉₊₋₍₎','0123456789+-()')
SYMBOLS={'∞':r'\infty','±':r'\pm','∓':r'\mp','→':r'\to','⇒':r'\Rightarrow','↔':r'\leftrightarrow','≤':r'\leq','≥':r'\geq','≠':r'\neq','≈':r'\approx','∈':r'\in','∉':r'\notin','∪':r'\cup','∩':r'\cap','∅':r'\emptyset','∫':r'\int','∑':r'\sum','π':r'\pi','θ':r'\theta','α':r'\alpha','β':r'\beta','Δ':r'\Delta','−':'-','×':r'\times','·':r'\cdot'}
def tex_notation(text):
    text=re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱ]+',lambda m:'^{'+m[0].translate(SUPER)+'}',text)
    text=re.sub(r'[₀₁₂₃₄₅₆₇₈₉₊₋₍₎]+',lambda m:'_{'+m[0].translate(SUB)+'}',text)
    def replace(match):
        command=SYMBOLS[match[0]];following=text[match.end():match.end()+1]
        return command+(' ' if command.startswith('\\') and following and (following.isalpha() or following in SYMBOLS) else '')
    return re.sub('['+''.join(SYMBOLS)+']',replace,text)

def group(text,pos):
    while pos<len(text) and text[pos].isspace():pos+=1
    if pos>=len(text) or text[pos]!='{':raise ValueError('Unresolved question TeX.')
    start=pos+1;depth=1;pos+=1
    while pos<len(text):
        if text[pos]=='\\':pos+=2;continue
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':
            depth-=1
            if not depth:return text[start:pos],pos+1
        pos+=1
    raise ValueError('Unresolved question TeX.')

def blank_tex(text,version,*,solutions=False):
    """Resolve only documented finite variants and student/solution switches."""
    if not isinstance(text,str) or len(text)>60000 or not re.fullmatch('[A-Z]',version):raise ValueError('Question TeX unavailable.')
    text=re.sub(r'(?<!\\)%[^\n]*','',text)
    text=re.sub(r'\\begin\s*\{solution\}(?:\[[^\]]*\])?.*?\\end\s*\{solution\}','',text,flags=re.S)
    exercise=re.search(r'\\begin\s*\{exercise\}(?:\[[^\]]*\])?(.*?)\\end\s*\{exercise\}',text,re.S)
    if exercise:text=exercise[1]
    def resolve(value,depth=0):
        if depth>20:raise ValueError('Question variants are too deeply nested.')
        out=[];pos=0
        pattern=re.compile(r'\\(vary|IfMath(?:Student|Solutions)(?:TF|T|F))\b')
        for _ in range(300):
            match=pattern.search(value,pos)
            if not match:out.append(value[pos:]);return ''.join(out)
            out.append(value[pos:match.start()]);command=match[1];first,end=group(value,match.end())
            if command=='vary':
                choices=[];start=0;level=0;i=0
                while i<len(first):
                    if first[i]=='\\':i+=2;continue
                    if first[i]=='{':level+=1
                    elif first[i]=='}':level-=1
                    elif first[i]==';' and level==0:choices.append(first[start:i]);start=i+1
                    i+=1
                choices.append(first[start:]);chosen=choices[(ord(version)-65)%len(choices)]
            else:
                truth=('Solutions' if solutions else 'Student') in command
                if command.endswith('TF'):
                    second,end=group(value,end);chosen=first if truth else second
                else:chosen=first if truth==command.endswith('T') else ''
            out.append(resolve(chosen,depth+1));pos=end
        raise ValueError('Question has too many variants.')
    text=resolve(text).strip()
    # A diagram's local filename is not mathematical context. Its pixels are
    # supplied separately, and no file/include command is ever executed here.
    text=re.sub(r'\\includegraphics(?:\[[^\]]*\])?\s*\{[^{}]*\}',lambda _:r'\GraphProvidedInImage{}',text)
    text=re.sub(r'\\label\s*\{[^{}]*\}','',text)
    if re.search(r'\\(?:includegraphics|href|url|pgfplotstableread)\b|\\addplot[^;\n]*\bfile\b|https?://|[A-Za-z]:[\\/]',text):raise ValueError('Use the printed image for external diagram data.')
    if not text or len(text)>16000 or re.search(r'\\(?:if\w*|else|fi|input|include(?!graphics)|documentclass|usepackage|write\w*|read\w*|open\w*|directlua|catcode|csname)\b',text):raise ValueError('Question TeX requires unsupported source expansion.')
    return text

def related_questions(base,q):
    outline=base.get('outline',[]);node=next((n for n in outline if n.get('graded') and n.get('key')==q['key']),None)
    keys={n['key'] for n in outline if n.get('graded') and node and node.get('parentNumber') and n.get('parentNumber')==node['parentNumber']}
    if not keys:
        match=re.fullmatch(r'(\d+)(?:[a-z]|\.\d+)',q['key'],re.I)
        if match:keys={p['key'] for p in base['questions'] if re.fullmatch(re.escape(match[1])+r'(?:[a-z]|\.\d+)',p['key'],re.I)}
    return [p for p in base['questions'] if p['key'] in keys] or [q]

def context_regions(base,q):
    pages={}
    for item in related_questions(base,q):
        rect=item.get('rect')
        if not rect:continue
        page=item['page']
        if page not in pages:pages[page]=list(rect)
        else:
            old=pages[page];pages[page]=[min(old[0],rect[0]),min(old[1],rect[1]),max(old[2],rect[2]),max(old[3],rect[3])]
    if len(pages)>4:raise ValueError('Use at most four pages of parent-question context.')
    return [{'page':page,'rect':rect} for page,rect in sorted(pages.items())]
