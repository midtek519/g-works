"""Read-only, noninteractive package lookup in one selected TeX installation."""
from pathlib import Path
import os,re,subprocess

MIKTEX_READ_ONLY=['--miktex-disable-installer','--miktex-disable-maintenance','--miktex-disable-diagnose']

def missing(folder,distribution,required,*,env=None,runner=None):
    required=list(required);suffix='.exe' if os.name=='nt' else ''
    tool=Path(folder)/(('findtexmf' if distribution=='miktex' else 'kpsewhich')+suffix)
    if not tool.is_file():raise ValueError('The selected installation is missing '+tool.name+'.')
    args=[str(tool),*(MIKTEX_READ_ONLY if distribution=='miktex' else []),*required]
    result=runner(args,timeout=30,env=env) if runner else subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=30,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    # Both tools return 1 when one or more requested files were not found.
    # An actual tool error must not masquerade as an absent package.
    if result.returncode not in (0,1) or (not result.stdout.strip() and result.stderr.strip()):
        raise ValueError('The TeX package lookup failed: '+(result.stdout+result.stderr)[-1500:])
    found={Path(line.strip().replace('\\','/')).name.casefold() for line in result.stdout.splitlines() if line.strip()}
    return [name for name in required if name.casefold() not in found]

def missing_requirements(folder,distribution,required,alternatives=(),*,env=None,runner=None):
    absent=set(missing(folder,distribution,sorted(set(required).union(*(set(group) for group in alternatives))),env=env,runner=runner))
    result=set(required)&absent
    for group in alternatives:
        if group and all(name in absent for name in group):result.add(group[0])
    return sorted(result)

def engine_source(text,engine):
    """Select known engine branches; retain both branches of unknown conditions."""
    text=re.sub(r'(?<!\\)%[^\n]*','',text)
    engines={'ifLuaTeX':'luatex','ifluatex':'luatex','ifPDFTeX':'pdftex','ifpdftex':'pdftex','ifXeTeX':'xetex','ifxetex':'xetex'}
    primitive=set('if ifx ifnum ifdim ifodd ifcase ifcat ifvmode ifhmode ifmmode ifinner ifvoid ifhbox ifvbox ifeof iftrue iffalse ifdefined ifcsname iffontchar'.split())
    custom=set(re.findall(r'\\newif\s*\\(if[A-Za-z@]+)',text));stack=[];parts=[];position=0;previous=''
    active=lambda:all(value is not False for value in stack)
    for match in re.finditer(r'\\([A-Za-z@]+|.)',text):
        command=match[1]
        if active():parts.append(text[position:match.start()])
        if previous!='newif' and (command in engines or command in primitive or command in custom):
            stack.append(engines[command]==engine if command in engines else None)
        elif command=='else' and stack:
            if stack[-1] is not None:stack[-1]=not stack[-1]
        elif command=='fi' and stack:stack.pop()
        elif active():parts.append(match[0])
        previous=command;position=match.end()
    if active():parts.append(text[position:])
    return ''.join(parts)

def _group(text,position):
    while position<len(text) and text[position].isspace():position+=1
    if position>=len(text) or text[position]!='{':return None
    start=position+1;depth=1;position=start
    while position<len(text):
        if text[position]=='\\' and position+1<len(text) and text[position+1] in '{}':position+=2;continue
        if text[position]=='{':depth+=1
        elif text[position]=='}':
            depth-=1
            if not depth:return text[start:position],position+1
        position+=1
    return None

def _packages(text):
    result=set()
    for names in re.findall(r'\\(?:RequirePackage|usepackage)(?:\[[^\]]*\])?\{([^{}]+)\}',text):
        result.update(name.strip()+'.sty' for name in names.split(',') if re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*',name.strip()))
    return result

def _font_files(text):
    """Read explicit file-based fontspec declarations, not system font names."""
    result=set()
    for family,options in re.findall(r'\\(?:setmainfont|setsansfont|setmonofont)\s*\{([^{}]+)\}\s*\[([^\]]*)\]',text):
        extension=re.search(r'(?:^|,)\s*Extension\s*=\s*(\.[A-Za-z0-9]+)',options)
        if not extension or not re.fullmatch(r'[A-Za-z0-9_. -]+',family):continue
        faces=re.findall(r'(?:^|,)\s*(?:UprightFont|ItalicFont|BoldFont|BoldItalicFont)\s*=\s*([^,\s{}]+)',options)
        for face in faces or [family]:
            if not re.fullmatch(r'[A-Za-z0-9_.*-]+',face):continue
            name=face.replace('*',family);result.add(name if name.lower().endswith(extension[1].lower()) else name+extension[1])
    return result

def dependencies(libraries,engine='luatex'):
    """Direct class/style requirements for one engine, including font alternatives.

    Explicit OpenType font files are checked too. Real test PDFs remain the
    authority for transitive dependencies and system font-name resolution.
    This intentionally does not try to evaluate arbitrary TeX conditionals.
    """
    sources=[p for library in libraries for p in Path(library).iterdir() if p.suffix in ('.sty','.cls')];owned={p.name for p in sources};required=set();alternatives=[]
    for source in sources:
        body=engine_source(source.read_text('utf-8',errors='replace'),engine);replacements=[]
        for match in re.finditer(r'\\IfFileExists\b',body):
            position=match.end();groups=[]
            for _ in range(3):
                group=_group(body,position)
                if group is None:break
                value,position=group;groups.append(value)
            if len(groups)!=3:continue
            yes,no=_packages(groups[1]),_packages(groups[2])
            # A common font fallback: use one installed package or the other.
            if len(yes)==len(no)==1 and yes!=no:
                alternatives.append([next(iter(yes)),next(iter(no))]);replacements.append((match.start(),position))
        for start,end in reversed(replacements):body=body[:start]+body[end:]
        required.update(_packages(body)-owned)
        required.update(_font_files(body))
        required.update(name+'.cls' for name in re.findall(r'\\LoadClass(?:\[[^\]]*\])?\{([A-Za-z][A-Za-z0-9-]*)\}',body) if name+'.cls' not in owned)
    return required,sorted({tuple(group) for group in alternatives})
