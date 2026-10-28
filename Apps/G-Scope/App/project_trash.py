"""Permanent project Trash cleanup, restricted to confirmed local managed copies."""
from datetime import datetime,timezone
import hashlib,json,re,secrets,stat

ID=re.compile(r'[a-f0-9]{32}')

def ids(value,maximum=500):
    if not isinstance(value,list) or len(value)>maximum or any(not isinstance(x,str) or not ID.fullmatch(x) for x in value) or len(set(value))!=len(value):
        raise ValueError('Refresh Project Trash and confirm its current contents.')
    return sorted(value)

def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')

class ProjectTrash:
    def trash_init(self):
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS project_trash_purges(id TEXT PRIMARY KEY,project_count INTEGER NOT NULL,manifest_hash TEXT NOT NULL,created TEXT NOT NULL)')

    def project_trash_cleanup(self):
        rows=self.rows('SELECT id,project_count FROM project_trash_purges ORDER BY id')
        return {'batches':[r['id'] for r in rows],'pendingProjects':sum(r['project_count'] for r in rows)}

    def _trash_base(self):return self._archive_safe_path(self.root/'Trash Cleanup')

    def _trash_tree(self,path):
        """Validate every node before moving or deleting any managed tree."""
        path=self._archive_safe_path(path)
        if not path.exists():return
        if not path.is_dir():raise ValueError('A managed project folder is not a normal directory.')
        pending=[path]
        while pending:
            folder=pending.pop()
            for child in folder.iterdir():
                self._archive_safe_path(child)
                if child.is_dir():pending.append(child)
                elif not child.is_file():raise ValueError('A managed project contains an unsupported file.')

    def _trash_manifest(self,folder,expected=None):
        path=self._archive_safe_path(folder/'manifest.json',True)
        if path.stat().st_size>4_000_000:raise ValueError('The interrupted trash cleanup manifest is invalid.')
        raw=path.read_bytes()
        if expected and hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('The trash cleanup manifest changed. Local files were retained.')
        data=json.loads(raw)
        if not isinstance(data,dict) or set(data)!={'projects','versions','moves'}:raise ValueError('The trash cleanup manifest is invalid.')
        projects=ids(data['projects']);versions=ids(data['versions'],13000)
        if not isinstance(data['moves'],list):raise ValueError('The trash cleanup manifest is invalid.')
        allowed={('Projects',v) for v in versions}|{('Scan Inbox',p) for p in projects};seen=set()
        for item in data['moves']:
            if not isinstance(item,list) or len(item)!=2 or not all(isinstance(x,str) for x in item) or tuple(item) not in allowed or tuple(item) in seen:raise ValueError('The trash cleanup manifest is invalid.')
            seen.add(tuple(item))
        return data

    def _trash_restore_moves(self,folder,data):
        for kind,identity in reversed(data['moves']):
            source=self._archive_safe_path(self.root/kind/identity);staged=self._archive_safe_path(folder/kind/identity)
            if staged.exists():
                if source.exists():raise ValueError('An interrupted cleanup conflicts with an existing folder. Files were retained.')
                self._trash_tree(staged);source.parent.mkdir(parents=True,exist_ok=True);staged.rename(source)

    def _trash_remove_tree(self,path):
        self._archive_safe_path(path)
        if not path.exists():return
        if path.is_dir():
            # Keep the recovery manifest until every project file is gone.
            for child in sorted(path.iterdir(),key=lambda p:p.name=='manifest.json'):self._trash_remove_tree(child)
            path.rmdir()
        else:
            try:path.unlink()
            except PermissionError:
                # Read-only managed copies may be removed; ACL/in-use failures
                # remain pending and never cause a delete outside this root.
                path.chmod(path.stat().st_mode|stat.S_IWRITE);path.unlink()

    def _trash_recover(self):
        base=self._trash_base()
        if not base.exists():return
        committed={r['id'] for r in self.rows('SELECT id FROM project_trash_purges')}
        trashed={r['project_id'] for r in self.rows('SELECT project_id FROM project_trash')}
        for folder in base.iterdir():
            self._archive_safe_path(folder)
            if not ID.fullmatch(folder.name) or not folder.is_dir():raise ValueError('Unexpected files in the local trash cleanup folder. Files were retained.')
            if folder.name in committed:continue
            data=self._trash_manifest(folder)
            if not set(data['projects'])<=trashed:raise ValueError('Interrupted project cleanup needs review before restoring or clearing Trash.')
            owned={r['id'] for r in self.rows('SELECT id,project_id FROM versions') if r['project_id'] in data['projects']}
            if not set(data['versions'])<=owned:raise ValueError('The interrupted cleanup does not match these projects.')
            self._trash_restore_moves(folder,data)
            self._trash_tree(folder);self._trash_remove_tree(folder)

    def _trash_cleanup_committed(self):
        for row in self.rows('SELECT * FROM project_trash_purges ORDER BY id'):
            if not ID.fullmatch(row['id']):raise ValueError('The trash cleanup record is invalid. Files were retained.')
            folder=self._archive_safe_path(self._trash_base()/row['id'])
            try:
                if folder.exists():
                    if not (folder/'manifest.json').exists() and not any(folder.iterdir()):folder.rmdir()
                    else:self._trash_manifest(folder,row['manifest_hash']);self._trash_tree(folder);self._trash_remove_tree(folder)
                with self.connect() as db:db.execute('DELETE FROM project_trash_purges WHERE id=?',(row['id'],))
            except (OSError,ValueError):pass # Retain a visible retry record.

    def _trash_delete_records(self,db,projects):
        """Connection-local scopes select only rows owned by these projects."""
        db.execute('CREATE TEMP TABLE trash_projects(id TEXT PRIMARY KEY)')
        db.executemany('INSERT INTO trash_projects VALUES(?)',[(p,) for p in projects])
        definitions={
            'versions':('versions','project_id','projects'),
            'sources':('scan_sources','project_id','projects'),
            'packets':('scan_packets','source_id','sources'),
            'files':('files','version_id','versions'),
            'booklets':('booklets','version_id','versions'),
            'questions':('questions','version_id','versions'),
            'runs':('runs','version_id','versions'),
            'proposals':('proposals','run_id','runs'),
            'reviews':('reviews','proposal_id','proposals'),
            'rules':('consistency_rules','project_id','projects'),
            'references':('material_references','version_id','versions'),
            'applications':('material_solution_applications','version_id','versions'),
            'answers':('answer_key_drafts','version_id','versions'),
            'batches':('project_batches','project_id','projects'),
        }
        for key,(table,column,parent) in definitions.items():
            db.execute(f'CREATE TEMP TABLE trash_{key} AS SELECT id FROM {table} WHERE {column} IN (SELECT id FROM trash_{parent})')
        children=[('answer_groups','question_id','questions'),('reviewed_examples','question_id','questions'),('grading_preferences','version_id','versions'),('reviews','proposal_id','proposals'),('proposals','run_id','runs'),
            ('consistency_revisions','rule_id','rules'),('scan_matching','packet_id','packets'),
            ('scan_provenance','booklet_id','booklets'),('scan_identities','booklet_id','booklets'),
            ('scan_removed_files','file_id','files'),('scan_source_versions','source_id','sources'),
            ('scan_split_reviews','source_id','sources'),('scan_order','project_id','projects'),
            ('scan_packets','source_id','sources'),('scan_sources','project_id','projects'),
            ('scan_layouts','version_id','versions'),('version_structured_rubrics','version_id','versions'),
            ('version_rubric_outline','version_id','versions'),('version_rubrics','version_id','versions'),
            ('material_pdf_previews','reference_id','references'),('material_solution_applications','version_id','versions'),
            ('material_references','version_id','versions'),('answer_key_drafts','version_id','versions'),
            ('project_scan_settings','project_id','projects'),('project_rosters','project_id','projects'),
            ('consistency_rules','project_id','projects'),('project_batches','project_id','projects'),
            ('questions','version_id','versions'),('booklets','version_id','versions'),('files','version_id','versions'),
            ('runs','version_id','versions'),('versions','project_id','projects'),
            ('project_trash','project_id','projects'),('projects','id','projects')]
        for table,column,scope in children:db.execute(f'DELETE FROM {table} WHERE {column} IN (SELECT id FROM trash_{scope})')
        owned=' UNION '.join('SELECT id FROM trash_'+key for key in ['projects',*definitions])
        db.execute('DELETE FROM events WHERE subject IN ('+owned+')')

    def clear_project_trash(self,payload):
        with self.lock:
            if not isinstance(payload,dict) or set(payload)!={'confirmed','projectIds','cleanupBatches'} or payload['confirmed'] is not True:
                raise ValueError('Confirm permanent removal from Project Trash.')
            projects=ids(payload['projectIds']);batches=ids(payload['cleanupBatches'])
            self._archive_idle();self._trash_recover()
            current=sorted(r['project_id'] for r in self.rows('SELECT project_id FROM project_trash'))
            if projects!=current or batches!=self.project_trash_cleanup()['batches']:
                raise ValueError('Project Trash changed. Refresh and review it before clearing.')
            if projects:
                versions=sorted(r['id'] for r in self.rows('SELECT id,project_id FROM versions') if r['project_id'] in projects)
                ids(versions,13000)
                plan={'projects':projects,'versions':versions,'moves':[]}
                for kind,identities in (('Projects',versions),('Scan Inbox',projects)):
                    for item in identities:
                        path=self._archive_safe_path(self.root/kind/item);self._trash_tree(path)
                        if path.exists():plan['moves'].append([kind,item])
                raw=packed(plan)
                if len(raw)>4_000_000:raise ValueError('This Trash cleanup is too large. Files were retained.')
                purge=secrets.token_hex(16);folder=self._archive_safe_path(self._trash_base()/purge)
                folder.mkdir(parents=True,exist_ok=False)
                try:
                    (folder/'manifest.json').write_bytes(raw)
                    for kind,item in plan['moves']:
                        destination=self._archive_safe_path(folder/kind/item);destination.parent.mkdir(parents=True,exist_ok=True)
                        self._archive_safe_path(self.root/kind/item).rename(destination)
                    with self.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        self._trash_delete_records(db,projects)
                        db.execute('INSERT INTO project_trash_purges VALUES(?,?,?,?)',(purge,len(projects),hashlib.sha256(raw).hexdigest(),datetime.now(timezone.utc).isoformat()))
                except BaseException:
                    self._trash_restore_moves(folder,plan);self._trash_tree(folder);self._trash_remove_tree(folder)
                    raise
            self._trash_cleanup_committed()
            cleanup=self.project_trash_cleanup()
            return {'clearedProjects':len(projects),'complete':not cleanup['pendingProjects'],'cleanup':cleanup,
                'message':'Trash cleared.' if not cleanup['pendingProjects'] else 'Project records were removed. Some local files could not be removed; close previews, check folder access and retry Clear trash.'}
