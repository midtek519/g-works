"""Read-only G-Whiz handout links and pinned, locally reviewed solution sources.

No TeX is executed and no URL is fetched. Bounded academic question/solution
excerpts may enter local drafting; only reviewed solutions become grading guidance.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, importlib, json, os, re, secrets, sys


MAX_TEX = 4 * 1024 * 1024
MAX_PDF = 200 * 1024 * 1024
ID = re.compile(r'[a-f0-9]{32}')
BLOCK = re.compile(r'\n?\[G-Scope reviewed solution; version [A-Z]\]\n.*?\n\[/G-Scope reviewed solution\]', re.S)


def stamp(): return datetime.now(timezone.utc).isoformat()
def encoded(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
def digest(value): return hashlib.sha256(value if isinstance(value, bytes) else encoded(value).encode()).hexdigest()
def short(value, maximum=240):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError('Use a short Materials label.')
    return value.strip()


def version_letter(value):
    value = re.sub(r'^version\s+', '', str(value).strip(), flags=re.I).upper()
    if not re.fullmatch('[A-Z]', value):
        raise ValueError('Materials links need a version label A to Z (or Version A to Version Z).')
    return value

def source_title(title,term,version,role,fmt):
    match=re.match(r'(?i)^(?:exam[- _]*(\d+)|final(?:[- _]*exam)?)(?:\b|[-_])',str(title))
    if not match:return str(title)
    parts=['Exam '+match[1] if match[1] else 'Final Exam']
    season={'fa':'Fall','sp':'Spring','su':'Summer','wi':'Winter'}.get(term[:2])
    if season:parts.append(season+' '+str(2000+int(term[2:])))
    if version:parts.append('Version '+version)
    if role=='solutions':parts.append('Solutions')
    if fmt=='tex':parts.append('TeX source')
    return ' · '.join(parts)


def safe_file(path, roots, suffixes):
    """Reject traversal and every lexical link, before resolving the file."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Choose a file from the local Materials catalog.')
    bases = [Path(r).absolute() for r in roots]
    if not any(path.is_relative_to(base) for base in bases):
        raise ValueError('The Materials file is outside its allowed source folder.')
    for node in (path, *path.parents):
        if node.is_symlink() or getattr(node, 'is_junction', lambda: False)():
            raise ValueError('Materials links cannot follow symbolic links or junctions.')
    if not path.is_file() or path.suffix.lower() not in suffixes:
        raise ValueError('The Materials source is unavailable.')
    resolved = path.resolve()
    if not any(resolved.is_relative_to(base.resolve()) for base in bases):
        raise ValueError('The Materials file is outside its allowed source folder.')
    return resolved


def read_bounded(path, maximum):
    if path.stat().st_size > maximum:
        raise ValueError('The Materials source exceeds the supported size.')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('The Materials source exceeds the supported size.')
    return raw


