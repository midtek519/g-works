"""Portable, locally generated TeX copies of question-bank selections."""
from pathlib import Path
import base64,hashlib,io,json,re,secrets

HEADER='% G-WHIZ QUESTION EXPORT 1'
MAX_BYTES=32*1024*1024
FORMATS={'free-response','multiple-choice','multiple-select','true-false','fill-in','mixed'}

def export_questions(library,payload):
    ids=payload.get('ids',[])
    if not isinstance(ids,list) or not 1<=len(ids)<=5000 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise ValueError('Choose between 1 and 5,000 questions to export.')
    keep_copy=payload.get('keep_copy',True)
    if not isinstance(keep_copy,bool):raise ValueError('Choose whether to keep a standard export copy.')
    include_solutions=payload.get('solutions',True) is not False
    chunks=[HEADER+'\n% Import this file through Question Bank > Import.\n% Questions, solutions and embedded figures stay together in this file.\n\n'];size=len(chunks[0].encode('utf-8'));assets={}
    def append(text):
        nonlocal size
        size+=len(text.encode('utf-8'))
        if size>MAX_BYTES:raise ValueError('This TeX export exceeds 32 MB. Export a smaller selection.')
        chunks.append(text)
    with library.desk.lock:
        cat=library._catalog()
        questions=[]
        for ident in ids:
            question=library._question(cat,ident);library._check_source(question);source=library._tex(question) if include_solutions else library._render_question({**question,'solution':''})
            questions.append((question,source))
            for asset in question.get('import_assets',[]):
                path=asset.get('path','')
                if not re.fullmatch(r'assets/imports/[a-f0-9]{64}\.(?:png|jpg|jpeg)',path):raise ValueError('An exported figure has an invalid path.')
                if '{'+path+'}' not in source:continue
                raw=library._inside(path).read_bytes();sha=hashlib.sha256(raw).hexdigest()
                if sha!=asset.get('sha256'):raise ValueError('An exported figure has changed. Restore it before exporting.')
                assets[path]=raw
        if len(assets)>2000:raise ValueError('Export at most 2,000 figures at a time.')
        for name,raw in assets.items():append('% GWHIZ-ASSET '+name+' '+base64.b64encode(raw).decode('ascii')+'\n')
        for question,source in questions:
            token=secrets.token_hex(16)
            meta={'source_id':question['id'],'question_format':question.get('question_format',question.get('metadata',{}).get('type','free-response')),'solution_status':question.get('solution_status','complete' if question.get('solution') else 'none'),'preamble':question.get('preamble','')}
            encoded=base64.b64encode(json.dumps(meta,ensure_ascii=False).encode('utf-8')).decode('ascii')
            if not include_solutions:
                meta['solution_status']='none'
                encoded=base64.b64encode(json.dumps(meta,ensure_ascii=False).encode('utf-8')).decode('ascii')
            append('\n% GWHIZ-BEGIN '+token+' '+encoded+'\n'+source.rstrip()+'\n% GWHIZ-END '+token+'\n')
    ident=secrets.token_hex(16);folder=Path(library.desk.root)/('Data/Exports/Questions' if keep_copy else 'Temp/PreviewCache/QuestionExports')/ident
    if not folder.resolve().is_relative_to(Path(library.desk.root).resolve()):raise ValueError('The export folder must remain inside this app.')
    folder.mkdir(parents=True,exist_ok=False);target=folder/'questions.tex';target.write_bytes(''.join(chunks).encode('utf-8'))
    return {'id':ident,'count':len(questions),'figures':len(assets),'url':'/api/universal/export/'+ident,'filename':'questions.tex','standard_copy':keep_copy}

def export_file(root,ident):
    if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a question export.')
    root=Path(root).resolve()
    for relative in ('Data/Exports/Questions','Temp/PreviewCache/QuestionExports'):
        path=root/relative/ident/'questions.tex'
        if not path.resolve().is_relative_to(root) or path.is_symlink():raise ValueError('The question export is unavailable.')
        if path.is_file():return path
    raise ValueError('The question export is unavailable. Export the questions again.')

