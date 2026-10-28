"""Strict, portable rubric exports; no page state, record IDs or geometry."""
import copy,json,math,re

def validate_outline(outline):
    def fail():raise ValueError('Check the outline labels, parent relationships and point values.')
    if not isinstance(outline,list) or not 1<=len(outline)<=200:fail()
    rows={};keys=set();graded={}
    for n in outline:
        if not isinstance(n,dict) or set(n)!={'number','key','title','maxPoints','parentNumber','graded'}:fail()
        number=n['number'];key=n['key'];points=n['maxPoints'];parent=n['parentNumber']
        if not isinstance(number,str) or len(number)>40 or not re.fullmatch(r'\d+(?:\.\d+)*',number) or number in rows:fail()
        if number.count('.')>1 or (parent is not None and ('.' in str(parent) or not n['graded'])):raise ValueError('Only one level of subquestions is allowed. Ungroup nested parts before saving or importing.')
        if (parent is None and '.' in number) or (parent is not None and number.rsplit('.',1)[0]!=parent):fail()
        if not isinstance(key,str) or len(key)>40 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',key) or key in keys:fail()
        if not isinstance(n['title'],str) or not n['title'].strip() or len(n['title'])>240 or type(n['graded']) is not bool or type(points) not in (int,float) or not math.isfinite(points) or not 0<=points<=1000000:fail()
        if parent is not None and (not isinstance(parent,str) or parent not in rows or not number.startswith(parent+'.') or rows[parent]['graded']):fail()
        rows[number]=n;keys.add(key)
        if n['graded']:graded[key]=n
    return graded

def validate_export(value):
    def fail():raise ValueError('Choose a complete G-Rater rubric export with valid questions, groups and outline.')
    def exact(v,keys):return isinstance(v,dict) and set(v)==set(keys.split())
    def text(v,n,empty=False):return isinstance(v,str) and len(v)<=n and (empty or bool(v.strip()))
    def num(v):return type(v) in (int,float) and math.isfinite(v) and abs(v)<=1000000
    def key(v):return text(v,40) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',v)
    def path(v):return text(v,40) and re.fullmatch(r'\d+(?:\.\d+)*',v)
    if not isinstance(value,dict):fail()
    version=value.get('version')
    if type(version) is not int or version not in (1,2) or not exact(value,'format version title text'+(' outline questions' if version==2 else '')) or value['format']!='g-rater-rubric-export':fail()
    if not text(value['title'],160,True) or not text(value['text'],200000):fail()
    if version==1:return {**value,'title':value['title'].strip() or 'Untitled rubric','text':value['text'].strip()}
    outline=value['outline'];questions=value['questions']
    validate_outline(outline)
    if not isinstance(outline,list) or not 1<=len(outline)<=200 or not isinstance(questions,list) or not 1<=len(questions)<=100:fail()
    numbers={};graded={};keys=set()
    for row in outline:
        if not exact(row,'number key title maxPoints parentNumber graded') or not path(row['number']) or not key(row['key']) or not text(row['title'],240) or not num(row['maxPoints']) or row['maxPoints']<0 or type(row['graded']) is not bool or row['number'] in numbers or row['key'] in keys:fail()
        parent=row['parentNumber']
        if parent is not None and (not path(parent) or parent not in numbers or not row['number'].startswith(parent+'.') or numbers[parent]['graded']):fail()
        numbers[row['number']]=row;keys.add(row['key'])
        if row['graded']:graded[row['key']]=row
    seen=set()
    for q in questions:
        if not exact(q,'key title maxPoints groups') or not key(q['key']) or not text(q['title'],240) or not num(q['maxPoints']) or q['maxPoints']<0 or q['key'] in seen or q['key'] not in graded or graded[q['key']]['maxPoints']!=q['maxPoints'] or graded[q['key']]['title']!=q['title']:fail()
        seen.add(q['key'])
        if not isinstance(q['groups'],list) or not 1<=len(q['groups'])<=50:fail()
        for g in q['groups']:
            if not exact(g,'description selectionMode items') or not text(g['description'],4000,True) or g['selectionMode'] not in ('one','all') or not isinstance(g['items'],list) or not 1<=len(g['items'])<=50:fail()
            for i in g['items']:
                if not exact(i,'label description points') or not text(i['label'],160) or not text(i['description'],4000) or not num(i['points']):fail()
    if len(seen)!=len(graded):fail()
    try:parsed=json.loads(value['text'])
    except (ValueError,TypeError):fail()
    if parsed!={'outline':outline,'questions':questions}:fail()
    return {**value,'title':value['title'].strip() or 'Untitled rubric','text':value['text'].strip()}

