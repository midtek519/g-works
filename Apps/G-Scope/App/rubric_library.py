"""A fixed local rubric inbox plus reusable, reviewed question-card templates."""
from pathlib import Path
from datetime import datetime, timezone
import errno,hashlib,json,os,re,secrets

def stamp():return datetime.now(timezone.utc).isoformat()
from rubric_export import validate_export,export_questions,reviewed_export

def text_id(text,version=1):return hashlib.sha256((('rubric-v2\n' if version==2 else '')+text).encode('utf-8')).hexdigest()

def windows_downloads():
    # Read the Windows known-folder location, never Chrome settings or profiles.
    if os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                value,_=winreg.QueryValueEx(key,'{374DE290-123F-4565-9164-39C4925E467B}')
            if isinstance(value,str) and value:return Path(os.path.expandvars(value))
        except OSError:pass
    return Path.home()/'Downloads'

class RubricLibrary:
    def library_init(self):
        folder=self.root/'Rubrics'
        if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():raise ValueError('Use the installed local rubric library folder.')
        folder.mkdir(exist_ok=True);self.rubric_folder=folder;self.rubric_downloads_folder=windows_downloads()/'G-Rater'/'Rubrics'
        with self.connect() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS rubric_library(id TEXT PRIMARY KEY,title TEXT NOT NULL,filename TEXT NOT NULL,questions TEXT NOT NULL DEFAULT '[]',created TEXT NOT NULL,updated TEXT NOT NULL,deleted TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS rubric_download_imports(source TEXT PRIMARY KEY,sha256 TEXT NOT NULL,rubric_id TEXT NOT NULL,imported TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rubric_metadata_migrations(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS version_structured_rubrics(version_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS version_rubric_outline(version_id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS version_rubrics(version_id TEXT PRIMARY KEY,rubric_id TEXT NOT NULL,applied TEXT NOT NULL);
        ''')
        # Recover the structured marker for exports loaded by the earlier 0.6
        # build, which already stored their hierarchy but had no marker table.
        if not self.rows("SELECT name FROM rubric_metadata_migrations WHERE name='structured-marker'"):
            for row in self.rows('SELECT v.id,v.raw_rubric,o.data FROM versions v JOIN version_rubric_outline o ON o.version_id=v.id LEFT JOIN version_structured_rubrics s ON s.version_id=v.id WHERE s.version_id IS NULL'):
                try:
                    data=json.loads(row['raw_rubric'])
                    value=validate_export({'format':'g-rater-rubric-export','version':2,'title':'','text':row['raw_rubric'],**data})
                    if value['outline']!=json.loads(row['data']):continue
                    saved={json.loads(q['data'])['key']:json.loads(q['data']) for q in self.rows('SELECT data FROM questions WHERE version_id=?',(row['id'],))}
                    if all(q['key'] in saved and saved[q['key']]['items'] for q in value['questions']):
                        with self.connect() as db:db.execute('INSERT OR IGNORE INTO version_structured_rubrics VALUES(?)',(row['id'],))
                except (ValueError,KeyError,TypeError):continue
            with self.connect() as db:db.execute("INSERT OR IGNORE INTO rubric_metadata_migrations VALUES('structured-marker')")
    def open_rubric_folder(self):
        # Fixed managed directory only. Never accept a path or command from the client.
        folder=self._archive_safe_path(self.rubric_folder)
        if not folder.is_dir():raise ValueError('The rubric folder is unavailable.')
        os.startfile(str(folder))
        return {'opened':True}
    def _rubric_files(self):
        for index,path in enumerate(sorted(self.rubric_folder.glob('*.json'))):
            if index>=1000:break
            if path.is_symlink() or path.stat().st_size>1_000_000:continue
            try:
                value=validate_export(json.loads(path.read_text('utf-8-sig')))
                yield path,value,text_id(value['text'],value['version'])
            except (ValueError,OSError,UnicodeError):continue
    def _receive_browser_rubric(self,value,rid):
        target=self.rubric_folder/('rubric-'+rid+'.json')
        def existing():
            if target.is_symlink() or getattr(target,'is_junction',lambda:False)() or target.stat().st_size>1_000_000:raise ValueError('The saved rubric file needs local review.')
            old=validate_export(json.loads(target.read_text('utf-8-sig')))
            if text_id(old['text'],old['version'])!=rid:raise ValueError('The saved rubric file changed unexpectedly.')
        if target.exists():existing();return
        temp=self.rubric_folder/('.browser-'+secrets.token_hex(12)+'.tmp')
        try:
            raw=(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')
            with temp.open('xb') as file:file.write(raw)
            try:os.link(temp,target)
            except FileExistsError:existing()
            except OSError as error:
                if error.errno not in (errno.EPERM,errno.EACCES,errno.ENOTSUP,errno.EXDEV):raise
                try:
                    with target.open('xb') as file:file.write(raw)
                except FileExistsError:existing()
        finally:
            if temp.exists():temp.unlink()
    def _import_browser_exports(self):
        folder=self.rubric_downloads_folder
        # Scan only the named inbox, with no recursion or symlink/junction exits.
        if any(part.is_symlink() or getattr(part,'is_junction',lambda:False)() for part in (folder.parent,folder)):return
        if not folder.is_dir():return
        pattern=re.compile(r'g-rater-([a-f0-9]{64})(?: \(\d+\))?\.json')
        for index,path in enumerate(sorted(folder.glob('*.json'))):
            if index>=1000:break
            match=pattern.fullmatch(path.name)
            if path.name.startswith('g-rater-') and not match:continue
            try:
                if path.is_symlink() or not path.is_file() or path.resolve().parent!=folder.resolve() or path.stat().st_size>1_000_000:continue
                raw=path.read_bytes()
                if len(raw)>1_000_000:continue
                digest=hashlib.sha256(raw).hexdigest()
                previous=self.rows('SELECT sha256 FROM rubric_download_imports WHERE source=?',(path.name,))
                if previous and previous[0]['sha256']==digest:continue
                value=validate_export(json.loads(raw.decode('utf-8-sig')));rid=text_id(value['text'],value['version'])
                if match and rid!=match[1]:continue
                self._receive_browser_rubric(value,rid)
                with self.connect() as db:db.execute('INSERT OR REPLACE INTO rubric_download_imports VALUES(?,?,?,?)',(path.name,digest,rid,stamp()))
            except (ValueError,OSError,UnicodeError):continue
    def library_scan(self):
        with self.lock:
            self._import_browser_exports()
            found={}
            for path,value,rid in self._rubric_files():
                # Prefer the connector's canonical filename if there are manual duplicates.
                if rid not in found or path.name=='rubric-'+rid+'.json':found[rid]=(path,value)
            with self.connect() as db:
                for rid,(path,value) in found.items():
                    previous=db.execute('SELECT * FROM rubric_library WHERE id=?',(rid,)).fetchone()
                    if not previous:db.execute('INSERT INTO rubric_library(id,title,filename,created,updated) VALUES(?,?,?,?,?)',(rid,value['title'],path.name,stamp(),stamp()))
                    elif previous['title']!=value['title'] or previous['filename']!=path.name or previous['deleted']:db.execute("UPDATE rubric_library SET title=?,filename=?,updated=?,deleted='' WHERE id=?",(value['title'],path.name,stamp(),rid))
                # Missing files are not silently used from a database cache.
                for row in db.execute("SELECT id FROM rubric_library WHERE deleted='' ").fetchall():
                    if row['id'] not in found:db.execute('UPDATE rubric_library SET deleted=? WHERE id=?',(stamp(),row['id']))
            return found
    def library_list(self):
        found=self.library_scan()
        rows=self.rows("SELECT id,title,created,updated,questions FROM rubric_library WHERE deleted='' ORDER BY updated DESC")
        for row in rows:
            questions=json.loads(row.pop('questions'));row['questionCount']=len(questions);row['prepared']=bool(questions)
            value=found[row['id']][1];row['structured']=value['version']==2
            if row['structured']:row['questionCount']=len(value['questions'])
        return {'items':rows}
    def _library_entry(self,rid):
        if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{64}',rid):raise ValueError('Choose a saved rubric.')
        found=self.library_scan()
        if rid not in found:raise ValueError('This saved rubric is unavailable. Refresh the library.')
        row=self.rows("SELECT * FROM rubric_library WHERE id=? AND deleted=''",(rid,))[0]
        path,value=found[rid];return row,path,value
    def library_get(self,rid):
        row,_,value=self._library_entry(rid)
        questions=json.loads(row['questions'])
        supported=True
        if value['version']==2:
            try:questions=export_questions(value)
            except ValueError:supported=False;questions=[]
        return {'id':rid,'title':row['title'],'text':value['text'],'questions':questions,'structured':value['version']==2,'supported':supported,'outline':value.get('outline',[])}
    def _write_rubric(self,path,value):
        if path.parent.resolve()!=self.rubric_folder.resolve() or path.is_symlink():raise ValueError('Use the local rubric library.')
        temp=self.rubric_folder/('.save-'+secrets.token_hex(12)+'.tmp')
        try:
            temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n','utf-8');os.replace(temp,path)
        finally:
            if temp.exists():temp.unlink()
    def library_import(self,payload):
        value=validate_export(payload);rid=text_id(value['text'],value['version']);found=self.library_scan()
        if rid not in found:self._write_rubric(self.rubric_folder/('rubric-'+rid+'.json'),value)
        return self.library_get(rid)
    def library_rename(self,rid,payload):
        _,_,value=self._library_entry(rid);title=payload.get('title')
        if not isinstance(title,str) or not title.strip() or len(title)>160:raise ValueError('Enter a rubric title up to 160 characters.')
        # Rename is a title change; filenames remain opaque and cannot be paths.
        for path,other,identity in list(self._rubric_files()):
            if identity==rid:self._write_rubric(path,{**other,'title':title.strip()})
        return self.library_get(rid)
    def library_delete(self,rid,payload):
        self._library_entry(rid)
        if payload.get('confirmed') is not True:raise ValueError('Confirm deleting this rubric from the library.')
        trash=self.rubric_folder/'Trash'
        if trash.is_symlink() or getattr(trash,'is_junction',lambda:False)():raise ValueError('Use the local library trash folder.')
        trash.mkdir(exist_ok=True)
        for path,_,identity in list(self._rubric_files()):
            if identity==rid:os.replace(path,trash/(secrets.token_hex(12)+'-'+path.name))
        with self.connect() as db:db.execute('UPDATE rubric_library SET deleted=? WHERE id=?',(stamp(),rid))
        return {'deleted':True,'existingExamCopiesRetained':True}
    def import_export(self,vid,payload):
        value=validate_export(payload);self.one('versions',vid);self.writable(vid)
        extracted=export_questions(value)
        previous=self.version(vid)['questions'];by_key={q['key']:q for q in previous}
        self.import_rubric(vid,{'text':value['text']})
        if extracted is not None:
            # The validated incoming tree is authoritative for parent summaries.
            with self.connect() as db:db.execute('DELETE FROM version_rubric_outline WHERE version_id=?',(vid,))
            parent_keys={n['key'] for n in value['outline'] if not n['graded']}
            questions=[]
            for q in extracted:
                old=by_key.get(q['key'],{})
                questions.append({**q,'id':old.get('id'),'guidance':old.get('guidance',''),'page':old.get('page',1),'rect':old.get('rect'),'checkedFiles':[]})
            used={q['key'] for q in questions}
            questions.extend({**q,'items':[]} for q in previous if q['key'] not in used and q['key'] not in parent_keys)
            self.save_questions(vid,{'questions':questions})
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO version_rubric_outline VALUES(?,?)',(vid,json.dumps(value['outline'],ensure_ascii=False)))
                db.execute('INSERT OR REPLACE INTO version_structured_rubrics VALUES(?)',(vid,))
        return self.version(vid)
    def library_use(self,vid,payload):
        self.one('versions',vid);self.writable(vid);rid=payload.get('rubricId');entry=self.library_get(rid)
        if payload.get('confirmed') is not True:raise ValueError('Confirm loading this saved rubric into the exam version.')
        _,_,value=self._library_entry(rid)
        if value['version']==2:self.import_export(vid,value)
        else:
            previous=self.version(vid)['questions'];by_key={q['key']:q for q in previous}
            self.import_rubric(vid,{'text':entry['text']})
            questions=[]
            for q in entry['questions']:
                old=by_key.get(q['key'],{})
                questions.append({**q,'id':old.get('id'),'guidance':old.get('guidance',''),'page':old.get('page',1),'rect':old.get('rect'),'checkedFiles':[]})
            used={q['key'] for q in questions}
            questions.extend({**q,'items':[]} for q in previous if q['key'] not in used)
            if questions:self.save_questions(vid,{'questions':questions})
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO version_rubrics VALUES(?,?,?)',(vid,rid,stamp()))
            self.event(db,'library-rubric-reused',vid,{'rubric_id':rid,'reviewed_cards':bool(entry['questions'])})
        return self.version(vid)
    def library_save_version(self,vid,payload):
        v=self.version(vid);self.writable(vid);title=payload.get('title','')
        prepared=bool(v['rubric_approved']) and v['rubric_approved']==self.rubric_hash(v)
        fields=('key','title','maxPoints','selectionMode')
        questions=[{**{k:q[k] for k in fields},'items':[{k:item[k] for k in ('label','description','points')} for item in q['items']]} for q in v['questions']]
        text=v['raw_rubric']
        if not text.strip():
            if not prepared:raise ValueError('Confirm the complete rubric before saving it to the folder.')
            # Manual and AI drafts have no imported text. Save reviewed criteria only;
            # exclude version-specific solutions, question geometry and record IDs.
            text=json.dumps({'questions':questions},ensure_ascii=False,indent=2)
        portable=reviewed_export(v,title) if prepared else None
        value=self.library_import(portable or {'format':'g-rater-rubric-export','version':1,'title':title,'text':text})
        rid=value['id']
        if prepared:
            with self.connect() as db:db.execute('UPDATE rubric_library SET questions=?,updated=? WHERE id=?',(json.dumps(questions,ensure_ascii=False),stamp(),rid))
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO version_rubrics VALUES(?,?,?)',(vid,rid,stamp()))
        return {'rubric':self.library_get(rid),'prepared':prepared,'version':self.version(vid)}
