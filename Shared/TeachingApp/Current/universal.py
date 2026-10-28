"""Universal question library and revision-pinned assignment builder.

All sources, revisions, manifests, and compilation stay on this computer.
"""
from pathlib import Path
from copy import deepcopy
import hashlib,json,math,re,secrets,os
from core import CODES,escape,hash_file,save,stamp,term,tex_input,replace_file

from toolchain import question_bank_path
from taxonomy_model import all_questions, course_copy, validate_classifications, set_classifications, header_title, fresh_question_id

KINDS={'manual','worksheet','quiz','exam'}

QUESTION_FORMATS={'free-response','multiple-choice','multiple-select','true-false','fill-in','mixed'}

def question_properties(q,payload):
    """Validate builder-owned properties without trusting arbitrary metadata."""
    for label in ('question','solution'):
        body=q.get(label,'')
        if re.search(r'\\(?:begin|end)\s*\{(?:exercise|solution|document)\}|\\documentclass\b',uncomment(body)):
            raise ValueError('Enter only the '+label+' content in LaTeX. The app supplies the exercise and solution environments and document setup.')
    fmt=payload.get('question_format',q.get('metadata',{}).get('type') or 'free-response')
    if fmt not in QUESTION_FORMATS:raise ValueError('Choose a valid question format.')
    q.setdefault('metadata',{})['type']=fmt
    status=payload.get('solution_status',q.get('solution_status'))
    if status is not None and status not in ('none','incomplete','complete'):
        raise ValueError('Choose None, Incomplete, or Complete for solution status.')
    if not q.get('solution','').strip():status='none'
    elif not status or status=='none':
        status='incomplete' if re.search(r'solution pending',q['solution'],re.I) else 'complete'
    q['solution_status']=status


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def plain(value,label,maximum=300):
    if not isinstance(value,str) or len(value)>maximum or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise ValueError('Check '+label+'.')
    return value.strip()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def metadata_text(value,label,maximum=300):
    value=plain(value,label,maximum)
    tex_input(value)
    level=0;math_mode=False;result=[];i=0
    while i<len(value):
        c=value[i]
        if c=='\\' and i+1<len(value):
            result.append(value[i:i+2]);i+=2;continue
        if c=='{':level+=1
        if c=='}':
            level-=1
            if level<0:raise ValueError('Check the matching braces in '+label+'.')
        if c=='$':math_mode=not math_mode
        if c in '%&#' or (c=='_' and not math_mode):result.append('\\'+c)
        else:result.append(c)
        i+=1
    if level:raise ValueError('Check the matching braces in '+label+'.')
    if math_mode:raise ValueError('Close the math expression in '+label+' with a second dollar sign.')
    return ''.join(result)

def uncomment(text):
    result=[];i=0
    while i<len(text):
        if text[i]=='\\' and i+1<len(text):
            result.append(text[i:i+2]);i+=2;continue
        if text[i]=='%':
            end=text.find('\n',i)
            if end<0:break
            result.append('\n');i=end+1;continue
        result.append(text[i]);i+=1
    return ''.join(result)

def workspace_slots(text):
    source=uncomment(text)
    control=re.compile(r'\\([A-Za-z@]+|.|$)',re.S)

    def whitespace(pos):
        while pos<len(source) and source[pos].isspace():pos+=1
        return pos

    def group_end(pos):
        # A control-symbol token such as \{ or \\ consumes both characters.
        # Checking just the preceding slash mishandles braces after \\.
        opening=source[pos];closing='}' if opening=='{' else ']';depth=1;pos+=1
        while pos<len(source):
            if source[pos]=='\\':pos=control.match(source,pos).end();continue
            if opening=='[' and source[pos]=='{':pos=group_end(pos);continue
            if source[pos]==opening:depth+=1
            elif source[pos]==closing:
                depth-=1
                if not depth:return pos+1
            pos+=1
        return len(source)

    def argument_end(pos):
        pos=whitespace(pos)
        if pos>=len(source):return pos
        if source[pos]=='{':return group_end(pos)
        if source[pos]=='\\':return control.match(source,pos).end()
        return pos+1

    def arguments_end(pos,count):
        for _ in range(count):pos=argument_end(pos)
        return pos

    def skip_options(pos):
        pos=whitespace(pos)
        while pos<len(source) and source[pos]=='[':pos=whitespace(group_end(pos))
        return pos

    def foreach_end(pos):
        # PGF syntax: \foreach \x[/\y] [options] in {values} [options] {body}.
        # The value list is the first brace group, not the repeated body.
        while pos<len(source):
            pos=whitespace(pos)
            if pos>=len(source):return pos
            if source[pos] in '{[':pos=group_end(pos);continue
            if source[pos]=='\\':pos=control.match(source,pos).end();continue
            word=re.match(r'[A-Za-z]+',source[pos:])
            if word and word[0]=='in':
                pos=skip_options(argument_end(pos+2))
                if pos<len(source) and source[pos]=='{':return group_end(pos)
                token=control.match(source,pos)
                # An unbraced TikZ path body ends at its top-level semicolon.
                if token and token[1] in ('draw','path','fill','filldraw','node','coordinate','shade','shadedraw','clip'):
                    end=token.end()
                    while end<len(source):
                        if source[end]=='\\':end=control.match(source,end).end();continue
                        if source[end] in '{[':end=group_end(end);continue
                        if source[end]==';':return end+1
                        end+=1
                    return end
                end=argument_end(pos)
                # A single unbraced macro may itself have grouped arguments.
                while whitespace(end)<len(source) and source[whitespace(end)]=='{':end=group_end(whitespace(end))
                return end
            pos+=len(word[0]) if word else 1
        return pos

    # These macros take a test followed by one/two branches, or a loop body.
    # Explicit arities keep an ordinary group *after* an if-T macro outside it.
    arities={'vary':1,'ifthenelse':3,'whiledo':2,'multido':3,
        'pgfplotsinvokeforeach':2,'ForEachUsedExerciseByID':1,
        'IfFileExists':3,'IfFormatAtLeastTF':3,'IfPackageLoadedTF':3,
        'IfClassLoadedTF':3,'IfPackageAtLeastTF':4,'IfClassAtLeastTF':4,
        'IfDocumentMetadataTF':2,'IfExercisePropertySetTF':3,
        'IfExercisePropertyValueTF':4,'IfExerciseTypeTF':3,
        'GetExercisePropertyT':2,'ifboolexpr':3,'ifnumcomp':5,'ifdimcomp':5,
        'ifnumequal':4,'ifdimequal':4,'ifstrequal':4,'ifdefequal':4,
        'ifstrempty':3,'ifblank':3,'ifdef':3,'ifundef':3,'ifcsdef':3,
        'ifcsundef':3,'ifbool':3,'iftoggle':3,'ifdefstring':4,'ifcsstring':4,
        'ifcsempty':3,'ifcsvoid':3,'ifdefempty':3,'ifdefvoid':3,
        '@ifundefined':3,'@ifnextchar':3}
    for family in ('Document','Manual','Assessment','Exam','Worksheet','Student','Solutions','Developer','Accessible','QuestionWorkspace','WorksheetWorkspace'):
        for suffix,count in (('T',1),('F',1),('TF',2)):arities['IfMath'+family+suffix]=count
    for family in ('Boolean','NoValue','Value'):
        for suffix,count in (('T',2),('F',2),('TF',3)):arities['If'+family+suffix]=count

    commands=list(control.finditer(source));conditional_ranges=[];definition_ranges=[]
    for m in commands:
        name=m[1];end=None
        if name in arities:end=arguments_end(m.end(),arities[name])
        elif name in ('foreach','pgfplotsforeachungrouped'):end=foreach_end(m.end())
        elif name in ('newcommand','renewcommand','providecommand','DeclareRobustCommand'):
            pos=whitespace(m.end())
            if pos<len(source) and source[pos]=='*':pos+=1
            end=argument_end(skip_options(argument_end(pos)));definition_ranges.append((m.end(),end))
        elif name in ('NewDocumentCommand','RenewDocumentCommand','ProvideDocumentCommand','DeclareDocumentCommand'):
            end=arguments_end(m.end(),3);definition_ranges.append((m.end(),end))
        elif name in ('def','gdef','edef','xdef'):
            pos=argument_end(m.end())
            while pos<len(source) and source[pos]!='{':
                pos=control.match(source,pos).end() if source[pos]=='\\' else pos+1
            end=group_end(pos) if pos<len(source) else pos;definition_ranges.append((m.end(),end))
        if end is not None:conditional_ranges.append((m.end(),end))

    def within(pos,ranges):return any(start<=pos<end for start,end in ranges)

    # Primitive/custom \if...\else...\fi and plain-TeX \loop...\repeat
    # have no brace arguments. A loop's final test is closed by \repeat.
    conditional_depth=0;loops=[];newif_target=None;slots=[]
    for m in commands:
        name=m[1]
        if within(m.start(),definition_ranges):continue
        if name=='newif':newif_target=whitespace(m.end());continue
        if m.start()==newif_target:newif_target=None;continue
        if name=='loop':loops.append(conditional_depth)
        elif name=='repeat' and loops:conditional_depth=loops.pop()
        # \iff is a relation and mh's \ifm prints "if" in a cases row.
        elif name.startswith('if') and name not in arities and name not in ('iff','ifm'):conditional_depth+=1
        elif name=='fi':conditional_depth=max(0,conditional_depth-1)
        elif name=='WorkspaceHere':
            if conditional_depth or loops or within(m.start(),conditional_ranges):
                raise ValueError('Keep workspace positions outside version choices, conditional branches, loops, and command definitions.')
            slots.append({'index':len(slots)+1,'weight':1,'context':re.sub(r'\s+',' ',source[max(0,m.start()-100):m.start()])})
    # Definition bodies were skipped above because their primitive tests do not
    # execute at declaration time. A marker there is still an unstable slot.
    if any(m[1]=='WorkspaceHere' and within(m.start(),definition_ranges) for m in commands):
        raise ValueError('Keep workspace positions outside command definitions; place them directly in the question.')
    return slots

