"""Local G-Vault workspace registry. Database inspection never reads student rows."""
from pathlib import Path
from contextlib import closing
import json, os, re, sqlite3, threading, uuid


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class VaultWorkspaces:
    """One grade database per course; letters and integrity remain independent."""
    def __init__(self, app_root):
        self.root = Path(app_root).resolve()
        self.path = self.root / 'Data/vault-workspaces.json'
        self.modules = self.root / 'Data/PrivateModules'
        self.lock = threading.RLock()

    def encode(self, path):
        path = Path(path).resolve()
        return path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path)

    def resolve(self, value):
        p = Path(value)
        if not p.is_absolute():
            p = (self.root / p).resolve()
            if not p.is_relative_to(self.root):
                raise ValueError('Choose a local workspace path.')
        return p.resolve()

    def load(self):
        if self.path.exists():
            value = json.loads(self.path.read_text('utf-8-sig'))
            if value.get('version') != 1 or not isinstance(value.get('courses'), list):
                raise ValueError('The workspace registry is not compatible with this version.')
            return value
        value = {'version': 1, 'courses': [], 'active_course': '', 'libraries': {}}
        old = self.modules / 'Math135/Math_135_Central.sqlite'
        if old.is_file():
            value['courses'].append({'id': 'math-135', 'code': '135', 'name': 'Math 135',
                                    'path': self.encode(old), 'policy_mode': 'legacy135'})
            value['active_course'] = 'math-135'
        for module, folder in (('recommendations', 'Recommendations'), ('integrity', 'Integrity')):
            value['libraries'][module] = self.encode(self.modules / folder)
        atomic_json(self.path, value)
        return value

    def inventory(self):
        with self.lock:
            value = self.load()
            return {**value, 'courses': [{**row, 'path': str(self.resolve(row['path'])),
                                         'available': self.resolve(row['path']).is_file()}
                                        for row in value['courses']],
                    'libraries': {k: str(self.resolve(v)) for k, v in value['libraries'].items()}}

    def course(self, identity=None):
        value = self.load()
        identity = identity or value.get('active_course')
        row = next((r for r in value['courses'] if r['id'] == identity), None)
        if not row:
            raise ValueError('Create or open a course database to begin.')
        return {**row, 'database': self.resolve(row['path'])}

    def library(self, module):
        if module not in ('recommendations', 'integrity'):
            raise ValueError('Choose a letters or integrity library.')
        return self.resolve(self.load()['libraries'][module])

    def inspect_database(self, path):
        """Validate structure and optional course identity using a read-only connection."""
        path = Path(path).resolve()
        if not path.is_file() or path.suffix.lower() not in ('.sqlite', '.sqlite3', '.db'):
            raise ValueError('Choose an existing G-Vault grade database (.sqlite or .db).')
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('PRAGMA trusted_schema=OFF')
                required = {'students': {'ruid'}, 'enrollments': {'ruid', 'semester', 'official_grade'},
                            'semesters': {'semester', 'policy_json'},
                            'assessment_definitions': {'assessment_id', 'assessment_key'},
                            'sources': {'source_id', 'kind', 'semester'}, 'app_settings': {'key', 'value'}}
                schema = self.modules / 'Math135/App/empty_database.sql'
                if schema.is_file():
                    with closing(sqlite3.connect(':memory:')) as expected:
                        expected.executescript(schema.read_text('utf-8'))
                        for (table,) in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'app_%' AND name NOT LIKE 'sqlite_%'"):
                            required[table] = {r[1] for r in expected.execute('PRAGMA table_info("' + table + '")')}
                for table, columns in required.items():
                    found = {r[1] for r in db.execute('PRAGMA table_info("' + table + '")')}
                    if not columns <= found:
                        raise ValueError('This is not a compatible G-Vault grade database.')
                return dict(db.execute("SELECT key,value FROM app_settings WHERE key IN ('course_code','course_name','policy_mode')"))
        except sqlite3.DatabaseError as exc:
            raise ValueError('The selected grade database could not be read.') from exc

    def update(self, payload):
        with self.lock:
            value = self.load()
            action = payload.get('action')
            if action == 'select':
                row = self.course(payload.get('id'))
                if not row['database'].is_file():
                    raise ValueError('This course database is unavailable. Open its current location.')
                value['active_course'] = row['id']
            elif action in ('create', 'register'):
                code = str(payload.get('code', '')).strip()
                name = str(payload.get('name', '')).strip() or 'Math ' + code
                if not re.fullmatch(r'\d{3}', code) or len(name) > 120:
                    raise ValueError('Enter a three-digit Rutgers Mathematics course and a short name.')
                existing = next((r for r in value['courses'] if r['code'] == code), None)
                if action == 'create' and existing:
                    raise ValueError('This course already has a database. Open it to add another semester or section.')
                identity = 'math-' + code
                if action == 'create':
                    path = self.modules / 'Grades' / identity / 'grades.sqlite'
                    if path.exists():
                        raise ValueError('A database already exists for this course. Use Open database to register it.')
                    schema = self.modules / 'Math135/App/empty_database.sql'
                    if not schema.is_file():
                        raise ValueError('The grade database framework is not installed.')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name('grades.' + uuid.uuid4().hex + '.initializing')
                    try:
                        with closing(sqlite3.connect(temporary)) as db:
                            db.executescript(schema.read_text('utf-8'))
                            db.executemany('INSERT OR REPLACE INTO app_settings VALUES(?,?)',
                                           [('course_code', code), ('course_name', name), ('policy_mode', 'custom')])
                            db.commit()
                        # Rename must not replace an existing course database.
                        if os.name == 'nt': temporary.rename(path)
                        else: os.link(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
                    mode = 'custom'
                else:
                    path = Path(str(payload.get('path', '')))
                    if not path.is_absolute():
                        raise ValueError('Enter the full path to an existing grade database.')
                    path = path.resolve()
                    if any(r['code'] != code and self.resolve(r['path']) == path for r in value['courses']):
                        raise ValueError('This database is already registered.')
                    info = self.inspect_database(path)
                    if info.get('course_code') and info['course_code'] != code:
                        raise ValueError('The course number does not match the selected database.')
                    mode = info.get('policy_mode', 'legacy135' if code == '135' else 'custom')
                row = {'id': identity, 'code': code, 'name': name,
                       'path': self.encode(path), 'policy_mode': mode}
                if existing:
                    previous = list(existing.get('previous_paths', []))
                    if existing['path'] != row['path'] and existing['path'] not in previous:
                        previous.append(existing['path'])
                    existing.update(row, previous_paths=previous)
                else:
                    value['courses'].append(row)
                value['active_course'] = identity
            elif action == 'library':
                module = payload.get('module')
                if module not in ('recommendations', 'integrity'):
                    raise ValueError('Choose a letters or integrity library.')
                path = Path(str(payload.get('path', '')))
                if not path.is_absolute():
                    raise ValueError('Enter the full path to the library folder.')
                path = path.resolve()
                other = 'integrity' if module == 'recommendations' else 'recommendations'
                if path == self.resolve(value['libraries'][other]):
                    raise ValueError('Letters and integrity need separate library folders.')
                if payload.get('create'):
                    if path.exists() and any(path.iterdir()):
                        raise ValueError('Choose an empty folder for a new library.')
                    path.mkdir(parents=True, exist_ok=True)
                    (path / 'tools').mkdir(exist_ok=True)
                    atomic_json(path / 'tools/g-vault-library.json', {'version': 1, 'module': module})
                elif not path.is_dir() or not (path / 'tools').is_dir():
                    raise ValueError('Choose an existing library containing its tools folder.')
                marker = path / 'tools/g-vault-library.json'
                if marker.is_file() and json.loads(marker.read_text('utf-8')).get('module') != module:
                    raise ValueError('This folder belongs to the other library type.')
                value['libraries'][module] = self.encode(path)
            else:
                raise ValueError('Choose a workspace action.')
            atomic_json(self.path, value)
            return self.inventory()
