"""Installed base content with a separate, preserved local editing layer."""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache
import hashlib,json,os,re,time,tempfile,stat

def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
def load(path,default):return json.loads(path.read_text('utf-8-sig')) if path.is_file() else default
def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.course-',suffix='.new',dir=path.parent,delete=False) as stream:
        temp=Path(stream.name);stream.write(raw)
    try:os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def linked(path):
    try:info=path.lstat()
    except FileNotFoundError:return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024))

@contextmanager
def locked(root):
    path=checked(root/'Data','.course-content.lock');path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            stream.seek(0);stream.write(b'0');stream.flush();deadline=time.monotonic()+30
            while True:
                try:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>deadline:raise ValueError('Course content is being prepared. Retry shortly.')
                    time.sleep(.1)
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

def checked(base,relative,*,verified_tree=False):
    relative=str(relative).replace(os.sep,'/')
    parts=relative.split('/')
    if not relative or '\\' in relative or PurePosixPath(relative).is_absolute() or any(p in ('','..','.') or ':' in p or p.rstrip(' .')!=p for p in parts):
        raise ValueError('Invalid installed course path.')
    if any(p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts):raise ValueError('Invalid installed course path.')
    target=base.joinpath(*parts)
    # Lexical containment plus the explicit no-link walk avoids repeatedly
    # resolving thousands of already-normalized paths during first startup.
    if not target.absolute().is_relative_to(base.absolute()):raise ValueError('Invalid installed course path.')
    if not verified_tree:
        for node in (target,*target.parents):
            if linked(node):raise ValueError('Course content cannot follow links.')
            if node==base:break
    return target

def source_files(base):
    if linked(base):raise ValueError('Course content cannot follow links.')
    result={}
    for folder,dirs,files in os.walk(base):
        for name in dirs+files:
            path=Path(folder)/name
            if linked(path):raise ValueError('Course content cannot follow links.')
        for name in files:
            path=Path(folder)/name;result[path.relative_to(base).as_posix()]=path
    return result

def commit(changes):
    """Apply file/catalogue pairs together; restore originals after an I/O failure."""
    originals={path:path.read_bytes() if path.is_file() else None for path in changes};applied=[]
    try:
        for path,raw in changes.items():
            if originals[path]==raw:continue
            write(path,raw);applied.append(path)
    except BaseException:
        for path in reversed(applied):
            if originals[path] is None:path.unlink(missing_ok=True)
            else:write(path,originals[path])
        raise