def integer(value,label,low,high):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
        raise ValueError(label+' must be between '+str(low)+' and '+str(high)+'.')
    return value

def number(value,label,low=0,high=10000):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('Enter a valid '+label+'.')
    return value

def manual_topic_inventory(cat):
    """Describe imported placement without changing it or choosing primary topics."""
    report={}
    for code,manual in cat.get('manuals',{}).items():
        questions=[q for q in cat.get('questions',[]) if 'manual' in q.get('suitability',{}).get(code,[])]
        chapters={c['id']:c for c in manual.get('chapters',[])}
        by_chapter={cid:set() for cid in chapters};by_topic={}
        for q in questions:
            chapter=q.get('manual',{}).get(code,{}).get('chapter')
            if chapter not in chapters:continue
            for topic in q.get('topics',[]):
                by_chapter[chapter].add(topic);by_topic.setdefault(topic,set()).add(chapter)
        report[code]={
            'question_count':len(questions),
            'missing_placement':[q['id'] for q in questions if q.get('manual',{}).get(code,{}).get('chapter') not in chapters],
            'multi_topic_questions':[q['id'] for q in questions if len(q.get('topics',[]))>1],
            'chapters':[{'id':c['id'],'title':c['title'],'topics':sorted(by_chapter[c['id']])} for c in chapters.values()],
            'topics_in_multiple_chapters':{t:sorted(ids) for t,ids in by_topic.items() if len(ids)>1},
            'unambiguous_links':{t:next(iter(ids)) for t,ids in by_topic.items() if len(ids)==1 and by_chapter[next(iter(ids))]=={t}}
        }
    return report

def topic_course_label(cat,topic,code,inventory=None):
    """Return an explicit link or a safe inferred link; catalog reads stay read-only."""
    label=deepcopy(topic.get('course_labels',{}).get(code,{}))
    section=next((x for x in cat.get('manuals',{}).get(code,{}).get('sections',[]) if x['id']==label.get('section_id')),None)
    if section:
        label.update(chapter_id=section['chapter'],chapter_title=section['title'],chapter_order=section['order'],chapter_link_status='linked')
        return label
    chapters=cat.get('manuals',{}).get(code,{}).get('chapters',[])
    chapter=next((c for c in chapters if c['id']==label.get('chapter_id') and c.get('topic_id',topic['id'])==topic['id']),None)
    inferred=False
    if not chapter:
        inventory=inventory if inventory is not None else manual_topic_inventory(cat)
        ident=inventory.get(code,{}).get('unambiguous_links',{}).get(topic['id'])
        chapter=next((c for c in chapters if c['id']==ident and c.get('topic_id',topic['id'])==topic['id']),None)
        inferred=chapter is not None
    if chapter:
        label.update(chapter_id=chapter['id'],chapter_title=chapter['title'],chapter_order=chapter.get('order',1),chapter_link_status='inferred' if inferred else 'linked')
    else:
        label.pop('chapter_id',None);label.pop('chapter_title',None);label.pop('chapter_order',None)
        label['chapter_link_status']='unlinked'
    return label

