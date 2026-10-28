"""Plain JSON to TeX for local recommendation letters. No network access."""
import argparse
import json
from pathlib import Path
import re
import unicodedata

TEX = {'\\':r'\textbackslash{}','{':r'\{','}':r'\}','#':r'\#','$':r'\$',
       '%':r'\%','&':r'\&','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}',
       '\u2018':'`','\u2019':"'",'\u201c':'``','\u201d':"''",'\u2013':'--','\u2014':'---','\u00a0':' ',
       # Common PDF-extraction artifacts and typography. Map only selected
       # compatibility characters: broad NFKC would silently turn 10² into 102.
       '\ufb00':'ff','\ufb01':'fi','\ufb02':'fl','\ufb03':'ffi','\ufb04':'ffl','\ufb05':'st','\ufb06':'st',
       '\u2010':'-','\u2011':'-','\u2012':'--','\u2015':'---','\u2212':r'\ensuremath{-}',
       '\u2026':r'\ldots{}','\u2022':r'\textbullet{}',
       '\u25a1':r'\fbox{\rule{0pt}{0.5em}\rule{0.5em}{0pt}}',
       '\u2000':' ','\u2001':' ','\u2002':' ','\u2003':' ','\u2004':' ','\u2005':' ',
       '\u2006':' ','\u2007':' ','\u2008':' ','\u2009':' ','\u200a':' ','\u202f':' ',
       '\u00ad':'','\u200b':'','\ufeff':'',
       '\u2190':r'\ensuremath{\leftarrow}','\u2192':r'\ensuremath{\rightarrow}',
       '\u2194':r'\ensuremath{\leftrightarrow}'}

def escape(value):
    if not isinstance(value,str): raise ValueError('All text values must be strings')
    if any(ord(c)<32 and c not in '\n\r\t' for c in value): raise ValueError('Unsupported control character')
    # Compose supported Latin accents without altering mathematical characters,
    # names, or text in scripts that the configured TeX font may not support.
    value=unicodedata.normalize('NFC',value)
    return ''.join(TEX.get(c,c) for c in value).replace('\r','').replace('\n',r'\\ ')

def lines(values):
    if not isinstance(values,list) or any(not isinstance(x,str) for x in values):
        raise ValueError('Line fields must be arrays of strings')
    return r'\\ '.join(escape(x) for x in values)

def paragraph(value):
    """Reflow legacy extraction wraps inside one semantic body paragraph.

    Paragraph boundaries are already represented by the paragraphs array.
    Addresses, contact blocks, and closing lines still use explicit line fields.
    Only CR/LF are folded; other unsupported controls remain validation errors.
    """
    if not isinstance(value,str): raise ValueError('All text values must be strings')
    folded=' '.join(value.replace('\r\n','\n').replace('\r','\n').split('\n'))
    # Old Word/PDF separators can contain hundreds of underscores. Render their
    # intended line as a bounded rule rather than one unbreakable TeX word.
    def segment(part):
        if not re.fullmatch(r'_{8,}',part):return escape(part)
        if len(part)>=80:return r'\par\noindent\rule{\linewidth}{0.4pt}\par '
        return r'\allowbreak{}\rule{0.35\linewidth}{0.4pt}\allowbreak{}'
    return ''.join(segment(part)for part in re.split(r'(_{8,})',folded))

def require_local(path):
    path=Path(path).resolve()
    for parent in [path,*path.parents]:
        if (parent/'.git').exists() or parent.name.lower()=='mh-git':
            raise ValueError('Student inputs and generated files must be outside a Git checkout')
    return path