class LocalMaterialsProvider:
    """Use the installed authoring catalog; clients never provide paths/roots."""
    def __init__(self, root, desk=None, library=None):
        self.root = Path(root).absolute()
        if desk is None:
            from integration_paths import teaching_code
            app = teaching_code(self.root)
            for name in ('core', 'toolchain', 'universal', 'authoring'):
                safe_file(app / (name + '.py'), [app], {'.py'})
                loaded = sys.modules.get(name)
                if loaded and Path(loaded.__file__).resolve() != (app / (name + '.py')).resolve():
                    raise ValueError('A different Materials application is already loaded.')
            sys.path.insert(0, str(app))
            try:
                core = importlib.import_module('core')
                universal = importlib.import_module('universal')
                authoring = importlib.import_module('authoring')
                desk = core.Desk(self.root)
                library = authoring.CourseLibrary(desk, universal.Universal(desk))
            finally:
                sys.path.remove(str(app))
        self.desk, self.library = desk, library

    def _entry(self, course, term, origin, identity, role, path, roots, title, version=None, **meta):
        try:
            path = safe_file(path, roots, {'.pdf', '.tex'})
            if path.stat().st_size > (MAX_TEX if path.suffix.lower() == '.tex' else MAX_PDF): return None
        except (ValueError, OSError): return None
        return {'id': digest([course, term, origin, identity])[:32], 'role': role,
                'format': path.suffix.lower()[1:], 'title': short(source_title(title,term,version,role,path.suffix.lower()[1:])[:240]),
                'filename': short(path.name[:240]), 'version': version, 'origin': origin,
                'course': course, 'term': term, **meta, '_path': path, '_roots': roots}

    def _entries(self, course, term):
        module = self.desk.module(course)
        course_root = Path(module.COURSE).absolute()
        if not course_root.is_relative_to(Path(self.desk.repo).absolute()):
            raise ValueError('The course source folder is outside the Materials repository.')
        records = []
        def add(record):
            if record: records.append(record)
        # Exact existing build outputs carry reliable version and pairing metadata.
        builds = self.root / 'Temp' / 'Builds'
        for manifest in sorted(builds.glob('*/result.json'), reverse=True)[:200]:
            try:
                safe_file(manifest, [builds], {'.json'})
                build = json.loads(read_bounded(manifest, MAX_TEX))
                bid = build.get('id', '')
                if not re.fullmatch('[a-f0-9]{16}', bid) or manifest.parent.name != bid: continue
                if str(build.get('course')) != course or build.get('semester') != term: continue
                for index, job in enumerate(build.get('jobs', [])[:250]):
                    if job.get('status') != 'ready' or str(job.get('kind', '')).lower() not in ('exam', 'final exam', 'quiz', 'worksheet'): continue
                    mode = job.get('mode')
                    if mode not in ('student', 'solutions'): continue
                    version = version_letter(job.get('version', 'A'))
                    role = 'handout' if mode == 'student' else 'solutions'
                    assignment = str(job.get('assignment_id') or '')
                    if assignment and not re.fullmatch('A[a-f0-9]{16}', assignment): assignment = ''
                    group = digest(['build', bid, assignment or [job.get('kind'), job.get('publish_number'), re.sub(r'-(?:[A-Z])(?:-sols)?$', '', str(job.get('name', ''))) ]])[:32]
                    metadata = {'buildId': bid, 'assignmentId': assignment, 'groupId': group, 'sourceState': 'saved build PDF'}
                    pdf = self._entry(course, term, 'build', [bid, index, 'pdf'], role,
                                      builds / bid / str(index) / 'document.pdf', [builds / bid],
                                      str(job.get('name', 'Saved handout')), version, **metadata)
                    if pdf:
                        pdf['_expectedHash'] = job.get('pdf_sha256')
                        pdf['_questionRevisions'] = job.get('question_revisions',[])
                    add(pdf)
                    if role == 'solutions':
                        add(self._entry(course, term, 'build-source', [bid, index, 'tex'], 'solutions',
                                        Path(str(job.get('source', ''))), [course_root, self.root / 'Temp' / 'Drafts'],
                                        str(job.get('name', 'Saved solutions')) + ' — TeX source', version,
                                        **{**metadata, 'sourceState': 'current TeX source; review before use'}))
            except (ValueError, OSError, TypeError, KeyError): continue
        catalog = self.desk.catalog(course, term)
        for document in catalog.get('documents', []):
            if str(document.get('kind', '')).lower() not in ('exam', 'final exam', 'quiz', 'worksheet'): continue
            for relative in document.get('source_files', []):
                # A complete source may contain all variants. The authoring default is A.
                path = Path(self.desk.repo) / str(relative)
                add(self._entry(course, term, 'course-source', [document.get('key'), relative], 'solutions',
                                path, [course_root], str(document.get('label', 'Handout')) + ' — TeX source', 'A',
                                groupId=digest(['course', document.get('key')])[:32], buildId='', assignmentId='',
                                sourceState='current TeX source; default solutions Version A'))
        if self.library is not None:
            catalog = self.library.catalog(course, term)
            for document in catalog.get('documents', []):
                if str(document.get('kind', '')).lower() not in ('exam', 'final exam', 'quiz', 'worksheet'): continue
                record = self.library.files.get((course, document.get('id')))
                if not record: continue
                path, base = record
                name = Path(path).stem
                solutions = bool(re.search(r'(?i)(?:-|\s)(?:sols?|solutions)$', name))
                match = re.search(r'-([A-Z])(?:-sols)?$', name, re.I)
                version = match[1].upper() if match else ('A' if solutions else None)
                group = re.sub(r'(?i)-(?:[A-Z])(?:-sols)?$|-sols$', '', name)
                add(self._entry(course, term, 'library', document['id'], 'solutions' if solutions else 'handout',
                                path, [base], document.get('title', name), version,
                                libraryId=document['id'], buildId='', assignmentId='', groupId=digest(['library', group])[:32],
                                sourceState='current published or source PDF'))
        for record in records:
            record['pairedSourceIds'] = [r['id'] for r in records if r['groupId'] == record['groupId'] and r['id'] != record['id']]
        return records

    def catalog(self, course, term):
        return [{k: v for k, v in row.items() if not k.startswith('_')} for row in self._entries(course, term)]

    def _output_entries(self,course,term):
        semester,_=self.desk.module(course).semester_info(term)
        folder=Path(self.desk.output_root(course))/semester
        if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():raise ValueError('The semester output folder cannot be a directory link.')
        records=[]
        if folder.is_dir():
            for path in folder.rglob('*'):
                if path.suffix.lower() not in ('.pdf','.tex'):continue
                relative=path.relative_to(folder).as_posix()
                role='solutions' if re.search(r'(?i)(?:[-_\s])(?:sols?|solutions|answers?|answer[-_\s]?key)(?:\b|[-_\s])',path.stem) else 'handout'
                if role=='handout' and path.suffix.lower()!='.pdf':continue
                match=re.search(r'(?i)[-_\s]([A-Z])(?:[-_\s](?:sols?|solutions|answers?))?$',path.stem)
                version=match[1].upper() if match else ('A' if role=='solutions' else None)
                group=re.sub(r'(?i)[-_\s][A-Z](?:[-_\s](?:sols?|solutions|answers?))?$','',path.stem)
                row=self._entry(course,term,'output-folder',relative,role,path,[folder],path.stem,version,groupId=digest(['output',group])[:32],buildId='',assignmentId='',relativePath=relative,sourceState='semester output folder')
                if row:records.append(row)
        records.sort(key=lambda r:(r['filename'].casefold(),r['relativePath'].casefold()))
        for row in records:row['pairedSourceIds']=[r['id'] for r in records if r['id']!=row['id'] and r['groupId']==row['groupId']]
        return folder,records

    def output_catalog(self,course,term):
        folder,rows=self._output_entries(course,term)
        return {'outputFolder':str(folder),'sources':[{k:v for k,v in row.items() if not k.startswith('_')} for row in rows]}

    def blank_question_tex(self,course,term,blank_sha):
        """Match exact built PDF bytes to its saved question revisions, never current assignments."""
        from answer_context import blank_tex
        universal=getattr(self.library,'universal',None)
        if not universal:return {}
        candidates=[r for r in self._entries(course,term) if r['role']=='handout' and r.get('_expectedHash')==blank_sha and r.get('_questionRevisions')]
        if not candidates:return {}
        cat=universal._catalog();results=[]
        for row in candidates[:4]:
            if digest(read_bounded(safe_file(row['_path'],row['_roots'],{'.pdf'}),MAX_PDF))!=blank_sha:continue
            sections={}
            for index,revision in enumerate(row['_questionRevisions'],1):
                try:
                    question=universal._question_revision(cat,revision['id'],revision['revision'])
                    # The question field contains its full preamble and all parts.
                    source=question.get('question')
                    if source is None:source=universal._tex(question)
                    text=blank_tex(source,row['version'])
                    diagram=re.search(r'(?i)\b(?:graph|figure|diagram|sketch|plotted|shown\s+(?:above|below))\b|\\(?:begin\s*\{(?:tikzpicture|ctikz|axis|pspicture)|includegraphics|draw|addplot|[A-Za-z]*(?:graph|figure|axes|plot)[A-Za-z]*)\b',text)
                    sections[str(index)]={'text':text,'needsImage':bool(question.get('prefix','').strip() or diagram)}
                except (ValueError,KeyError,OSError,TypeError):continue
            results.append(sections)
        if not results or any(r!=results[0] for r in results[1:]):return {}
        return results[0]

    def read(self, course, term, source_id):
        if not isinstance(source_id, str) or not ID.fullmatch(source_id): raise ValueError('Choose a Materials catalog item.')
        _,outputs=self._output_entries(course,term) if hasattr(self.desk,'output_root') else (None,[])
        matches = [row for row in outputs if row['id']==source_id]
        if not matches:matches = [row for row in self._entries(course, term) if row['id'] == source_id]
        if len(matches) != 1: raise ValueError('Refresh the Materials catalog and choose an available source.')
        row = matches[0]
        path = safe_file(row['_path'], row['_roots'], {'.pdf', '.tex'})
        raw = read_bounded(path, MAX_TEX if row['format'] == 'tex' else MAX_PDF)
        if row.get('_expectedHash') and digest(raw) != row['_expectedHash']:
            raise ValueError('The saved build PDF changed. Choose a freshly compiled source.')
        return {k: v for k, v in row.items() if not k.startswith('_')}, raw