def export_questions(value):
    if value['version']==1:return None
    # Current G-Scope has one selection rule per graded part. Do not silently
    # flatten independent groups into a different scoring rule.
    if any(len(q['groups'])!=1 for q in value['questions']):raise ValueError('This export has multiple independent rubric groups per question. Keep the export; G-Scope needs group editing support before it can load those rules safely.')
    return [{k:q[k] for k in ('key','title','maxPoints')}|{'selectionMode':q['groups'][0]['selectionMode'],'items':q['groups'][0]['items']} for q in value['questions']]

def reviewed_export(version,title):
    outline=copy.deepcopy(version.get('rubricOutline',[]));by_key={q['key']:q for q in version['questions']}
    if not outline or {n['key'] for n in outline if n['graded']}!=set(by_key):return None
    try:descriptions={q['key']:q['groups'][0]['description'] for q in json.loads(version.get('raw_rubric',''))['questions'] if len(q['groups'])==1}
    except (ValueError,KeyError,TypeError):descriptions={}
    questions=[]
    for row in outline:
        if not row['graded']:continue
        q=by_key[row['key']];row['title']=q['title'];row['maxPoints']=q['maxPoints']
        questions.append({k:q[k] for k in ('key','title','maxPoints')}|{'groups':[{'description':descriptions.get(q['key'],''),'selectionMode':q['selectionMode'],'items':[{k:i[k] for k in ('label','description','points')} for i in q['items']]}]})
    for row in reversed(outline):
        children=[n for n in outline if n['parentNumber']==row['number']]
        if not row['graded'] and children:row['maxPoints']=sum(n['maxPoints'] for n in children)
    data={'outline':outline,'questions':questions}
    return validate_export({'format':'g-rater-rubric-export','version':2,'title':title,'text':json.dumps(data,ensure_ascii=False,indent=2),**data})

def reconcile_outline(previous,questions):
    """Keep template groups through rubric/title/label edits at either entry point."""
    outline=copy.deepcopy(previous.get('rubricOutline',[]))
    if not outline:return None
    # Old saved hierarchies may predate the single-sublayer rule. Keep every
    # graded part under its top-level group and remove intermediate summaries.
    if any(n['number'].count('.')>1 or (n['parentNumber'] and not n['graded']) for n in outline):
        by_number={n['number']:n for n in outline}
        for n in outline:
            parent=by_number.get(n['parentNumber']);seen={n['number']}
            while parent and parent['parentNumber']:
                if parent['number'] in seen:raise ValueError('Check the outline hierarchy for a cycle.')
                seen.add(parent['number']);parent=by_number.get(parent['parentNumber'])
            if n['parentNumber']:n['parentNumber']=parent['number'] if parent else None
        old=[n for n in outline if n['graded'] or not n['parentNumber']];outline=[]
        children_by_parent={n['number']:[c for c in old if c['parentNumber']==n['number']] for n in old if not n['parentNumber']}
        for index,root in enumerate(n for n in old if not n['parentNumber']):
            number=root['number'];root['number']=str(index+1);outline.append(root)
            for part,child in enumerate(children_by_parent[number]):
                child['parentNumber']=root['number'];child['number']=root['number']+'.'+str(part+1);outline.append(child)
    by_id={q['id']:q for q in previous['questions']};by_key={q['key']:q for q in questions};renamed={by_id[q['id']]['key']:q for q in questions if q.get('id') in by_id}
    parent_keys={n['key'] for n in outline if not n['graded']}
    if parent_keys&set(by_key):raise ValueError('A question label is already used by a parent group. Use a distinct subpart label or ungroup it first.')
    next_rows=[];used=set()
    for row in outline:
        if not row['graded']:next_rows.append(row);continue
        q=renamed.get(row['key']) or by_key.get(row['key'])
        if not q:continue
        row.update(key=q['key'],title=q['title'],maxPoints=q['maxPoints']);next_rows.append(row);used.add(q['key'])
    root_index=max([int(n['number'].split('.')[0]) for n in next_rows] or [0])
    for q in questions:
        if q['key'] not in used:
            root_index+=1;next_rows.append({'number':str(root_index),'key':q['key'],'title':q['title'],'maxPoints':q['maxPoints'],'parentNumber':None,'graded':True})
    changed=True
    while changed:
        parents={n['parentNumber'] for n in next_rows};filtered=[n for n in next_rows if n['graded'] or n['number'] in parents];changed=len(filtered)!=len(next_rows);next_rows=filtered
    for row in reversed(next_rows):
        if not row['graded']:row['maxPoints']=sum(n['maxPoints'] for n in next_rows if n['parentNumber']==row['number'])
    validate_outline(next_rows);return next_rows