def asset(value,base,*,shared_signature=False):
    if not value: return None
    if not isinstance(value,str): raise ValueError('Asset paths must be strings')
    p=(Path(base)/value).resolve()
    # This author-owned asset is deliberately shared with other letter types.
    # Keep the exception exact: private letterheads and all student files stay local.
    canonical_signature=Path(__file__).resolve().parents[2]/'img'/'signature.png'
    if not (shared_signature and p==canonical_signature.resolve()):
        p=require_local(p)
    if any(c in str(p) for c in '{}%#\n\r'): raise ValueError('Unsupported character in asset path')
    if not p.is_file(): raise ValueError('Local asset does not exist: '+str(p))
    if p.suffix.lower() not in ('.png','.jpg','.jpeg','.pdf'):
        raise ValueError('Use a PNG, JPEG, or PDF asset')
    return r'\detokenize{'+p.as_posix()+'}'

def render(data,profile,base,final=False):
    if data.get('schema_version')!=1: raise ValueError('Expected schema_version 1')
    if not isinstance(data.get('paragraphs'),list) or not data['paragraphs']:
        raise ValueError('At least one paragraph is required')
    if any(not isinstance(p,str) or not p.strip() for p in data['paragraphs']):
        raise ValueError('Body paragraphs must be nonempty strings')
    for name in ('date','closing'):
        if not isinstance(data.get(name),str) or not data[name].strip(): raise ValueError('Missing '+name)
    sender=profile.get('sender',{})
    for name in ('name','title','department'):
        if not isinstance(sender.get(name),str) or not sender[name].strip(): raise ValueError('Missing sender '+name)
    layout=data.get('layout','standard')
    if layout not in ('standard','balanced','classic'): raise ValueError('Use standard, balanced or classic layout')
    salutation=data.get('salutation','Dear Members of the Selection Committee:')
    closing_lines=data.get('closing_lines',[sender['name'],sender['title']])
    out=[r'\documentclass{mhletter}',r'\usepackage['+layout+r',palatino]{mh-recommendation}',
         r'\LetterSender{'+escape(sender['name'])+'}{'+escape(sender['title'])+'}{'+escape(sender['department'])+'}',
         r'\LetterContact{'+lines(sender.get('contact_lines',[]))+'}',
         r'\LetterDate{'+escape(data['date'])+'}',
         r'\LetterRecipient{'+lines(data.get('recipient_lines',[]))+'}',
         r'\LetterSubject{'+escape(data.get('subject',''))+'}',
         r'\RecommendationSalutation{'+escape(salutation)+'}',
         r'\RecommendationRunningLabel{'+escape(data.get('running_label','Letter of recommendation'))+'}',
         r'\RecommendationClosing{'+escape(data['closing'])+'}',
         r'\RecommendationClosingLines{'+lines(closing_lines)+'}']
    if 'unit_lines' in profile:
        out.append(r'\LetterUnitLines{'+lines(profile['unit_lines'])+'}')
    if not final: out.append(r'\LetterStatus{DRAFT -- for author review}')
    # A signature is applied only on an explicit final build. Drafts stay unsigned.
    head=asset(profile.get('letterhead_file'),base)
    if head: out.append(r'\RecommendationLetterheadFile{'+head+'}')
    if final:
        sig=asset(profile.get('signature_file'),base,shared_signature=True)
        if sig: out.append(r'\LetterSignatureFile{'+sig+'}')
    out += [r'\begin{document}',r'\MakeRecommendationOpening']
    out += [paragraph(p)+'\n' for p in data['paragraphs']]
    out += [r'\MakeRecommendationClosing',r'\end{document}']
    return '\n'.join(out)+'\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('letter',type=Path)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--final',action='store_true',help='Remove draft label and use configured signature')
    args=parser.parse_args()
    try:
        source=require_local(args.letter); profile_path=require_local(args.profile); output=require_local(args.output)
        if output.exists(): raise ValueError('Output exists; choose a new revision filename')
        data=json.loads(source.read_text(encoding='utf-8-sig'))
        profile=json.loads(profile_path.read_text(encoding='utf-8-sig'))
        result=render(data,profile,profile_path.parent,args.final)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(result,encoding='utf-8')
        print('Created local TeX source: '+str(output))
    except (ValueError,OSError,KeyError) as exc: parser.exit(1,str(exc)+'\n')

if __name__=='__main__': main()