def prepare(root):
    root=Path(root).resolve();data=root/'Data';work=checked(data,'Teaching Content');bank=checked(data,'Question Bank')
    support=root/'Dependencies/TeachingSupport'
    if not support.is_dir():raise ValueError('Shared TeX support is missing. Run G-Works Setup and choose Repair.')
    # Resolve only the installer-owned dependency link; content descendants and
    # local editing destinations remain link-free.
    support=support.resolve();support_files=source_files(support)
    if 'lib/mhdocument.cls' not in support_files:raise ValueError('The shared MathHouse support library is incomplete.')
    shared=root.parent.parent/'Shared';course_root=shared/'Courses';courses=[];sources={}
    if linked(course_root):raise ValueError('Course content cannot follow links.')
    for folder in sorted(course_root.glob('*')):
        if linked(folder):raise ValueError('Course content cannot follow links.')
        if not folder.is_dir():continue
        manifest=load(checked(folder,'manifest.json'),{})
        if manifest.get('schema')!=1 or manifest.get('course')!=folder.name or not isinstance(manifest.get('files'),dict):raise ValueError('Repair the installed course package.')
        base=checked(folder,'Base');actual=source_files(base)
        if set(actual)!=set(manifest['files']):raise ValueError('Installed course files differ from their manifest. Repair the course pack.')
        content={}
        for relative,expected in manifest['files'].items():
            p=checked(base,relative,verified_tree=True);raw=p.read_bytes()
            if not isinstance(expected,str) or digest(raw)!=expected:raise ValueError('Installed course content changed. Repair its course pack before continuing.')
            content[relative]=raw
        incoming=json.loads(content['bank/catalog.json']) if 'bank/catalog.json' in content else {}
        courses.append(incoming)
        for relative,raw in content.items():
            if relative=='bank/catalog.json':continue
            target=checked(bank,relative[5:],verified_tree=True) if relative.startswith('bank/') else checked(work,relative,verified_tree=True)
            if target in sources and sources[target]!=raw:raise ValueError('Installed courses contain conflicting base files.')
            sources[target]=raw
    for relative,p in support_files.items():
        if relative=='.gworks-package.json':continue
        target=checked(work,relative,verified_tree=True);raw=p.read_bytes()
        if target in sources and sources[target]!=raw:raise ValueError('Installed course and shared support files conflict.')
        sources[target]=raw
    with locked(root):
        # Validate each existing destination node once, rather than resolving
        # every ancestor for every question. Writes recheck their exact path.
        source_files(work);source_files(bank)
        state_path=checked(data,'course-content.json');state=load(state_path,{'files':{},'records':{}})
        old=state.get('files',{});files=dict(old);records=dict(state.get('records',{}));changes={};protected=set()
        @lru_cache(maxsize=None)
        def key(path):return path.relative_to(data).as_posix()
        # Windows file-open checks dominate a large bank. Read independent
        # current files concurrently, while keeping validation and mutation
        # serialized under the content lock. Every source hash is still checked.
        def read_current(path):return path,path.read_bytes() if path.is_file() else None
        with ThreadPoolExecutor(max_workers=8) as reader:current=dict(reader.map(read_current,sources))
        def contents(path):
            if path not in current:current[path]=path.read_bytes() if path.is_file() else None
            return current[path]
        def owned(path):
            raw=contents(path)
            return (raw is None and key(path) not in old) or (raw is not None and digest(raw)==old.get(key(path)))
        catpath=checked(bank,'catalog.json',verified_tree=True)
        cat=load(catpath,{'schema_version':1,'status':'ready','questions':[],'topics':[],'objectives':[],'courses':[],'manuals':{},'assets':{}})
        for incoming in courses:
            for kind in ('questions','archived_questions','topics','objectives','archive_topics','archive_objectives','courses'):
                field='code' if kind=='courses' else 'id';rows=cat.setdefault(kind,[]);index={r[field]:i for i,r in enumerate(rows)}
                for row in incoming.get(kind,[]):
                    ident=kind+'/'+row[field];sha=digest(encoded(row));existing=rows[index[row[field]]] if row[field] in index else None
                    can_replace=(existing is None and ident not in records) or (existing is not None and digest(encoded(existing))==records.get(ident))
                    if kind in ('questions','archived_questions'):
                        target=checked(bank,row.get('file','questions/'+row['id']+'.tex'),verified_tree=True)
                        previous=checked(bank,existing.get('file','questions/'+existing['id']+'.tex'),verified_tree=True) if existing else target
                        if target not in sources:raise ValueError('An installed question is missing its TeX file.')
                        if row.get('tex') is not None and sources[target].decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')!=row['tex']:raise ValueError('An installed question and its TeX file disagree.')
                        can_replace=can_replace and owned(target) and owned(previous)
                        if not can_replace:
                            protected.update((target,previous));continue
                        if existing is not None and existing!=row:
                            if not re.fullmatch(r'[A-Za-z0-9_-]+',str(existing['id'])) or not re.fullmatch(r'[a-f0-9]{64}',str(existing.get('revision',''))):raise ValueError('The saved question revision is invalid.')
                            snapshot=deepcopy(existing)
                            if 'tex' not in snapshot:snapshot['tex']=previous.read_text('utf-8-sig')
                            for suffix,raw in (('.json',encoded(snapshot)),('.tex',snapshot['tex'].encode('utf-8'))):
                                revision=checked(bank,'revisions/'+existing['id']+'/'+existing['revision']+suffix,verified_tree=True)
                                if revision.is_file():
                                    if suffix=='.tex' and revision.read_bytes()!=raw:raise ValueError('A saved question revision has changed.')
                                    if suffix=='.json':
                                        saved=load(revision,{})
                                        if any(saved.get(k)!=snapshot.get(k) for k in ('id','revision','tex')):raise ValueError('A saved question revision has changed.')
                                else:changes[revision]=raw
                    if not can_replace:continue
                    if existing is None:index[row[field]]=len(rows);rows.append(deepcopy(row))
                    else:rows[index[row[field]]]=deepcopy(row)
                    records[ident]=sha
            for kind in ('manuals','assets'):
                existing=cat.setdefault(kind,{})
                for ident,row in incoming.get(kind,{}).items():
                    record=kind+'/'+ident;sha=digest(encoded(row))
                    if (ident not in existing and record not in records) or (ident in existing and digest(encoded(existing[ident]))==records.get(record)):
                        existing[ident]=deepcopy(row);records[record]=sha
            if incoming.get('archive_categories'):
                cat['archive_categories']=list(dict.fromkeys(cat.get('archive_categories',[])+incoming['archive_categories']))
        for target,raw in sources.items():
            if target not in protected and owned(target):
                if contents(target)!=raw:changes[target]=raw
                files[key(target)]=digest(raw)
        cat.pop('taxonomy_revision',None)
        changes[catpath]=encoded(cat);changes[state_path]=encoded({'files':files,'records':records})
        for path in changes:checked(data,path.relative_to(data))
        commit(changes)
    return work