class Universal:
    def __init__(self,desk):
        self.desk=desk
        self.base=question_bank_path(desk.root,desk.repo)
        self.catalog_path=self.base/'catalog.json'
        self.assignments_path=self.base/'assignments'

    def available(self):return self.catalog_path.is_file()

    def _catalog(self):
        staged=getattr(self,'_staged_write',None)
        if staged is not None:return staged['catalog']
        if not self.available():raise ValueError('The universal question library is being prepared. Existing materials are still available under Courses.')
        cat=read_json(self.catalog_path)
        cat.setdefault('manuals',{})
        cat.setdefault('topics',[])
        cat.setdefault('objectives',[])
        cat.setdefault('taxonomy_revision',digest({k:cat.get(k) for k in ['topics','objectives','manuals']}))
        return cat

    def _inside(self,relative):
        p=(self.base/relative).resolve()
        if not p.is_relative_to(self.base.resolve()):raise ValueError('Invalid question file.')
        for part in [p,*p.parents]:
            if part==self.base.resolve():break
            if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Question files must stay in the library.')
        return p

    def _editable(self):
        if self.desk.active:raise ValueError('Let the current compilation finish before editing the library.')

    def _question(self,cat,ident):
        q=next((q for q in all_questions(cat) if q['id']==ident),None)
        if not q:raise ValueError('Choose a question from the universal bank.')
        return q

    def _question_revision(self,cat,ident,revision=None):
        q=next((q for q in all_questions(cat) if q['id']==ident),None)
        if q is None and (not revision or not re.fullmatch(r'Q\d{6,}',str(ident))):raise ValueError('Choose an available bank question or its saved handout revision.')
        if q is not None and (not revision or q['revision']==revision):
            self._check_source(q)
            return deepcopy(q)
        if not re.fullmatch('[a-f0-9]{64}',str(revision)):raise ValueError('Choose a valid saved question revision.')
        p=self.base/'revisions'/ident/(revision+'.json')
        if not p.is_file():raise ValueError('A saved question revision is unavailable: '+ident+'.')
        result=read_json(p)
        if result.get('id')!=ident or result.get('revision')!=revision:raise ValueError('A saved question revision does not match its record.')
        return result

    def _check_source(self,q):
        path=self._inside(q.get('file','questions/'+q['id']+'.tex'))
        expected=q.get('tex')
        staged=getattr(self,'_staged_write',None)
        if staged is not None and path in staged['changes']:
            if expected is not None and staged['changes'][path]!=expected:raise ValueError('The staged question source changed.')
            return
        if expected is None:
            revision_file=self.base/'revisions'/q['id']/(q['revision']+'.tex')
            expected=revision_file.read_text(encoding='utf8') if revision_file.is_file() else None
        if not path.is_file() or (expected is not None and path.read_text(encoding='utf8')!=expected):
            raise ValueError(q['id']+' changed outside the app. Review or restore its question file before editing or compiling the current revision. Saved assignment revisions remain preserved.')

    def _tex(self,q):
        if 'tex' in q:return q['tex']
        if 'classifications' in q:return self._render_question(q)
        path=self.base/'revisions'/q['id']/(q['revision']+'.tex')
        if path.is_file():return path.read_text(encoding='utf8')
        return self._inside(q.get('file','questions/'+q['id']+'.tex')).read_text(encoding='utf8')

    def _remember(self,q,tex=None):
        folder=self.base/'revisions'/q['id'];snapshot=deepcopy(q);snapshot['tex']=tex if tex is not None else self._tex(q)
        p=folder/(q['revision']+'.json');target=folder/(q['revision']+'.tex');staged=getattr(self,'_staged_write',None)
        previous=read_json(p) if p.exists() else json.loads(staged['changes'][p]) if staged is not None and p in staged['changes'] else None
        if previous is not None and previous.get('tex')!=snapshot['tex']:raise ValueError('A saved revision has changed unexpectedly: '+q['id'])
        if staged is not None:
            if previous is None:staged['changes'][p]=json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n'
            if not target.exists():staged['changes'][target]=snapshot['tex']
            return
        folder.mkdir(parents=True,exist_ok=True)
        if previous is None:save(p,snapshot)
        if not target.exists():target.write_text(snapshot['tex'],encoding='utf8')

    def catalog(self):
        with self.desk.lock:
            cat=self._catalog();result=deepcopy(cat)
            # Deleted duplicate records remain only for immutable historical uses.
            result.pop('merged_questions',None)
            result['topics']=[t for t in cat['topics'] if not t.get('retired')]
            result['objectives']=[o for o in cat['objectives'] if not o.get('retired')]
            inventory=manual_topic_inventory(cat)
            result['topics']=deepcopy(result['topics'])
            for topic in result['topics']:
                topic['course_labels']={code:topic_course_label(cat,topic,code,inventory) for code in topic.get('course_labels',{})}
            result['manual_topic_review']=inventory
            for q in all_questions(result):
                q.setdefault('excerpt',re.sub(r'\s+',' ',q.get('question',''))[:180])
                q.setdefault('workspace_slots',[])
                q['manual_placement_warnings']=self._placement_warnings(cat,q,inventory)
                q.pop('tex',None)
            result['assignments']=self.assignments()
            result['bank_revision']=self._bank_revision(cat)
            usage={}
            for assignment in result['assignments']:
                for item in assignment.get('questions',[]):
                    usage.setdefault(item['id'],[]).append({'id':assignment['id'],'title':assignment.get('title',''),'course':assignment.get('course',''),'semester':assignment.get('semester','')})
            result['bank_usage']=usage
            return result

    def assignments(self):
        return sorted([read_json(p) for p in self.assignments_path.glob('*.json')],key=lambda a:(a.get('updated',''),a.get('title','')),reverse=True)

    def assignment(self,ident):
        if not re.fullmatch('A[a-f0-9]{16}',str(ident)):raise ValueError('Choose a saved assignment.')
        p=self.assignments_path/(ident+'.json')
        if not p.is_file():raise ValueError('The saved assignment was not found.')
        return read_json(p)

    def _write_catalog(self,cat,changes=None,reason='Universal library edited'):
        staged=getattr(self,'_staged_write',None)
        if staged is not None:
            staged['catalog']=cat;staged['changes'].update(changes or {});return
        paths={self.catalog_path:self.catalog_path.read_bytes()}
        changes=changes or {}
        for p in changes:
            if p.is_file():paths[p]=p.read_bytes()
        self.desk._history(paths,reason)
        originals={p:p.read_bytes() if p.exists() else None for p in [*changes,self.catalog_path]}
        try:
            for p,data in changes.items():
                p.parent.mkdir(parents=True,exist_ok=True);
                if data is None:p.unlink(missing_ok=True);continue
                tmp=p.with_suffix(p.suffix+'.partial');tmp.write_bytes(data) if isinstance(data,bytes) else tmp.write_text(data,encoding='utf8');replace_file(tmp,p)
            cat['updated']=stamp();save(self.catalog_path,cat)
        except Exception:
            for p,data in originals.items():
                if data is None:p.unlink(missing_ok=True)
                else:p.write_bytes(data)
            raise

    def _suitability(self,value,none=False):
        if not isinstance(value,dict):raise ValueError('Choose course and use combinations, or None.')
        if none:
            if any(value.values()):raise ValueError('None cannot be combined with another suitability.')
            return {}
        result={}
        for code,kinds in value.items():
            if code not in getattr(self.desk,'modules',CODES) or code=='136' or not isinstance(kinds,list) or any(k not in KINDS for k in kinds):raise ValueError('Choose valid course and use combinations.')
            if kinds:result[code]=[k for k in ['manual','worksheet','quiz','exam'] if k in kinds]
        if not result:raise ValueError('Choose at least one course and suitable use.')
        return result

    def _refs(self,cat,name,values):
        if not isinstance(values,list) or len(values)>30:raise ValueError('Select valid '+name+'.')
        available={r['id'] for r in cat[name] if not r.get('retired')}
        if any(v not in available for v in values):raise ValueError('A selected '+name[:-1]+' is no longer available. Refresh the library.')
        return list(dict.fromkeys(values))

    def _topic_chapters(self,cat,q,code,inventory=None):
        chapters={}
        for topic in cat['topics']:
            if topic['id'] not in q.get('topics',[]) or topic.get('retired') or code not in topic.get('course_labels',{}):continue
            label=topic_course_label(cat,topic,code,inventory)
            if label.get('chapter_id'):chapters[label['chapter_id']]=topic['id']
        return chapters

    def _placement_warnings(self,cat,q,inventory=None):
        warnings=[]
        for code,uses in q.get('suitability',{}).items():
            if 'manual' not in uses:continue
            placement=q.get('manual',{}).get(code,{})
            if placement.get('chapter') in {c['id'] for c in cat.get('manuals',{}).get(code,{}).get('chapters',[])}:continue
            choices=self._topic_chapters(cat,q,code,inventory)
            if len(choices)>1:message='Choose the primary manual chapter because the selected topics lead to different chapters.'
            else:message='Set a chapter for this course topic in Topics & Objectives, or choose a manual chapter.'
            warnings.append({'course':code,'message':message})
        return warnings

    def _auto_manual_placements(self,cat,q,inventory=None):
        inventory=inventory if inventory is not None else manual_topic_inventory(cat)
        for code,uses in q['suitability'].items():
            if 'manual' not in uses or q['manual'].get(code,{}).get('chapter'):continue
            choices=self._topic_chapters(cat,q,code,inventory)
            if len(choices)!=1:continue
            chapter=next(iter(choices))
            topic=next(t for t in cat['topics'] if t['id']==choices[chapter])
            label=topic_course_label(cat,topic,code,inventory)
            section=next((sec for sec in cat.get('manuals',{}).get(code,{}).get('sections',[]) if sec['id']==label.get('section_id')),None)
            orders=[p.get('manual',{}).get(code,{}).get('order',0) for p in cat['questions'] if p['id']!=q['id'] and p.get('manual',{}).get(code,{}).get('chapter')==chapter]
            q['manual'][code]={'chapter':chapter,'section':section['id'] if section else '','section_order':section.get('order',0) if section else 0,'order':min(max(orders or [0])+1,100000),'topic_id':choices[chapter]}

    def _render_question(self,q):
        meta=dict(q.get('metadata',{}))
        meta.pop('points',None);meta.pop('workspace',None);meta.pop('workspace-top',None)
        meta.update(ID=q['id'],topics=','.join(q['topics']),objectives=','.join(q['objectives']))
        options=','.join(k if v is True else k+'={'+str(v)+'}' for k,v in meta.items() if v not in ('',None,False))
        return (q.get('prefix','')+'\n\\begin{exercise}['+options+']\n'+re.sub(r'\A(?:[ \t]*\r?\n)+','',q['question'])+'\n\\end{exercise}\n'+q.get('solution_bridge',q.get('bridge',''))+
                ('\n\\begin{solution}\n'+q['solution']+'\n\\end{solution}\n' if q['solution'] else '')+q.get('suffix',''))

    def save_question(self,payload):
        with self.desk.lock:
            self._editable();cat=self._catalog();ident=payload.get('id')
            if ident:
                old=self._question(cat,ident)
                if old.get('merged_into'):raise ValueError('This duplicate was removed. Edit its original question '+old['merged_into']+' instead.')
                if old.get('bank_trash'):raise ValueError('Restore this question from Trash before editing it.')
                if old.get('pending_classification'):raise ValueError('Approve this Math 135 classification before editing the original question. You can copy it as a new question.')
                self._check_source(old)
                if old.get('archived'):raise ValueError('Copy an archived question before returning it to the active bank.')
                if payload.get('confirmed') is not True:raise ValueError('Enable editing and confirm the question change.')
                if payload.get('expected_revision')!=old['revision']:raise ValueError('This question changed. Refresh before editing it.')
                self._remember(old);q=deepcopy(old)
            else:
                ident=fresh_question_id(cat)
                q={'id':ident,'legacy_id':'','source':{'course':'','collection':'created','path':''},'metadata':{'status':'draft'},'prefix':'','bridge':'','suffix':'','manual':{},'dependencies':[],'created':stamp()}
                if payload.get('copy_from_id'):
                    original=self._question(cat,payload['copy_from_id']);self._check_source(original)
                    if payload.get('copy_from_revision')!=original['revision']:raise ValueError('The source question changed. Open it again before saving a copy.')
                    for field in ('prefix','preamble','solution_bridge','bridge','suffix','metadata','dependencies','import_assets','import_provenance'):
                        if field in original:q[field]=deepcopy(original[field])
                    q['copied_from']={'id':original['id'],'revision':original['revision']}
            if not payload.get('id') and isinstance(payload.get('import_provenance'),dict):q['import_provenance']=deepcopy(payload['import_provenance'])
            if not payload.get('id') and payload.get('import_assets'):
                assets=payload['import_assets']
                if not isinstance(assets,list) or len(assets)>30:raise ValueError('Choose up to 30 imported images for a question.')
                q['import_assets']=[]
                for asset in assets:
                    if not isinstance(asset,dict) or not re.fullmatch(r'assets/imports/[a-f0-9]{64}\.(?:png|jpg|jpeg)',asset.get('path','')) or not re.fullmatch('[a-f0-9]{64}',asset.get('sha256','')):raise ValueError('Choose a valid library image.')
                    path=self._inside(asset['path']);staged=getattr(self,'_staged_write',None);data=staged['changes'].get(path) if staged else None
                    if data is None:data=path.read_bytes() if path.is_file() else None
                    if not isinstance(data,bytes) or hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('An imported image is missing or changed.')
                    q['import_assets'].append({'path':asset['path'],'sha256':asset['sha256']})
            q['question']=tex_input(payload.get('question',''));q['solution']=tex_input(payload.get('solution',''))
            if not q['question']:raise ValueError('Enter the question.')
            question_properties(q,payload)
            scoring_source=uncomment(q['question'])
            if re.search(r'\\part\s*\[[^\]]+\]|\\(?:AssessmentAddPoints|AssessmentPartPointBox|AssessmentExercisePointBox|marpoints)\b',scoring_source):raise ValueError('Assign points to the whole question in the assignment builder. Remove part point values and scoring commands from this question.')
            q['suitability']=self._suitability(payload.get('suitability',{}),payload.get('suitability_none') is True)
            q['suitability_none']=not bool(q['suitability'])
            previous_classes=deepcopy(q.get('classifications',{}))
            set_classifications(q,validate_classifications(cat,payload,q['suitability']))
            for code,entry in q['classifications'].items():
                if entry.get('topic')!=previous_classes.get(code,{}).get('topic'):q.get('manual',{}).pop(code,None)
            placements=deepcopy(payload.get('manual',q.get('manual',{})))
            for code,entry in q['classifications'].items():
                if entry.get('topic')!=previous_classes.get(code,{}).get('topic'):placements.pop(code,None)
            if not isinstance(placements,dict):raise ValueError('Choose valid manual placements.')
            q['manual']={}
            for code,placement in placements.items():
                if code not in q['suitability'] or 'manual' not in q['suitability'][code]:continue
                if not isinstance(placement,dict):raise ValueError('Choose a manual chapter.')
                chapter=placement.get('chapter','');chapters=cat.get('manuals',{}).get(code,{}).get('chapters',[])
                if chapter and chapter not in {c['id'] for c in chapters}:raise ValueError('Choose an existing manual chapter.')
                chapter_record=next((c for c in chapters if c['id']==chapter),{})
                if chapter_record.get('topic_id') and chapter_record['topic_id']!=q.get('classifications',{}).get(code,{}).get('topic'):raise ValueError('Choose a manual chapter that matches one of the question topics.')
                section=plain(placement.get('section',''),'section');sections=cat.get('manuals',{}).get(code,{}).get('sections',[])
                section_record=next((s for s in sections if s['id']==section),None)
                if section_record and section_record.get('chapter')!=chapter:raise ValueError('Choose a section within the selected chapter.')
                q['manual'][code]={'chapter':chapter,'section':section,'section_order':section_record.get('order',9999) if section_record else (9999 if section else 0),'order':number(placement.get('order',9999),'manual order',0,100000)}
                manual_topic=chapter_record.get('topic_id') or placement.get('topic_id')
                if manual_topic in q['topics']:q['manual'][code]['topic_id']=manual_topic
            self._auto_manual_placements(cat,q)
            q['workspace_slots']=workspace_slots(q['question'])
            q['excerpt']=re.sub(r'\s+',' ',q['question'])[:180];q['updated']=stamp();q['file']='questions/'+ident+'.tex'
            q.pop('tex',None);q.pop('revision',None)
            text=self._render_question(q);q['tex']=text;q['revision']=digest(q)
            self._remember(q,text)
            cat['questions']=[q if p['id']==ident else p for p in cat['questions']] if payload.get('id') else cat['questions']+[q]
            self._write_catalog(cat,{self.base/q['file']:text},'Question '+ident+' revised' if payload.get('id') else 'Question '+ident+' added')
            result=deepcopy(q);result['manual_placement_warnings']=self._placement_warnings(cat,q)
            return result

    def save_questions(self,payload,*,assets=None):
        """One retry-safe commit for bank entries, immutable revisions and an optional handout."""
        with self.desk.lock:
            self._editable();request=payload.get('request_id','')
            if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',request):raise ValueError('Start a new question save and retry.')
            fingerprint=digest(payload);marker=self._inside('actions/'+request+'.json')
            if marker.exists():
                receipt=read_json(marker)
                if receipt.get('fingerprint')!=fingerprint:raise ValueError('That save was already completed with different contents. Start a new save.')
                return {'catalog':self.catalog(),'questions':[self._question_revision(self._catalog(),q['id'],q['revision']) for q in receipt['questions']],'assignment':self.assignment(receipt['assignment']) if receipt.get('assignment') else None,'replayed':True}
            drafts=payload.get('questions')
            limit=5000 if payload.get('portable_restore') is True and payload.get('handout') is None else 150
            if not isinstance(drafts,list) or not 1<=len(drafts)<=limit or any(not isinstance(q,dict) or q.get('id') for q in drafts):raise ValueError('Choose between 1 and '+str(limit)+' new question drafts.')
            handout=payload.get('handout')
            if handout is not None and not isinstance(handout,dict):raise ValueError('Choose a handout draft.')
            if handout is not None and len(handout.get('questions',[]))+len(drafts)>150:raise ValueError('A handout can contain up to 150 questions.')
            staged={'catalog':self._catalog(),'changes':{}};self._staged_write=staged
            try:
                for relative,data in (assets or {}).items():
                    if not re.fullmatch(r'assets/imports/[a-f0-9]{64}\.(?:png|jpg|jpeg)',relative) or not isinstance(data,bytes):raise ValueError('Choose a valid imported image.')
                    target=self._inside(relative)
                    if target.exists() and target.read_bytes()!=data:raise ValueError('The imported image has changed.')
                    if not target.exists():staged['changes'][target]=data
                saved=[self.save_question(q) for q in drafts];assignment=None
                if handout is not None:
                    handout=deepcopy(handout);items=handout.setdefault('questions',[])
                    for q,draft in zip(saved,drafts):items.append({'id':q['id'],'revision':q['revision'],'points':draft.get('points'),'workspace_weights':[float(slot.get('weight',1)) for slot in q.get('workspace_slots',[])],'workspace_top':'0mm','page_break_after':False})
                    assignment=self.save_assignment(handout,_write=False);staged['changes'][self.assignments_path/(assignment['id']+'.json')]=json.dumps(assignment,ensure_ascii=False,indent=2)+'\n'
                receipt={'fingerprint':fingerprint,'questions':[{'id':q['id'],'revision':q['revision']} for q in saved],'assignment':assignment['id'] if assignment else None,'created':stamp()}
                staged['changes'][marker]=json.dumps(receipt,ensure_ascii=False,indent=2)+'\n'
            finally:self._staged_write=None
            self._write_catalog(staged['catalog'],staged['changes'],'Save '+str(len(saved))+' new question(s)'+(' and handout' if assignment else ''))
            return {'catalog':self.catalog(),'questions':saved,'assignment':assignment,'replayed':False}

    def _bank_revision(self,cat):
        return digest({'questions':sorted((q['id'],q.get('revision',''),q.get('bank_trash',{}).get('at','')) for q in all_questions(cat)), 'taxonomy':cat.get('taxonomy_revision','')})

    def manage_questions(self,payload):
        """One validated transaction for organization, recoverable deletion or restoration."""
        with self.desk.lock:
            self._editable();cat=self._catalog();operation=payload.get('operation')
            if operation not in ('organize','trash','restore','purge'):raise ValueError('Choose Organize, Move to Trash or Restore.')
            if payload.get('confirmed') is not True:raise ValueError('Review and confirm the selected question changes.')
            if payload.get('bank_revision')!=self._bank_revision(cat):raise ValueError('The question bank changed. Refresh and review the selection before applying it.')
            items=payload.get('items')
            if not isinstance(items,list) or not 1<=len(items)<=5000:raise ValueError('Select between 1 and 5000 questions.')
            selected=[];seen=set()
            for item in items:
                if not isinstance(item,dict):raise ValueError('Choose listed questions.')
                ident=item.get('id');question=self._question(cat,ident)
                if ident in seen or question.get('merged_into'):raise ValueError('Choose distinct questions from the bank.')
                if item.get('revision')!=question.get('revision'):raise ValueError('Question '+str(ident)+' changed. Refresh before applying the selection.')
                if bool(question.get('bank_trash'))!=(operation in ('restore','purge')):raise ValueError('Choose questions in '+('Trash.' if operation in ('restore','purge') else 'the current bank.'))
                self._check_source(question);seen.add(ident);selected.append(question)
            if operation=='purge' and seen!={q['id'] for q in cat.get('trashed_questions',[])}:raise ValueError('Review the entire Trash before clearing it.')
            changes={};replacements={}
            if operation=='organize':
                code=str(payload.get('course',''));self.desk.module(code)
                if code not in getattr(self.desk,'modules',CODES) or code=='136':raise ValueError('Choose an active course to organize.')
                add=payload.get('uses_add',[]);remove=payload.get('uses_remove',[])
                if not isinstance(add,list) or not isinstance(remove,list) or any(k not in KINDS for k in add+remove) or set(add)&set(remove):raise ValueError('Choose valid purpose changes.')
                if 'topic' in payload and not isinstance(payload['topic'],str):raise ValueError('Choose a topic for this course.')
                if not add and not remove and 'topic' not in payload:raise ValueError('Choose at least one topic or purpose change.')
                inventory=manual_topic_inventory(cat)
                for old in selected:
                    if old.get('archived') or old.get('pending_classification'):raise ValueError(old['id']+' must be active and its classification approved before organizing it.')
                    q=deepcopy(old);suitability=deepcopy(q.get('suitability',{}));uses=set(suitability.get(code,[]));uses.update(add);uses.difference_update(remove)
                    if uses:suitability[code]=[k for k in ('manual','worksheet','quiz','exam') if k in uses]
                    else:suitability.pop(code,None)
                    q['suitability']=self._suitability(suitability,not bool(suitability));q['suitability_none']=not bool(q['suitability'])
                    classes=deepcopy(q.get('classifications')) if 'classifications' in q else validate_classifications(cat,q,q['suitability'])
                    previous=deepcopy(classes)
                    if 'topic' in payload:
                        if code not in q['suitability']:raise ValueError('Choose a purpose for Math '+code+' before assigning its topic.')
                        classes[code]={'topic':payload['topic'],'objectives':payload.get('objectives',[])}
                    set_classifications(q,validate_classifications(cat,{'classifications':classes},q['suitability']))
                    for course in list(q.get('manual',{})):
                        if course not in q['suitability'] or 'manual' not in q['suitability'][course] or q['classifications'].get(course,{}).get('topic')!=previous.get(course,{}).get('topic'):q['manual'].pop(course,None)
                    self._auto_manual_placements(cat,q,inventory)
                    if q==old:continue
                    q['updated']=stamp();q.pop('revision',None);q.pop('tex',None);text=self._render_question(q);q['tex']=text;q['revision']=digest(q)
                    cat['questions']=[q if current['id']==q['id'] else current for current in cat['questions']]
                    replacements[q['id']]=q;changes[self._inside(q.get('file','questions/'+q['id']+'.tex'))]=text
                # Validation finishes for every selected question before any current source is changed.
                for old in selected:
                    if old['id'] in replacements:self._remember(old)
                for q in replacements.values():self._remember(q,q['tex'])
                cat['questions']=[replacements.get(q['id'],q) for q in cat['questions']]
            elif operation=='trash':
                trash=cat.setdefault('trashed_questions',[])
                for collection in ('questions','archived_questions'):
                    for old in cat.get(collection,[]):
                        if old['id'] in seen:
                            self._remember(old);q=deepcopy(old);q['bank_trash']={'at':stamp(),'origin':collection};trash.append(q)
                    cat[collection]=[q for q in cat.get(collection,[]) if q['id'] not in seen]
            elif operation=='purge':
                cat['next_question_number']=int(fresh_question_id(cat)[1:])
                for old in selected:
                    self._remember(old);changes[self._inside(old.get('file','questions/'+old['id']+'.tex'))]=None
                cat['trashed_questions']=[]
            else:
                for old in selected:
                    q=deepcopy(old);origin=q.pop('bank_trash')['origin']
                    if origin not in ('questions','archived_questions'):raise ValueError('The question recovery record is invalid.')
                    cat.setdefault(origin,[]).append(q)
                cat['trashed_questions']=[q for q in cat.get('trashed_questions',[]) if q['id'] not in seen]
            affected=list(replacements) if operation=='organize' else list(seen)
            if affected:self._write_catalog(cat,changes,operation.title()+' '+str(len(affected))+' question(s)')
            result=self.catalog();result['bank_action']={'operation':operation,'ids':affected,'count':len(affected)};return result

    def save_assignment(self,payload,*,_write=True):
        with self.desk.lock:
            self._editable();cat=self._catalog();code=str(payload.get('course',''));self.desk.module(code)
            tag=payload.get('semester','');term(tag);kind=payload.get('kind')
            if kind not in ('quiz','exam','final','worksheet'):raise ValueError('Choose Quiz, Exam, Final Exam, or Worksheet.')
            title=plain(payload.get('title',''),'assignment title',150)
            if kind=='worksheet':title=re.sub(r'(?i)\b(?:recitation[ ~_-]+worksheet|group[ -]?work)\b','Worksheet',title)
            if not title:raise ValueError('Enter an assignment title.')
            versions=integer(payload.get('versions',1),'Student versions',1,26)
            if kind=='worksheet' and versions!=1:raise ValueError('Worksheets use Version A. Set student versions to 1.')
            n=1 if kind=='final' else integer(payload.get('number',1),'Assignment number',1,999)
            selected=payload.get('questions',[])
            if not isinstance(selected,list) or not 1<=len(selected)<=150:raise ValueError('Select between 1 and 150 questions.')
            ident=payload.get('id');old=self.assignment(ident) if ident else None
            if old and payload.get('expected_revision')!=old['revision']:raise ValueError('This assignment changed. Refresh before saving it.')
            original=old or (self.assignment(payload['copy_from_id']) if payload.get('copy_from_id') else None)
            retained={(item['id'],item.get('revision')) for item in (original or {}).get('questions',[])}
            items=[];seen=set()
            for item in selected:
                current=next((q for q in all_questions(cat) if q['id']==item.get('id')),None)
                if current is None and (item.get('id'),item.get('revision')) not in retained:raise ValueError('This question was removed from the bank. Reuse it from its saved handout or create a copy.')
                if current is not None and current.get('bank_trash') and (item.get('id'),item.get('revision')) not in retained:raise ValueError('Restore '+current['id']+' from Trash before adding it to a new handout.')
                q=self._question_revision(cat,item['id'],item.get('revision'))
                if ('exam' if kind=='final' else kind) not in q.get('suitability',{}).get(code,[]):raise ValueError(q['id']+' is not marked suitable for Math '+code+' '+kind+'s.')
                if q['id'] in seen:raise ValueError('Each question can appear once in an assignment. Create a copy if you need a distinct question.')
                seen.add(q['id']);self._remember(q)
                points=item.get('points')
                if points is not None:
                    number(points,'point value')
                    if int(points)!=points:raise ValueError('Use whole-number points for each question.')
                    points=int(points)
                weights=item.get('workspace_weights')
                if weights is None:
                    try:weights=[float(s.get('weight',1)) for s in q.get('workspace_slots',[])]
                    except (ValueError,TypeError):raise ValueError('Choose numeric workspace weights for '+q['id']+'.')
                if not isinstance(weights,list) or len(weights)!=len(q.get('workspace_slots',[])):raise ValueError('The workspace positions changed for '+q['id']+'. Review its spacing in the builder.')
                for weight in weights:number(weight,'workspace weight',0,100)
                top=str(item.get('workspace_top','2mm')).strip() or '0pt'
                if not re.fullmatch(r'\d+(?:\.\d+)?(?:pt|mm|cm|in|em|ex)',top):raise ValueError('Enter top spacing such as 2mm or 0pt.')
                items.append({'id':q['id'],'revision':q['revision'],'points':points,'workspace_weights':weights,'workspace_top':top,'page_break_after':bool(item.get('page_break_after',False))})
            if any(x['id']!=ident and x.get('course')==code and x.get('semester')==tag and x.get('kind')==kind and x.get('number')==n for x in self.assignments()):
                raise ValueError(('Final Exam' if kind=='final' else kind.title()+' '+str(n))+' already exists for Math '+code+' in '+term(tag)+'. Open that handout or choose another semester or number.')
            a={'id':ident or 'A'+secrets.token_hex(8),'title':title,'course':code,'semester':tag,'kind':kind,'number':n,'versions':versions,'instructions':tex_input(payload.get('instructions','')),'workspace_enabled':bool(payload.get('workspace_enabled',False)),'questions':items,'created':old['created'] if old else stamp(),'updated':stamp()}
            original=old or (self.assignment(payload['copy_from_id']) if payload.get('copy_from_id') else None)
            if original:
                for field in ['source_preamble','source_instructions','source_suffix','imported','review_required','import_notes','source','provenance']:
                    if field in original:a[field]=deepcopy(original[field])
                if not old:a['copied_from']=original['id']
            a['revision']=digest(a);path=self.assignments_path/(a['id']+'.json')
            if _write:
                if path.exists():self.desk._history({path:path.read_bytes()},'Assignment '+title+' revised')
                save(path,a)
            return a

    def delete_assignment(self,payload):
        with self.desk.lock:
            self._editable()
            if payload.get('confirmed') is not True:raise ValueError('Confirm deletion of this handout.')
            a=self.assignment(payload.get('id'))
            if payload.get('expected_revision')!=a['revision']:raise ValueError('This handout changed. Refresh before deleting it.')
            path=(self.assignments_path/(a['id']+'.json')).resolve()
            if path.parent!=self.assignments_path.resolve():raise ValueError('Choose a saved handout.')
            self.desk._history({path:path.read_bytes()},'Deleted handout '+a['title'])
            recovery=self.base/'deleted-assignments';recovery.mkdir(exist_ok=True)
            save(recovery/(a['id']+'-'+secrets.token_hex(4)+'.json'),a)
            path.unlink()
            return {'deleted':a['id']}

    def _save_topic_chapters(self,cat,record,current,move_existing=False):
        """A protected topic edit can create a chapter, never silently regroup a manual."""
        inventory=manual_topic_inventory(cat);report=[]
        for code,label in record.get('course_labels',{}).items():
            old_label=topic_course_label(cat,current or record,code,inventory)
            title=label.pop('requested_chapter_title',old_label.get('chapter_title',''))
            requested_order=label.pop('requested_chapter_order',None)
            if old_label.get('section_id'):
                manual=cat['manuals'][code]
                section=next(x for x in manual['sections'] if x['id']==old_label['section_id'])
                if not title:raise ValueError('Enter a manual section name.')
                section['title']=title
                if requested_order is not None and requested_order!=section['order']:raise ValueError('Arrange this course in the manual outline to preserve its unit chapters.')
                for chapter in manual['chapters']:
                    for nested in chapter.get('sections',[]):
                        if nested['id']==section['id']:nested['title']=title
                label.update(chapter_id=section['chapter'],section_id=section['id'],chapter_title=title,chapter_order=section['order'])
                continue
            if not title:
                if old_label.get('chapter_id'):raise ValueError('Enter a manual chapter name for Math '+code+'. Existing chapters are preserved.')
                continue
            manual=cat['manuals'].setdefault(code,{'chapters':[],'sections':[]})
            chapters=manual.setdefault('chapters',[])
            ident=old_label.get('chapter_id') or 'c'+code+'-'+record['id']
            chapter=next((ch for ch in chapters if ch['id']==ident),None)
            if chapter and chapter.get('topic_id',record['id'])!=record['id']:raise ValueError('That manual chapter already belongs to a different topic.')
            default_order=old_label.get('chapter_order',max([c.get('order',0) for c in chapters] or [0])+1)
            order=number(default_order if requested_order is None else requested_order,'chapter order',1,100000)
            if chapter is None:
                chapter={'id':ident,'title':title,'order':order,'sections':[]};chapters.append(chapter)
            chapter.update(title=title,order=order,topic_id=record['id'])
            chapters.sort(key=lambda ch:(ch.get('order',9999),ch['id']))
            label.update(chapter_id=ident,chapter_title=title,chapter_order=order)
            existing=[q for q in cat['questions'] if 'manual' in q.get('suitability',{}).get(code,[]) and record['id'] in q.get('topics',[]) and q.get('manual',{}).get(code,{}).get('chapter')!=ident]
            candidates=[q for q in existing if q.get('topics')==[record['id']]]
            skipped=[];moved=[]
            if move_existing:
                protected_sections={s.get('after_section') for s in manual.get('supplements',[])}
                chapter_order={c['id']:c.get('order',9999) for c in chapters}
                section_order={s['id']:s.get('order',9999) for s in manual.get('sections',[])}
                candidates.sort(key=lambda q:(chapter_order.get(q.get('manual',{}).get(code,{}).get('chapter'),9999),section_order.get(q.get('manual',{}).get(code,{}).get('section'),9999),q.get('manual',{}).get(code,{}).get('order',9999),q['id']))
                last=max([q.get('manual',{}).get(code,{}).get('order',0) for q in cat['questions'] if q.get('manual',{}).get(code,{}).get('chapter')==ident] or [0])
                for q in candidates:
                    previous=q.get('manual',{}).get(code,{})
                    if previous.get('section') in protected_sections:
                        skipped.append({'id':q['id'],'reason':'Its imported section includes supplementary material.'});continue
                    self._check_source(q);self._remember(q);last+=1
                    q.setdefault('manual',{})[code]={'chapter':ident,'section':'','section_order':0,'order':last,'topic_id':record['id']}
                    q['updated']=stamp();q.pop('revision',None);q['revision']=digest(q);self._remember(q);moved.append(q['id'])
            report.append({'course':code,'chapter_id':ident,'chapter_title':title,'moved':moved,'remaining_imported':len(existing)-len(moved),'single_topic_candidates':len(candidates),'multi_topic_remaining':len(existing)-len(candidates),'skipped':skipped})
        return report

    def taxonomy(self,payload):
        with self.desk.lock:
            self._editable();cat=self._catalog()
            if payload.get('confirmed') is not True:raise ValueError('Enable editing and confirm this shared metadata change.')
            if payload.get('expected_revision')!=cat['taxonomy_revision']:raise ValueError('Topics or objectives changed. Refresh before saving.')
            kind=payload.get('kind');key={'topic':'topics','objective':'objectives'}.get(kind)
            if not key:raise ValueError('Choose topics or objectives.')
            ident=plain(payload.get('id',''),kind+' ID',100)
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_-]*',ident):raise ValueError('Use a stable ID with letters, numbers, hyphens, or underscores.')
            current=next((x for x in cat[key] if x['id']==ident),None);action=payload.get('action','save');changes={};chapter_changes=[]
            if action=='delete':
                if current is None:raise ValueError('That item no longer exists.')
                users=[q for q in cat['questions'] if ident in q.get(key,[])]
                replacement=payload.get('replacement_id')
                if kind=='topic' and any(ident in o.get('topic_ids',[]) and not o.get('retired') for o in cat['objectives']):raise ValueError('Move or delete this topic’s objectives before deleting the topic.')
                if users and not replacement:raise ValueError(str(len(users))+' questions use this '+kind+'. Choose a replacement first.')
                if replacement and (replacement==ident or not any(x['id']==replacement and not x.get('retired') for x in cat[key])):raise ValueError('Choose a different available replacement.')
                for q in users:
                    if kind=='objective':
                        replacement_record=next(x for x in cat['objectives'] if x['id']==replacement)
                        if any(ident in v.get('objectives',[]) and v.get('topic') not in replacement_record.get('topic_ids',[]) for v in q.get('classifications',{}).values()):raise ValueError('Choose a replacement objective that belongs to every affected topic.')
                    if kind=='topic':
                        replacement_record=next(x for x in cat['topics'] if x['id']==replacement)
                        if any(v.get('topic')==ident and code not in replacement_record.get('course_labels',{}) for code,v in q.get('classifications',{}).items()):raise ValueError('Choose a replacement topic available in every affected course.')
                    self._check_source(q)
                    self._remember(q);q[key]=list(dict.fromkeys(replacement if x==ident else x for x in q[key]))
                    if kind=='topic':
                        for placement in q.get('manual',{}).values():
                            if placement.get('topic_id')==ident:placement['topic_id']=replacement
                    for entry in q.get('classifications',{}).values():
                        if kind=='topic' and entry.get('topic')==ident:entry.update(topic=replacement,objectives=[],status='unassigned')
                        elif kind=='objective':entry['objectives']=list(dict.fromkeys(replacement if oid==ident else oid for oid in entry.get('objectives',[])))
                    if 'classifications' in q:set_classifications(q,q['classifications'])
                    q.pop('revision',None);q['tex']=self._render_question(q);q['revision']=digest(q);self._remember(q);changes[self.base/q['file']]=q['tex']
                current['retired']=True;current['replacement_id']=replacement
                if kind=='topic':
                    former={}
                    for code,label in current.get('course_labels',{}).items():
                        if label.get('chapter_id'):former[code]={field:label[field] for field in ('chapter_id','chapter_title','chapter_order') if field in label}
                        for field in ('chapter_id','chapter_title','chapter_order'):label.pop(field,None)
                    if former:current['retired_chapter_links']=former
                    for manual in cat['manuals'].values():
                        for chapter in manual.get('chapters',[]):
                            if chapter.get('topic_id')==ident:chapter.pop('topic_id')
            elif action=='save':
                value=payload.get('new_record',{})
                if not isinstance(value,dict):raise ValueError('Check the metadata fields.')
                record=deepcopy(current or {'id':ident});record['retired']=False
                if kind=='objective':
                    record['description']=metadata_text(value.get('description',''),'objective description',240)
                    if not record['description']:raise ValueError('Enter a short objective description.')
                    record['topic_ids']=self._refs(cat,'topics',value.get('topic_ids',[]))
                    if not record['topic_ids']:raise ValueError('Link this objective to at least one topic.')
                    for question in cat['questions']:
                        for entry in question.get('classifications',{}).values():
                            if ident in entry.get('objectives',[]) and entry.get('topic') not in record['topic_ids']:raise ValueError('This objective is used under a topic you removed. Reclassify those questions first.')
                else:
                    record['label']=metadata_text(value.get('label',''),'topic title',240)
                    if not record['label']:raise ValueError('Enter a topic title.')
                    labels=value.get('course_labels',{})
                    if not isinstance(labels,dict):raise ValueError('Check the course-specific topic labels.')
                    record['course_labels']={}
                    for code,label in labels.items():
                        if code not in getattr(self.desk,'modules',CODES) or not isinstance(label,dict):raise ValueError('Choose an installed course for the topic label.')
                        record['course_labels'][code]={'section':metadata_text(label.get('section',''),'section number',100),'title':metadata_text(label.get('title',''),'topic title',240)}
                        for field in ('app_name','header_name','lecture'):
                            record['course_labels'][code][field]=metadata_text(label.get(field,label.get('title','') if field!='lecture' else ''),field,300)
                        if 'chapter_title' in label:record['course_labels'][code]['requested_chapter_title']=metadata_text(label['chapter_title'],'manual chapter name',240)
                        if label.get('chapter_order') not in (None,''):record['course_labels'][code]['requested_chapter_order']=label['chapter_order']
                    used_courses=set()
                    for question in cat['questions']:
                        used_courses.update(code for code,entry in question.get('classifications',{}).items() if entry.get('topic')==ident)
                        if 'classifications' not in question and ident in question.get('topics',[]):
                            used_courses.update(set(question.get('suitability',{})) & set((current or {}).get('course_labels',{})))
                    removed=used_courses-set(record['course_labels'])
                    if removed:raise ValueError('This topic is used by questions in Math '+', '.join(sorted(removed))+'. Keep those course labels or reclassify the questions first.')
                    chapter_changes=self._save_topic_chapters(cat,record,current,payload.get('move_existing') is True)
                cat[key]=[record if r['id']==ident else r for r in cat[key]] if current else cat[key]+[record]
            else:raise ValueError('Choose save or delete.')
            cat['taxonomy_revision']=digest({k:cat.get(k) for k in ['topics','objectives','manuals']})
            changes.update(self._registry_files(cat))
            self._write_catalog(cat,changes,'Shared '+kind+' '+ident+' updated')
            result=self.catalog();result['topic_chapter_changes']=chapter_changes
            return result

    @staticmethod
    def _manual_question_rank(cat,code,q):
        placement=q.get('manual',{}).get(code,{})
        key=placement.get('section') or placement.get('chapter')
        ids=cat.get('manuals',{}).get(code,{}).get('question_order',{}).get(key,[])
        return (ids.index(q['id']) if q['id'] in ids else len(ids)+placement.get('order',9999),q['id'])

    def reorder_manual_questions(self,payload):
        with self.desk.lock:
            self._editable();cat=self._catalog();code=str(payload.get('course',''));self.desk.module(code)
            manual=cat.get('manuals',{}).get(code,{});chapter=payload.get('chapter');section=payload.get('section','')
            if not any(ch['id']==chapter for ch in manual.get('chapters',[])):raise ValueError('Choose a manual chapter.')
            if section and not any(s['id']==section and s['chapter']==chapter for s in manual.get('sections',[])):raise ValueError('Choose a section within this chapter.')
            group=[q for q in cat['questions'] if 'manual' in q.get('suitability',{}).get(code,[]) and q.get('manual',{}).get(code,{}).get('chapter')==chapter and (q['manual'][code].get('section') or '')==section]
            current=[q['id'] for q in sorted(group,key=lambda q:self._manual_question_rank(cat,code,q))]
            ids=payload.get('question_ids')
            if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)!=len(current) or len(set(ids))!=len(ids) or set(ids)!=set(current):raise ValueError('Reorder the existing questions within this section; questions cannot be added, removed, or moved between sections here.')
            if payload.get('expected_order')!=current:raise ValueError('This section changed. Refresh before reordering it.')
            if ids==current:return self.catalog()
            manual.setdefault('question_order',{})[section or chapter]=ids
            cat['taxonomy_revision']=digest({k:cat.get(k) for k in ['topics','objectives','manuals']})
            self._write_catalog(cat,reason='Math '+code+' manual question order changed within one section')
            return self.catalog()

    def manuals(self,payload):
        with self.desk.lock:
            self._editable();cat=self._catalog();code=str(payload.get('course',''));self.desk.module(code)
            if payload.get('confirmed') is not True:raise ValueError('Confirm the manual structure change.')
            if payload.get('expected_revision')!=cat['taxonomy_revision']:raise ValueError('The manual structure changed. Refresh before saving.')
            chapters=payload.get('chapters')
            if not isinstance(chapters,list) or len(chapters)>100:raise ValueError('Enter up to 100 manual chapters.')
            result=[];seen=set();new_sections=[];section_ids=set()
            for i,ch in enumerate(chapters):
                ident=plain(ch.get('id',''),'chapter ID',100);title=metadata_text(ch.get('title',''),'chapter title',240)
                if not re.fullmatch('[A-Za-z0-9_-]+',ident) or not title or ident in seen:raise ValueError('Each chapter needs a unique ID and a title.')
                previous=next((c for c in cat.get('manuals',{}).get(code,{}).get('chapters',[]) if c['id']==ident),{})
                section_rows=ch.get('sections',previous.get('sections',[]))
                if not isinstance(section_rows,list):raise ValueError('Check the chapter sections.')
                validated_sections=[]
                for si,section in enumerate(section_rows):
                    sid=plain(section.get('id',''),'section ID',100);stitle=metadata_text(section.get('title',''),'section title',240)
                    if not re.fullmatch('[A-Za-z0-9_-]+',sid) or sid in section_ids:raise ValueError('Each section needs a unique ID. Its title may be blank for exercises directly under the chapter.')
                    section_ids.add(sid);s={**section,'id':sid,'title':stitle,'chapter':ident,'order':len(new_sections)+1};validated_sections.append(s);new_sections.append(s)
                seen.add(ident);result.append({**previous,'id':ident,'title':title,'order':i+1,'sections':validated_sections})
            used={q.get('manual',{}).get(code,{}).get('chapter') for q in cat['questions'] if 'manual' in q.get('suitability',{}).get(code,[])}-{None,''}
            if used-seen:raise ValueError('Move questions out of a chapter before deleting it.')
            linked={t.get('course_labels',{}).get(code,{}).get('chapter_id') for t in cat['topics'] if not t.get('retired')}-{None,''}
            if linked-seen:raise ValueError('A topic uses this chapter. Keep the chapter and edit its name in Topics & Objectives.')
            old_sections={s['id'] for s in cat.get('manuals',{}).get(code,{}).get('sections',[])}
            used_sections={q.get('manual',{}).get(code,{}).get('section') for q in cat['questions'] if 'manual' in q.get('suitability',{}).get(code,[])} & old_sections
            if used_sections-section_ids:raise ValueError('Move questions out of a section before deleting it.')
            cat['manuals'].setdefault(code,{})['chapters']=result
            cat['manuals'][code]['sections']=new_sections
            chapter_map={ch['id']:ch for ch in result}
            for topic in cat['topics']:
                label=topic.get('course_labels',{}).get(code,{})
                chapter=chapter_map.get(label.get('chapter_id'))
                if chapter:label.update(chapter_title=chapter['title'],chapter_order=chapter['order'])
            cat['taxonomy_revision']=digest({k:cat.get(k) for k in ['topics','objectives','manuals']});self._write_catalog(cat,self._registry_files(cat),reason='Math '+code+' manual structure updated')
            return self.catalog()

    def _registry_files(self,cat):
        # Save registries in the same recoverable transaction as the catalog.
        return {
            self.base/'topics.json':json.dumps(cat['topics'],indent=2,ensure_ascii=False),
            self.base/'objectives.json':json.dumps(cat['objectives'],indent=2,ensure_ascii=False),
            self.base/'topics.tex':'\n'.join('\\DeclareMathTopic{'+t['id']+'}{title={'+t['label']+'},section={}}' for t in cat['topics'])+'\n',
            self.base/'archive/catalog.json':json.dumps({'questions':cat.get('archived_questions',[]),'categories':cat.get('archive_categories',[]),'topics':cat.get('archive_topics',[]),'objectives':cat.get('archive_objectives',[]),'supplements':cat.get('archived_supplements',[])},indent=2,ensure_ascii=False),
            self.base/'objectives.tex':'\n'.join('\\DeclareMathObjective{'+o['id']+'}{description={'+o['description']+'}}' for o in cat['objectives'])+'\n'
        }

    def _declarations(self,cat,code,questions=None):
        out=[]
        topic_ids={t for q in questions for t in q.get('topics',[])} if questions is not None else None
        objective_ids={o for q in questions for o in q.get('objectives',[])} if questions is not None else None
        for topic in cat['topics'] + cat.get('archive_topics',[]):
            if topic_ids is not None and topic['id'] not in topic_ids:continue
            label=topic.get('course_labels',{}).get(code,{})
            title=header_title(label,topic.get('label') or topic['id'])
            section='' if label.get('header_name') else label.get('section','')
            out.append('\\DeclareMathTopic{'+topic['id']+'}{title={'+title+'},section={'+section+'}}')
        for objective in cat['objectives'] + cat.get('archive_objectives',[]):
            if objective_ids is not None and objective['id'] not in objective_ids:continue
            description=objective.get('description',objective.get('label',objective['id']))
            out.append('\\DeclareMathObjective{'+objective['id']+'}{description={'+description+'}}')
        return '\n'.join(out)+'\n'

    def asset_source(self,text,assets):
        for asset in assets:
            relative=asset['path']
            if not re.fullmatch(r'assets/imports/[a-f0-9]{64}\.(?:png|jpg|jpeg)',relative):raise ValueError('Choose a valid library image.')
            image=self._inside(relative)
            if not image.is_file() or hash_file(image)!=asset['sha256']:raise ValueError('An imported question image is missing or changed. Restore it before compiling.')
            text=text.replace('{'+relative+'}','{\\detokenize{'+image.as_posix()+'}}')
        return text

    def _compile_tex(self,cat,code,title,tag,kind,mode,version,versions,selected,folder,instructions='',workspace=False,chapters=None,assignment=None,question_preview=False):
        selected=[(course_copy(q,code),use) for q,use in selected]
        if kind=='final':kind='exam'
        folder.mkdir(parents=True,exist_ok=True)
        layout='assessment' if kind in ('quiz','exam') else 'worksheet' if kind=='worksheet' else 'manual'
        prefix='\\PassOptionsToPackage{use-files}{xsim}\n\\documentclass['+layout+','+mode+']{mhdocument}\n'
        prefix+='\\usepackage{needspace,framed,tabularx}\n\\usetikzlibrary{patterns}\n\\usepgfplotslibrary{fillbetween}\n'
        coursework=self.desk.repo/'lib'/('mh-'+code)/('mh-'+code+'-coursework.sty')
        if kind in ('quiz','exam') and not (assignment or {}).get('source_instructions') and coursework.is_file():prefix+='\\usepackage{mh-'+code+'-coursework}\n'
        if kind=='exam' and code=='135' and not question_preview:prefix+='\\usepackage{mh-135-reference}\n'
        if assignment:prefix+=assignment.get('source_preamble','')+'\n\\SetCourseworkNumber{'+str(assignment.get('number',1))+'}\n'
        if any('MathExam' in self._tex(q) for q,_ in selected):prefix+='\\usepackage{mh-152-exam-data}\n'
        prefix+=self._declarations(cat,code,[q for q,_ in selected])
        prefix+='\\SetExamVersions{'+str(versions)+'}\n\\SetExamVersion{'+version+'}\n'
        prefix+='\\SetMathLeftHeader{Math '+code+' (01:640:'+code+')}\n\\SetMathCenterHeader{'+escape(title)+(' (Version '+version+')' if versions>1 and mode=='student' else '')+(' (Solutions)' if mode in ('solutions','developer') else '')+'}\n\\SetMathRightHeader{'+(term(tag) if kind!='manual' else '')+'}\n'
        if kind=='worksheet':prefix+='\\SetWorksheetWorkspace{'+('true' if workspace else 'false')+'}\n'
        prefix+='\\begin{document}\n'
        if kind=='manual':prefix+='\\frontmatter\n\\maketitle\n\\vspace{-2cm}\n\\tableofcontents\n\\mainmatter\n'
        elif kind=='worksheet':
            if workspace:
                # Same name/netID row as WorksheetFrontMatter in worksheet-blank.tex.
                prefix+=r'\IfMathStudentT{\noindent\begin{tabularx}{\linewidth}{@{}l X @{\hspace{2em}} l p{0.24\linewidth}@{}}Name: & \hrulefill & netID: & \hrulefill\end{tabularx}\par\vspace{-0.8em}}'+'\n'
        elif kind in ('quiz','exam') and not question_preview:
            front=(assignment or {}).get('source_instructions','')
            if kind=='exam' and code=='135':
                # Older imports contain an expanded copy of the original cover.
                front=front.replace('[c][1.15in][b]','[c][1.25in][b]').replace('[c][1.45in][b]','[c][1.25in][b]').replace(r'\rule{6.1in}{0.75pt}',r'\rule{\dimexpr\linewidth-0.95in\relax}{0.75pt}')
            if front:prefix+='\\IfMathStudentT{'+front+'}\n'
            elif coursework.is_file():prefix+='\\'+('QuizFrontMatter' if kind=='quiz' else 'ExamFrontMatter')+'\n'
            elif kind=='exam':prefix+='\\IfMathStudentT{\\begin{center}\\Large '+escape(title)+'\\end{center}\\noindent Name: \\hrulefill\\par}\n'
            if instructions and instructions!='Show your work clearly. Give complete answers to each question.':prefix+='\\IfMathStudentT{'+instructions+'\\par\\medskip}\n'
            if kind=='exam':
                if code=='135':
                    has_reference=any(marker in front for marker in [r'\ReferenceSheet','Quadratic Formula','formula-sheet-content'])
                    prefix+='\\IfMathStudentT{\\clearpage'+('' if has_reference else r'\ReferenceSheet')+'}\n'
                else:
                    prefix+=r'\IfMathStudentT{\clearpage\thispagestyle{empty}\null\clearpage}'+'\n'
        last_chapter=None;last_section=None
        manual=cat.get('manuals',{}).get(code,{})
        section_by_id={s['id']:s for s in manual.get('sections',[])}
        emitted_supplements=set()
        def supplements(placement,field='after_section'):
            result=[]
            for i,s in enumerate(manual.get('supplements',[])):
                if i not in emitted_supplements and s.get(field)==placement:
                    emitted_supplements.add(i);result.append(s['tex'])
            return '\n'.join(result)+'\n'
        for index,(q,use) in enumerate(selected):
            if kind=='manual':
                placement=q.get('manual',{}).get(code,{})
                chapter=placement.get('chapter');section=placement.get('section','')
                if chapter!=last_chapter:
                    if last_section is not None:prefix+=supplements(last_section)
                    if last_chapter is not None:prefix+=supplements(last_chapter,'after_chapter')
                    chapter_record=next((c for c in (chapters or []) if c['id']==chapter),None)
                    if chapter_record is None:raise ValueError(q['id']+' needs a manual chapter before compiling.')
                    prefix+='\\chapter{'+chapter_record['title']+'}\n';last_chapter=chapter;last_section=None
                if section and section!=last_section:
                    if last_section is not None:prefix+=supplements(last_section)+'\\clearpage\n'
                    section_title=section_by_id.get(section,{}).get('title',section)
                    if section_title.strip():prefix+='\\section{'+section_title+'}\n'
                    last_section=section
            text=self._tex(q)
            text=self.asset_source(text,q.get('import_assets',[]))
            # Imported blank lines must not make an empty paragraph after the box strut.
            text=re.sub(r'(\\begin\{exercise\}(?:\[[^\]]*\])?)[ \t]*\r?\n(?:[ \t]*\r?\n)+',r'\1\n',text,count=1)
            # Only the selected copies receive assignment-specific layout and points.
            options=[]
            if use.get('points') is not None and kind in ('quiz','exam'):options.append('points={'+str(use['points'])+'}')
            weights=use.get('workspace_weights',[])
            if kind in ('quiz','exam') and weights:
                if any(float(w)>0 for w in weights):options.extend(['workspace','workspace-top={'+use.get('workspace_top','2mm')+'}'])
                prefix+='\\SetQuestionWorkspaceWeights{'+','.join(str(w) for w in weights)+'}\n'
            elif kind=='worksheet' and workspace and weights:
                prefix+='\\SetQuestionWorkspaceWeights{'+','.join(str(w) for w in weights)+'}\n'
            if options:
                marker=re.search(r'\\begin\{exercise\}\s*\[',text)
                if marker:text=text[:marker.end()]+','.join(options)+','+text[marker.end():]
                else:text=text.replace('\\begin{exercise}','\\begin{exercise}['+','.join(options)+']',1)
            dest=folder/(str(index+1).zfill(3)+'-'+q['id']+'.tex');dest.write_text(text,encoding='utf8')
            if kind in ('quiz','exam') and use.get('points') is None:prefix+='\\begingroup\\RenewDocumentCommand{\\AssessmentExercisePointBox}{m}{}\n'
            prefix+='\\input{'+dest.as_posix()+'}\n'
            if kind in ('quiz','exam') and use.get('points') is None:prefix+='\\endgroup\n'
            if use.get('page_break_after'):prefix+='\\cp\n'
        if kind=='manual' and last_section is not None:prefix+=supplements(last_section)
        if kind=='manual' and last_chapter is not None:prefix+=supplements(last_chapter,'after_chapter')
        if kind=='exam' and not question_preview:prefix+=r'\IfMathStudentT{\par\clearpage\ifodd\value{page}\blankpage\blankpage\else\blankpage\fi}'+'\n'
        elif assignment and assignment.get('source_suffix'):prefix+='\\IfMathStudentT{'+assignment['source_suffix']+'}\n'
        prefix+='\\end{document}\n';source=folder/'document-source.tex';source.write_text(prefix,encoding='utf8');return source

    def compile(self,payload):
        with self.desk.lock:
            if self.desk.active:raise ValueError('Let the current compilation finish first.')
            ids=payload.get('assignment_ids')
            if ids is None:
                code,tag,jobs=self._compile_jobs(payload)
                return self.desk.start(code,tag,[],custom=jobs)
            if not isinstance(ids,list) or not 1<=len(ids)<=100 or len(set(ids))!=len(ids):raise ValueError('Select between 1 and 100 different handouts.')
            assignments=[self.assignment(ident) for ident in ids]
            contexts={(a['course'],a['semester']) for a in assignments}
            if len(contexts)!=1:raise ValueError('Select handouts from one course and semester.')
            plans=[{'assignment_id':a['id'],'mode':payload.get('mode','all'),'version':'all',**({'student_versions':payload['student_versions']} if 'student_versions' in payload else {})} for a in assignments]
            # Validate the complete selection before creating any draft sources.
            for a,options in zip(assignments,plans):self._compile_outputs(options,a['versions'])
            jobs=[]
            for options in plans:
                code,tag,planned=self._compile_jobs(options)
                jobs.extend(planned)
            return self.desk.start(code,tag,[],custom=jobs,publish_when_ready=payload.get('publish_when_ready') is True)

    @staticmethod
    def _compile_outputs(payload,versions):
        mode=payload.get('mode','all');version=payload.get('version','all')
        allowed=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')[:versions]
        if mode not in ('all','student','solutions','developer'):raise ValueError('Choose student, solutions, or developer output.')
        if version!='all' and version not in allowed:raise ValueError('Choose an available student version.')
        if 'student_versions' in payload:
            selected=payload['student_versions']
            if mode not in ('all','student') or version!='all':raise ValueError('Use selected student versions with student or all output and no single-version override.')
            if not isinstance(selected,list) or not selected or any(not isinstance(v,str) or v not in allowed for v in selected) or len(selected)!=len(set(selected)):raise ValueError('Select one or more different available student versions.')
            selected=[v for v in allowed if v in selected]
        else:selected=allowed if version=='all' else [version]
        outputs=[('student',v) for v in selected] if mode in ('all','student') else []
        if mode in ('all','solutions'):outputs.append(('solutions','A'))
        if mode=='developer':outputs.append(('developer','A'))
        return outputs

    def _compile_jobs(self,payload):
        with self.desk.lock:
            if self.desk.active:raise ValueError('Let the current compilation finish first.')
            cat=self._catalog();a=None;chapters=None
            if payload.get('assignment_id'):
                a=self.assignment(payload['assignment_id']);code=a['course'];tag=a['semester'];kind=a['kind'];title=a['title'];versions=a['versions']
                selected=[(self._question_revision(cat,u['id'],u['revision']),u) for u in a['questions']]
            elif payload.get('kind')=='manual':
                code=str(payload.get('course',''));self.desk.module(code);tag=payload.get('semester') or self.desk.module(code).CONFIG['default_semester'];kind='manual';title='Exercise Manual';versions=1
                chapters=cat.get('manuals',{}).get(code,{}).get('chapters',[]);order={c['id']:c.get('order',i) for i,c in enumerate(chapters)}
                qs=[q for q in cat['questions'] if 'manual' in q.get('suitability',{}).get(code,[])]
                if not qs:raise ValueError('No questions are marked suitable for this manual.')
                missing=[q['id'] for q in qs if q.get('manual',{}).get(code,{}).get('chapter') not in order]
                if missing:raise ValueError('Assign manual chapters first: '+', '.join(missing[:12]))
                sections={s['id']:s.get('order',i) for i,s in enumerate(cat['manuals'][code].get('sections',[]))}
                qs.sort(key=lambda q:(order[q['manual'][code]['chapter']],sections.get(q['manual'][code].get('section'),-1 if not q['manual'][code].get('section') else 9999),*self._manual_question_rank(cat,code,q)))
                selected=[(q,{}) for q in qs]
                for q in qs:self._check_source(q)
            else:raise ValueError('Choose a saved assignment or a course manual.')
            term(tag);outputs=self._compile_outputs(payload,versions)
            batchdir=self.desk.temp/'Drafts'/('universal-'+secrets.token_hex(8));jobs=[]
            for i,(md,v) in enumerate(outputs):
                source=self._compile_tex(cat,code,title,tag,kind,md,v,versions,selected,batchdir/str(i),a.get('instructions','') if a else '',a.get('workspace_enabled',False) if a else False,chapters,a)
                semester_folder,short=self.desk.module(code).semester_info(tag)
                name=('Manual-'+code if kind=='manual' else 'Final-Exam-'+short if kind=='final' else kind.title()+'-'+str(a['number'])+'-'+short)
                if kind!='manual' and versions>1:name+='-'+v
                if md=='solutions':name+='-Sols' if kind=='manual' else '-sols'
                if md=='developer':name+='-Developer'
                material_kind='Final Exam' if kind=='final' else kind.title()
                out=self.desk.publish_folder(code,tag,material_kind,a['number'] if a and kind!='final' else '',md,v)
                jobs.append({'name':name,'source':source,'prefix':'','folder':out,'kind':material_kind,'mode':md,'version':v,'universal':True,'assignment_id':a['id'] if a else None,'publish_number':a['number'] if a else '', 'question_revisions':[{ 'id':q['id'],'revision':q['revision']} for q,_ in selected]})
            return code,tag,jobs

    def preview(self,payload):
        with self.desk.lock:
            if self.desk.active:raise ValueError('Let the current compilation finish first.')
            cat=self._catalog();q=self._question(cat,payload.get('id'));code=str(payload.get('course') or next(iter(q['suitability']),None) or q.get('source',{}).get('course') or '135')
            self._check_source(q)
            module=self.desk.module(code);mode=payload.get('mode','solutions');kind=payload.get('layout','manual')
            if mode not in ('student','solutions','developer'):raise ValueError('Choose an output mode.')
            if kind not in ('manual','worksheet','quiz','exam','final','assessment'):raise ValueError('Choose a handout style for this question preview.')
            version=payload.get('version','A')
            if not isinstance(version,str) or not re.fullmatch('[A-Z]',version):raise ValueError('Choose a preview version from A to Z.')
            versions=integer(payload.get('versions',ord(version)-ord('A')+1),'Student versions',1,26)
            if ord(version)-ord('A')>=versions:raise ValueError('Choose a version available in this handout.')
            if mode!='student':version='A'
            workspace=payload.get('workspace_enabled',kind in ('quiz','exam','final','assessment'))
            if not isinstance(workspace,bool):raise ValueError('Choose whether working space is shown.')
            tag=payload.get('semester') or module.CONFIG['default_semester'];term(tag)
            folder=self.desk.temp/'Drafts'/('universal-preview-'+secrets.token_hex(8))
            use={'workspace_weights':[float(slot.get('weight',1)) if workspace else 0 for slot in q.get('workspace_slots',[])],'workspace_top':'0mm'}
            compile_kind='preview' if kind=='manual' else 'quiz' if kind=='assessment' else kind
            source=self._compile_tex(cat,code,'Question '+q['id'],tag,compile_kind,mode,version,versions,[(q,use)],folder,workspace=workspace,question_preview=True)
            return self.desk.start(code,tag,[],custom=[{'name':'Question-'+q['id']+'-'+mode+'-'+version,'source':source,'prefix':'','folder':folder,'kind':'Question preview','mode':mode,'version':version,'layout':kind,'preview_only':True,'universal':True}])
