"""Bounded academic TeX snapshots. Never execute TeX or follow arbitrary includes."""
from pathlib import Path
import re

INPUT=re.compile(r'\\input\s*\{([^{}]+)\}')
MISSING='Linked TeX needs temporary question files that are no longer available. Rebuild the handout in Materials, then replace its linked solutions file.'

def snapshot_tex(raw,app_root,*,managed=False):
    from materials_links import safe_file,read_bounded,MAX_TEX
    text=raw.decode('utf-8-sig',errors='strict');matches=list(INPUT.finditer(text))
    if not matches:return raw
    if not managed:raise ValueError('Link a self-contained solutions TeX file, or choose a saved Handout Build.')
    if len(matches)>100:raise ValueError('The TeX source has too many question files.')
    root=Path(app_root)/'Temp/Drafts';parts=[];pos=0;seen=set();total=len(raw)
    for match in matches:
        path=Path(match[1]);relative=None
        # Earlier installations used absolute cache prefixes. Only the exact
        # validated cache suffix below is remapped into the current app root.
        if not path.is_relative_to(root) and path.is_absolute():
            for i in range(len(path.parts)-1):
                if path.parts[i:i+2]==('Temp','Drafts'):
                    suffix=Path(*path.parts[i+2:])
                    if re.fullmatch(r'universal-[a-f0-9]{16}/\d{1,3}/\d{3}-Q\d{6,12}\.tex',suffix.as_posix()):path=root/suffix
                    break
        try:relative=path.relative_to(root).as_posix()
        except ValueError:pass
        if relative is None or not re.fullmatch(r'universal-[a-f0-9]{16}/\d{1,3}/\d{3}-Q\d{6,12}\.tex',relative):raise ValueError('The TeX source contains an unsupported file reference. Use self-contained solutions TeX.')
        if relative in seen:raise ValueError('Repeated question input is ambiguous; use self-contained solutions TeX.')
        seen.add(relative)
        try:child=read_bounded(safe_file(path,[root],{'.tex'}),60000)
        except (OSError,ValueError):raise ValueError(MISSING) from None
        body=child.decode('utf-8-sig',errors='strict')
        if INPUT.search(body):raise ValueError('A question contains nested TeX inputs. Link self-contained solutions TeX.')
        total+=len(child)
        if total>MAX_TEX:raise ValueError('The linked solutions source exceeds the supported size.')
        parts.extend((text[pos:match.start()],'\n',body,'\n'));pos=match.end()
    parts.append(text[pos:]);return ''.join(parts).encode('utf-8')