def _mask_comments(text):
    lines=[]
    for line in text.splitlines(keepends=True):
        for i,char in enumerate(line):
            if char!='%':continue
            j=i-1
            while j>=0 and line[j]=='\\':j-=1
            if (i-j-1)%2==0:
                content=line.rstrip('\r\n');line=line[:i]+' '*(len(content)-i)+line[len(content):];break
        lines.append(line)
    return ''.join(lines)

def parse_export(source):
    source=source.replace('\r\n','\n').replace('\r','\n')
    if not source.lstrip('\ufeff').startswith('% G-WHIZ QUESTION EXPORT'):return None
    if not source.lstrip('\ufeff').startswith(HEADER+'\n'):raise ValueError('This question export format is unsupported.')
    if len(source.encode('utf-8'))>MAX_BYTES:raise ValueError('The question export exceeds 32 MB.')
    from question_import import environment_blocks,group_at,macro_definitions,expand_macros
    images=[]
    for match in re.finditer(r'^% GWHIZ-ASSET (assets/imports/([a-f0-9]{64})\.(png|jpg|jpeg)) ([A-Za-z0-9+/=]+)$',source,re.M):
        raw=base64.b64decode(match[4],validate=True)
        if hashlib.sha256(raw).hexdigest()!=match[2]:raise ValueError('An embedded figure checksum is invalid.')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>60000000 or image.format not in ('PNG','JPEG'):raise ValueError('An embedded figure is unsupported or too large.')
            image.verify()
        images.append({'name':Path(match[1]).name,'path':match[1],'sha256':match[2],'extension':'.'+match[3],'bytes':raw})
        if len(images)>2000:raise ValueError('Import at most 2,000 embedded figures at a time.')
    records=list(re.finditer(r'^% GWHIZ-BEGIN ([a-f0-9]{32}) ([A-Za-z0-9+/=]+)\n(.*?)^% GWHIZ-END \1\s*$',source,re.M|re.S))
    if not 1<=len(records)<=5000 or len(re.findall(r'^% GWHIZ-BEGIN ',source,re.M))!=len(records):raise ValueError('A question export section is incomplete or too large.')
    result=[];warnings=[]
    for match in records:
        meta=json.loads(base64.b64decode(match[2],validate=True));text=match[3]
        if not isinstance(meta,dict) or meta.get('question_format') not in FORMATS:raise ValueError('An exported question has an invalid response format.')
        masked=_mask_comments(text);blocks=environment_blocks(masked,{'exercise'});solutions=environment_blocks(masked,{'solution'})
        if len(blocks)!=1:raise ValueError('Each exported question must contain one exercise.')
        block=blocks[0];body=text[block[2]:block[3]];_,end=group_at(body,0,'[',']');body=body[end:] if end else body
        preamble=meta.get('preamble','')
        if not isinstance(preamble,str) or len(preamble)>100000:raise ValueError('The exported question preamble is invalid.')
        definitions,notes=macro_definitions(preamble+'\n'+masked[:block[0]]);warnings.extend(notes)
        question=expand_macros(body.strip(),definitions);solution=expand_macros('\n\n'.join(text[s[2]:s[3]].strip() for s in solutions),definitions)
        if max(len(question),len(solution))>100000:raise ValueError('Keep each question and solution under 100,000 characters.')
        result.append({'label':str(meta.get('source_id','Question'))[:120],'question':question,'solution':solution,'question_format':meta['question_format'],'solution_status':meta.get('solution_status','complete' if solution else 'none'),'points':None,'original':text.strip(),'pages':[],'needs_figure':False,'warnings':[],'portable_export':True})
    result[0]['embedded_assets']=images
    return result,warnings