class MaterialsLinks:
    def materials_init(self, provider=None):
        self.materials_provider = provider
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS material_pdf_previews(reference_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS material_references(
              id TEXT PRIMARY KEY, version_id TEXT NOT NULL, role TEXT NOT NULL,
              source_id TEXT NOT NULL, sha256 TEXT NOT NULL, format TEXT NOT NULL,
              metadata TEXT NOT NULL, created TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS material_solution_applications(
              id TEXT PRIMARY KEY, version_id TEXT NOT NULL, reference_id TEXT NOT NULL,
              mappings_hash TEXT NOT NULL, created TEXT NOT NULL);
            ''')

    def _materials_provider(self):
        if self.materials_provider is None:
            self.materials_provider = LocalMaterialsProvider(__import__('integration_paths').materials_root())
        return self.materials_provider

    def blank_question_context(self,vid,handout):
        version,project,letter=self._materials_context(vid)
        for row in self.rows("SELECT * FROM material_references WHERE version_id=? AND role='handout' AND active=1",(vid,)):
            meta=json.loads(row['metadata']);expected=meta.get('questionContextSha256')
            if row['sha256']!=handout['sha256'] or not expected:continue
            path=self._materials_path(row).with_name(row['id']+'-questions.json')
            raw=read_bounded(safe_file(path,[path.parent],{'.json'}),MAX_TEX)
            if digest(raw)!=expected:raise ValueError('The pinned question TeX changed. Replace the linked blank exam source.')
            data=json.loads(raw)
            if not isinstance(data,dict) or any(not re.fullmatch(r'\d{1,3}',key) or not isinstance(value,dict) or not isinstance(value.get('text'),str) or len(value['text'])>16000 or not isinstance(value.get('needsImage'),bool) for key,value in data.items()):raise ValueError('The pinned question TeX is invalid.')
            return data
        provider=self._materials_provider()
        return provider.blank_question_tex(project['course'],project['term'],handout['sha256']) if hasattr(provider,'blank_question_tex') else {}

    def _materials_context(self, vid):
        row = self.one('versions', vid); project = self.one('projects', row['project_id'])
        return row, project, version_letter(row['label'])

    def materials_catalog(self, vid):
        version, project, letter = self._materials_context(vid)
        provider=self._materials_provider()
        listing=provider.output_catalog(project['course'],project['term']) if hasattr(provider,'output_catalog') else {'sources':provider.catalog(project['course'],project['term'])}
        return {'course': project['course'], 'term': project['term'], 'version': letter,
                'defaultSolutionsVersion': 'A', 'handoutBuilds':self.handout_builds(vid)['builds'], **listing}

    def materials_source(self, vid, source_id):
        _, project, _ = self._materials_context(vid)
        metadata, raw = self._materials_provider().read(project['course'], project['term'], source_id)
        result = {**metadata, 'sha256': digest(raw), 'bytes': len(raw)}
        if metadata['format'] == 'tex': result['text'] = raw.decode('utf-8-sig', errors='replace')
        return result

    def materials_source_pdf(self,vid,source_id):
        # Read the selected catalog item without linking or compiling anything.
        _,project,_=self._materials_context(vid)
        metadata,raw=self._materials_provider().read(project['course'],project['term'],source_id)
        if metadata['format']!='pdf':raise ValueError('Choose a PDF source to preview.')
        if not raw.startswith(b'%PDF-'):raise ValueError('This source is not a readable PDF.')
        return raw

    def materials_list(self, vid):
        self.one('versions', vid)
        rows = self.rows('SELECT * FROM material_references WHERE version_id=? AND active=1 ORDER BY rowid', (vid,))
        result = []
        for row in rows:
            meta = json.loads(row['metadata'])
            result.append({'id': row['id'], 'role': row['role'], 'sourceId': row['source_id'],
                           'sha256': row['sha256'], 'format': row['format'], 'created': row['created'],
                           'pinned': True, **meta})
        return {'references': result}

    def _materials_path(self, row):
        path = self.root / 'Projects' / row['version_id'] / 'Materials' / (row['id'] + '.' + row['format'])
        return safe_file(path, [self.root / 'Projects' / row['version_id'] / 'Materials'], {'.pdf', '.tex'})

    def _materials_reference_bytes(self, vid, reference_id):
        self.one('versions', vid)
        rows=self.rows('SELECT * FROM material_references WHERE id=? AND version_id=? AND active=1',(reference_id,vid))
        if len(rows)!=1:raise ValueError('Choose a current file linked to this version.')
        row=rows[0];raw=read_bounded(self._materials_path(row),MAX_TEX if row['format']=='tex' else MAX_PDF)
        if digest(raw)!=row['sha256']:raise ValueError('The saved file changed. Replace it with a current copy.')
        return row,raw

    def materials_reference(self, vid, reference_id):
        row,raw=self._materials_reference_bytes(vid,reference_id)
        result={'id':row['id'],'sha256':row['sha256'],'role':row['role'],'format':row['format'],**json.loads(row['metadata'])}
        if row['format']=='tex':result['text']=raw.decode('utf-8-sig',errors='replace')
        return result

    def materials_pdf(self,vid,reference_id):
        with self.lock:
            row,raw=self._materials_reference_bytes(vid,reference_id)
            if row['format']=='pdf':return raw
            preview=self.rows('SELECT sha256 FROM material_pdf_previews WHERE reference_id=?',(reference_id,))
            path=self.root/'Projects'/vid/'Materials'/(reference_id+'-preview.pdf')
            if preview:
                raw=read_bounded(safe_file(path,[path.parent],{'.pdf'}),MAX_PDF)
                if digest(raw)!=preview[0]['sha256']:raise ValueError('The saved PDF preview changed. Replace this solutions source.')
                return raw
            # Existing TeX links may predate saved PDF previews. Only use the
            # matching compiled build, and only while its TeX is unchanged.
            _,project,_=self._materials_context(vid);provider=self._materials_provider();meta=json.loads(row['metadata'])
            if not meta.get('buildId'):raise ValueError('This TeX file has no compiled PDF. Answer-key drafts are available in Rubrics & answer keys.')
            source,source_raw=provider.read(project['course'],project['term'],row['source_id'])
            if digest(source_raw)!=row['sha256']:raise ValueError('The original solutions source changed after it was linked. Replace it before previewing its PDF.')
            matches=[item for item in provider.catalog(project['course'],project['term']) if item.get('format')=='pdf' and item.get('role')=='solutions' and item.get('buildId')==meta['buildId'] and item.get('groupId')==source.get('groupId') and item.get('version')==meta.get('sourceVersion')]
            if len(matches)!=1:raise ValueError('The compiled solutions PDF is no longer available. Answer-key drafts can still use the saved TeX.')
            _,raw=provider.read(project['course'],project['term'],matches[0]['id'])
            path=self._archive_safe_path(path)
            if path.exists():
                if digest(read_bounded(safe_file(path,[path.parent],{'.pdf'}),MAX_PDF))!=digest(raw):raise ValueError('The saved PDF preview changed. Replace this solutions source.')
            else:
                with path.open('xb') as stream:stream.write(raw)
            with self.connect() as db:db.execute('INSERT INTO material_pdf_previews VALUES(?,?)',(reference_id,digest(raw)))
            return raw

    def materials_remove(self,vid,reference_id,payload):
        if payload.get('confirmed') is not True:raise ValueError('Confirm removal of this linked file.')
        return self._materials_change(vid,reference_id,payload.get('sha256'))

    def materials_replace(self,vid,reference_id,name,raw,sha):
        return self._materials_change(vid,reference_id,sha,(name,raw))

    def _materials_change(self,vid,reference_id,sha,replacement=None):
        with self.lock:
            self._archive_idle();self.writable(vid)
            rows=self.rows('SELECT * FROM material_references WHERE id=? AND version_id=? AND active=1',(reference_id,vid))
            if len(rows)!=1:raise ValueError('Choose the current linked file.')
            row=rows[0]
            if sha!=row['sha256']:raise ValueError('This file selection changed. Reload before editing it.')
            role=row['role'];new=None;pages=0;fid=None
            if replacement:
                name,raw=replacement;name=short(Path(name).name,240);fmt=Path(name).suffix.lower().lstrip('.')
                if fmt not in ('pdf','tex') or role=='handout' and fmt!='pdf':raise ValueError('Use a blank-exam PDF or a solutions PDF/TeX file.')
                if not raw or len(raw)>(MAX_TEX if fmt=='tex' else MAX_PDF):raise ValueError('Choose a nonempty file within the supported size.')
                if fmt=='pdf':
                    import pypdfium2 as pdfium
                    try:
                        pdf=pdfium.PdfDocument(raw);pages=len(pdf);pdf.close()
                        if not raw.startswith(b'%PDF-') or not 1<=pages<=10000:raise ValueError()
                    except Exception:raise ValueError('The replacement PDF could not be read.') from None
                else:
                    try:text=raw.decode('utf-8-sig')
                    except UnicodeDecodeError:raise ValueError('Use a UTF-8 TeX source file.') from None
                    if not text.strip() or '\x00' in text:raise ValueError('Use a readable TeX source file.')
                if digest(raw)==row['sha256'] and fmt==row['format']:return {'version':self.version(vid),**self.materials_list(vid),'unchanged':True}
                if role=='handout':
                    pid=self.one('versions',vid)['project_id'];settings=self.rows('SELECT pages FROM project_scan_settings WHERE project_id=?',(pid,))
                    if settings and settings[0]['pages']!=pages and self.rows("SELECT id FROM scan_sources WHERE project_id=? AND deleted=''",(pid,)):raise ValueError('This project already has scans. The replacement blank must have the same number of pages per exam.')
                ident=secrets.token_hex(16);folder=self._archive_safe_path(self.root/'Projects'/vid/'Materials');folder.mkdir(parents=True,exist_ok=True)
                with (folder/(ident+'.'+fmt)).open('xb') as stream:stream.write(raw)
                letter=version_letter(self.one('versions',vid)['label']);meta={'title':name,'filename':name,'origin':'external-upload','sourceVersion':letter,'applicableVersion':letter,'versionConfirmed':True}
                new=(ident,vid,role,'external-'+ident,digest(raw),fmt,encoded(meta),stamp())
                if role=='handout':
                    fid=secrets.token_hex(16);folder=self._archive_safe_path(self.root/'Projects'/vid/'Files');folder.mkdir(parents=True,exist_ok=True)
                    with (folder/(fid+'.pdf')).open('xb') as stream:stream.write(raw)
            active_blanks=self.rows("SELECT * FROM files WHERE version_id=? AND kind='handout' AND archived=''",(vid,))
            changes_blank=role=='handout' and (replacement or any(f['sha256']==row['sha256'] for f in active_blanks))
            with self.connect() as db:
                db.execute('UPDATE material_references SET active=0 WHERE id=?',(reference_id,))
                if new:db.execute('INSERT INTO material_references VALUES(?,?,?,?,?,?,?,?,1)',new)
                if changes_blank:
                    db.execute("UPDATE files SET archived=? WHERE version_id=? AND kind='handout' AND archived=''",(stamp(),vid))
                    if fid:db.execute('INSERT INTO files(id,version_id,kind,name,sha256,pages) VALUES(?,?,?,?,?,?)',(fid,vid,'handout',name,digest(raw),pages))
                    db.execute('UPDATE scan_layouts SET approved=0 WHERE version_id=?',(vid,))
                for qrow in db.execute('SELECT id,data FROM questions WHERE version_id=?',(vid,)).fetchall():
                    q=json.loads(qrow['data']);q['guidance']=BLOCK.sub('',q.get('guidance','')).rstrip()
                    if changes_blank:q.update(rect=None,checkedFiles=[],page=min(q.get('page',1),pages) if pages else q.get('page',1))
                    db.execute('UPDATE questions SET data=? WHERE id=?',(encoded(q),qrow['id']))
                db.execute("UPDATE versions SET rubric_approved='' WHERE id=?",(vid,))
                self.event(db,'exam-file-replaced' if new else 'exam-file-removed',vid,{'referenceId':reference_id,'role':role,'replacementId':new[0] if new else None,'retainedOriginal':True})
            return {'version':self.version(vid),**self.materials_list(vid)}

    def materials_link(self, vid, payload):
        with self.lock:
            self.writable(vid)
            version, project, target = self._materials_context(vid)
            if version_letter(payload.get('targetVersion', target)) != target: raise ValueError('Confirm the target exam version.')
            source_id = payload.get('sourceId')
            metadata, raw = self._materials_provider().read(project['course'], project['term'], source_id)
            sha = digest(raw)
            if payload.get('sha256') != sha: raise ValueError('The Materials source changed. Preview it again before linking.')
            role = payload.get('role', metadata['role'])
            if role not in ('handout', 'solutions') or role != metadata['role']: raise ValueError('Choose the matching handout or solutions source.')
            source_version = metadata.get('version') or ('A' if role == 'solutions' else None)
            if (source_version != target) and payload.get('versionConfirmed') is not True:
                raise ValueError('Confirm this source belongs to the selected exam version; solutions default to A.')
            if metadata.get('course') != project['course'] or metadata.get('term') != project['term']:
                raise ValueError('The Materials source must match this course and semester.')
            fmt = metadata['format']
            if fmt not in ('pdf', 'tex') or (role == 'handout' and fmt != 'pdf'): raise ValueError('Choose a handout PDF or a solutions source.')
            question_context=None
            if role=='handout':
                provider=self._materials_provider()
                if hasattr(provider,'blank_question_tex'):
                    try:question_context=provider.blank_question_tex(project['course'],project['term'],sha)
                    except (ValueError,OSError):pass
            snapshot=None
            if role=='solutions' and fmt=='tex':
                from solution_sources import snapshot_tex
                provider=self._materials_provider()
                snapshot=snapshot_tex(raw,getattr(provider,'root',__import__('integration_paths').materials_root()),managed=metadata.get('origin')=='build-source')
            ident = secrets.token_hex(16)
            folder = self.root / 'Projects' / vid / 'Materials'
            # The directory is private and fixed. Validate it before writing a new name.
            for node in (folder, *folder.parents):
                if node.is_symlink() or getattr(node, 'is_junction', lambda: False)(): raise ValueError('Materials storage cannot use a link or junction.')
            folder.mkdir(parents=True, exist_ok=True)
            target_path = folder / (ident + '.' + fmt)
            with target_path.open('xb') as stream: stream.write(raw)
            meta = {k: short(str(metadata.get(k, '')), 240) for k in ('title', 'filename', 'origin', 'groupId', 'buildId', 'assignmentId', 'libraryId', 'sourceState')}
            meta.update(sourceVersion=source_version, applicableVersion=target, versionConfirmed=payload.get('versionConfirmed') is True)
            if question_context:
                context_raw=encoded(question_context).encode('utf-8')
                if len(context_raw)<=MAX_TEX:
                    with (folder/(ident+'-questions.json')).open('xb') as stream:stream.write(context_raw)
                    meta['questionContextSha256']=digest(context_raw)
            if snapshot is not None and snapshot!=raw:
                with (folder/(ident+'-solutions.tex')).open('xb') as stream:stream.write(snapshot)
                meta['solutionSnapshotSha256']=digest(snapshot)
            if role == 'solutions':
                # A new link must never appear to authorize the old answer text.
                questions = deepcopy(self.version(vid)['questions']); changed = False
                for question in questions:
                    previous = question.get('guidance', '')
                    question['guidance'] = BLOCK.sub('', previous).rstrip()
                    changed = changed or previous != question['guidance']
                if changed: self.save_questions(vid, {'questions': questions})
            with self.connect() as db:
                db.execute('UPDATE material_references SET active=0 WHERE version_id=? AND role=?', (vid, role))
                db.execute('INSERT INTO material_references VALUES(?,?,?,?,?,?,?,?,1)', (ident, vid, role, source_id, sha, fmt, encoded(meta), stamp()))
                self.event(db, 'materials-linked', vid, {'referenceId': ident, 'role': role, 'sha256': sha, 'version': target})
            return self.materials_list(vid)

    def materials_use_handout(self, vid, payload):
        with self.lock:
            self.writable(vid)
            if payload.get('confirmed') is not True: raise ValueError('Confirm use of this linked PDF as the blank template.')
            source = self.materials_reference(vid, payload.get('referenceId'))
            if source['role'] != 'handout' or source['format'] != 'pdf' or source['sha256'] != payload.get('sha256'):
                raise ValueError('Choose the current linked handout PDF.')
            existing = [f for f in self.version(vid)['files'] if f['kind'] == 'handout']
            if existing:
                if len(existing) != 1 or existing[0]['sha256'] != source['sha256']:
                    raise ValueError('This version already has a different handout. Keep its crops and use a new version for a replacement.')
                return self.version(vid)
            row = self.rows('SELECT * FROM material_references WHERE id=? AND version_id=?', (source['id'], vid))[0]
            raw = read_bounded(self._materials_path(row), MAX_PDF)
            if digest(raw) != source['sha256']: raise ValueError('The pinned handout changed. Relink its source.')
            return self.upload(vid, 'handout', source['filename'], raw)

    def materials_upload(self,vid,name,raw,role):
        with self.lock:
            self.writable(vid);_,_,letter=self._materials_context(vid)
            if role not in ('handout','solutions'):raise ValueError('Choose whether this PDF is a blank exam or solutions.')
            name=short(Path(name).name,240)
            if not name.lower().endswith('.pdf') or not raw.startswith(b'%PDF-') or len(raw)>MAX_PDF:raise ValueError('Choose a readable PDF up to 200 MB.')
            import pypdfium2 as pdfium
            try:
                pdf=pdfium.PdfDocument(raw);pages=len(pdf);pdf.close()
                if not 1<=pages<=10000:raise ValueError()
            except Exception:raise ValueError('The selected PDF could not be read.') from None
            sha=digest(raw)
            previous=next((r for r in self.materials_list(vid)['references'] if r['role']==role and r['sha256']==sha),None)
            if previous:return {'version':self.version(vid),**self.materials_list(vid),'role':role}
            if role=='handout':self.upload(vid,'handout',name,raw)
            ident=secrets.token_hex(16);folder=self._archive_safe_path(self.root/'Projects'/vid/'Materials');folder.mkdir(parents=True,exist_ok=True)
            self._archive_safe_path(folder/(ident+'.pdf')).write_bytes(raw)
            meta={'title':name,'filename':name,'origin':'external-upload','groupId':'','buildId':'','assignmentId':'','sourceState':'uploaded external PDF','sourceVersion':letter,'applicableVersion':letter,'versionConfirmed':True}
            if role=='solutions':
                questions=deepcopy(self.version(vid)['questions']);changed=False
                for q in questions:
                    before=q.get('guidance','');q['guidance']=BLOCK.sub('',before).rstrip();changed=changed or before!=q['guidance']
                if changed:self.save_questions(vid,{'questions':questions})
            with self.connect() as db:
                db.execute('UPDATE material_references SET active=0 WHERE version_id=? AND role=?',(vid,role));db.execute('INSERT INTO material_references VALUES(?,?,?,?,?,?,?,?,1)',(ident,vid,role,'external-'+ident,sha,'pdf',encoded(meta),stamp()));self.event(db,'external-exam-file-linked',vid,{'role':role,'sha256':sha})
            return {'version':self.version(vid),**self.materials_list(vid),'role':role}

    def materials_solutions(self, vid, payload):
        with self.lock:
            self.writable(vid)
            _, _, letter = self._materials_context(vid)
            if payload.get('reviewed') is not True or version_letter(payload.get('targetVersion', '')) != letter:
                raise ValueError('Review the question solutions and confirm their target version first.')
            source = self.materials_reference(vid, payload.get('referenceId'))
            if source['role'] != 'solutions' or source['applicableVersion'] != letter or source['sha256'] != payload.get('sha256'):
                raise ValueError('Choose and review the current solutions reference for this version.')
            mappings = payload.get('mappings')
            if not isinstance(mappings, list) or not 1 <= len(mappings) <= 100: raise ValueError('Map a reviewed solution to at least one question.')
            version = self.version(vid); questions = deepcopy(version['questions']); by_key = {q['key']: q for q in questions}; seen = set(); cleaned = []
            for mapping in mappings:
                if not isinstance(mapping, dict) or set(mapping) != {'questionKey', 'text'}: raise ValueError('Use a question key and reviewed solution text.')
                qkey, text = mapping['questionKey'], mapping['text']
                if not isinstance(qkey, str) or qkey not in by_key or qkey in seen: raise ValueError('Choose each existing question once.')
                if not isinstance(text, str) or not text.strip() or len(text) > 8000 or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
                    raise ValueError('Keep each reviewed solution between 1 and 8,000 characters.')
                # Do not import document wrappers, includes, file operations, or arbitrary full TeX.
                if re.search(r'\\(?:documentclass|usepackage|input|include|openout|openin|write|read|catcode|directlua|immediate|special|csname)\b|\\(?:begin|end)\s*\{document\}', text, re.I) or '[G-Scope reviewed solution' in text or '[/G-Scope reviewed solution]' in text:
                    raise ValueError('Paste the reviewed mathematical answer only, without document commands or file operations.')
                seen.add(qkey); text = text.strip()
                previous = BLOCK.sub('', by_key[qkey].get('guidance', '')).rstrip()
                guidance = previous + '\n[G-Scope reviewed solution; version ' + letter + ']\n' + text + '\n[/G-Scope reviewed solution]'
                if len(guidance) > 12000: raise ValueError('The solution and existing question guidance exceed 12,000 characters.')
                by_key[qkey]['guidance'] = guidance; cleaned.append({'questionKey': qkey, 'text': text})
            result = self.save_questions(vid, {'questions': questions})
            with self.connect() as db:
                db.execute('INSERT INTO material_solution_applications VALUES(?,?,?,?,?)', (secrets.token_hex(16), vid, source['id'], digest(cleaned), stamp()))
                self.event(db, 'materials-solutions-reviewed', vid, {'referenceId': source['id'], 'questions': len(cleaned), 'version': letter})
            return result

    def materials_snapshot(self, vid):
        # Reference IDs, paths and raw TeX never enter the grading prompt or Lens export.
        result = []
        for row in self.rows('SELECT * FROM material_references WHERE version_id=? AND active=1 ORDER BY role', (vid,)):
            metadata = json.loads(row['metadata'])
            state = {'role': row['role'], 'sha256': row['sha256'], 'version': metadata['applicableVersion']}
            try:
                raw = read_bounded(self._materials_path(row), MAX_TEX if row['format'] == 'tex' else MAX_PDF)
                if digest(raw) != row['sha256']: state['unavailable'] = True
            except (ValueError, OSError): state['unavailable'] = True
            result.append(state)
        return result

    def materials_validate(self, vid):
        if any(row.get('unavailable') for row in self.materials_snapshot(vid)):
            raise ValueError('A pinned Materials source is missing or changed. Relink and review it before processing.')
