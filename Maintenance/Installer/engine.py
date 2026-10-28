"""G-Works installation engine. Standard library only; no user records in releases."""
from __future__ import annotations
from pathlib import Path, PurePosixPath
import argparse, base64, contextlib, hashlib, hmac, json, os, re, secrets, shutil, stat, subprocess, sys, time, urllib.request, urllib.parse, urllib.error, zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
APPS = {'whiz': 'G-Whiz', 'scope': 'G-Scope', 'spot': 'G-Vault'}
APP_SUITES = {'whiz': 'professional', 'scope': 'professional', 'spot': 'professional'}
SUITE_NAMES = {'professional': 'G-Works'}
DEPENDENCY_ROLES = {'Python', 'DesktopRuntime', 'Poppler', 'GeneralAI', 'IntegrityPython', 'WizzyPoppler'}
SHARED_RUNTIME_ROLES = DEPENDENCY_ROLES | {'TeachingApp', 'TeachingSupport', 'ScopeVendor', 'TeXLive', 'Commands'}
HEX = re.compile('^[a-f0-9]{64}$')

def root_suite(root):
    suites = set()
    for name in ('root.json', 'installation.json'):
        path = Path(root) / '.gworks' / name
        if path.is_file():
            value = json.loads(path.read_text('utf-8-sig')).get('suite')
            if value is not None:
                if value not in SUITE_NAMES:
                    raise ValueError('Unknown installation suite.')
                suites.add(value)
    if len(suites) > 1:
        raise ValueError('Installation suite records disagree. Restore the matching local records before updating.')
    return next(iter(suites), None)

def installation_suite(root, apps, requested=None):
    suites = {APP_SUITES[app] for app in apps}
    if len(suites) != 1:
        raise ValueError('Professional and personal apps need separate installation folders.')
    selected = next(iter(suites))
    current = root_suite(root)
    if requested is not None and requested not in SUITE_NAMES:
        raise ValueError('Unknown installation suite.')
    if current and current != selected or (requested and requested != selected):
        raise ValueError('The selected apps belong to ' + SUITE_NAMES[selected] + ". Choose that suite's installation folder.")
    return current or requested or selected

def previous_app_names(root, prior):
    names = {'spot': 'G-Keeper', 'wizzy': 'Application', 'schwing': 'Application'}
    record = prior.get('apps', {}).get('spot', {})
    legacy_name = 'G-' + 'Spot'
    original = record.get('name') == legacy_name or (record.get('version') and release_version(record['version']) < (2, 1, 0))
    if original and root_suite(root) != 'personal' and (not (Path(root) / 'Apps/G-Keeper').exists()):
        names['spot'] = legacy_name
    return names

def require_suite_release(catalog, options, suite):
    if catalog.get('distribution_policy') == 2:
        import distribution
        distribution.validate(catalog)
        if catalog['suite'] != suite:
            raise ValueError('Choose the installer for this suite.')
    legacy = catalog.get('suite_layout') != 1
    if legacy and (not options.get('dependencies_only')):
        raise ValueError('This release predates the G-Works / Application split. App updates require a split-compatible release. Choose Change dependencies only to maintain the installed apps.')
    if not legacy:
        for app in catalog.get('applications', []):
            if app.get('id') in APPS and (app.get('name') != APPS[app['id']] or app.get('suite') != APP_SUITES[app['id']]):
                raise ValueError('The release has inconsistent suite routing.')
    return legacy

def release_version(value):
    if not isinstance(value, str) or not re.fullmatch('\\d+\\.\\d+\\.\\d+', value):
        raise ValueError('Invalid release version.')
    return tuple(map(int, value.split('.')))

def select_release_update(bundled, candidate):
    if candidate.get('channel') != 'public':
        raise ValueError('The update channel must provide a public release catalogue.')
    return candidate if release_version(candidate['release']) > release_version(bundled['release']) else bundled

def emit(text, **fields):
    print(json.dumps({'message': text, **fields}), flush=True)

def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()

def json_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(5) + '.new')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', 'utf-8')
    os.replace(temp, path)

def linked(path):
    return Path(path).is_symlink() or getattr(Path(path), 'is_junction', lambda: False)()

def dependency_target(root, target):
    target = Path(target).resolve()
    shared = Path(root) / 'Shared'
    return target.is_relative_to(shared.resolve()) or any(((shared / role).is_dir() and target.is_relative_to((shared / role).resolve()) for role in SHARED_RUNTIME_ROLES))

def clean_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid package path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any((p in ('..', '.') or ':' in p or p.rstrip(' .') != p or (not p) for p in value.split('/'))):
        raise ValueError('Unsafe package path.')
    if any((p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]} for p in path.parts)):
        raise ValueError('Reserved package filename.')
    return path

def contained(root, relative, allow_leaf_link=False):
    root = Path(root).absolute()
    rel = clean_relative(relative)
    path = root.joinpath(*rel.parts)
    for parent in (root, *list(path.parents)[:len(rel.parts) - 1], *(() if allow_leaf_link else (path,))):
        if linked(parent):
            raise ValueError('An installation path is a link; choose a normal folder.')
    if not (path.parent.resolve() if allow_leaf_link else path.resolve()).is_relative_to(root.resolve()):
        raise ValueError('Installation path escaped its folder.')
    return path

def validate_root(root):
    root = Path(root).expanduser().absolute()
    if root == Path(root.anchor) or root == Path.home() or len(root.parts) < 2:
        raise ValueError('Choose a dedicated G-Works folder inside a drive.')
    for node in (root, *root.parents):
        if linked(node):
            raise ValueError('Choose an installation folder without directory links.')
    for name in ('.gworks', 'Apps', 'Shared'):
        if linked(root / name):
            raise ValueError('The G-Works control folders may not be links.')
    if any((str(root).casefold().startswith(str(Path(os.environ[k])).casefold() + os.sep) or root == Path(os.environ[k]) for k in ('WINDIR', 'SystemRoot') if k in os.environ)):
        raise ValueError('Choose a folder outside Windows.')
    if root.exists() and any(root.iterdir()) and (not (root / '.gworks/root.json').is_file()):
        raise ValueError('This folder contains other files. Choose an empty folder or an existing G-Works installation.')
    return root

def verify_signature(raw, signature, key):
    """RSA PKCS#1 v1.5 SHA-256 verification with a pinned public key."""
    try:
        n = int(key['n'])
        e = int(key['e'])
        size = (n.bit_length() + 7) // 8
        sig = base64.b64decode(signature, validate=True)
        if len(sig) != size or int.from_bytes(sig, 'big') >= n:
            return False
        actual = pow(int.from_bytes(sig, 'big'), e, n).to_bytes(size, 'big')
        tail = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(raw).digest()
        expected = b'\x00\x01' + b'\xff' * (size - len(tail) - 3) + b'\x00' + tail
        return size >= 256 and hmac.compare_digest(actual, expected)
    except (ValueError, KeyError, TypeError):
        return False

def catalogue(path, signature, key):
    raw = Path(path).read_bytes()
    if len(raw) > 2000000 or not verify_signature(raw, Path(signature).read_text('ascii').strip(), key):
        raise ValueError('Release catalogue signature is invalid.')
    value = json.loads(raw)
    if value.get('schema') != 1 or not isinstance(value.get('packages'), list):
        raise ValueError('Unsupported release catalogue.')
    app_names = {}
    for app in value.get('applications', []):
        if not re.fullmatch('[a-z][a-z0-9-]{0,39}', app.get('id', '')) or not re.fullmatch('G-[A-Za-z0-9-]{1,40}', app.get('name', '')) or app.get('visibility') not in ('public', 'private'):
            raise ValueError('Invalid application definition.')
        legacy = app['id'] == 'spot' and app['name'] == 'Application' and (value.get('suite_layout') != 1) or (release_version(value.get('release', '0.0.0')) < (2, 2, 0) and app['name'] == {'spot': 'G-Keeper', 'wizzy': 'Application'}.get(app['id']))
        if app['id'] not in APPS or (APPS[app['id']] != app['name'] and (not legacy)):
            raise ValueError('An application changed its install folder.')
        if value.get('suite_layout') == 1 and app.get('suite') != APP_SUITES[app['id']]:
            raise ValueError('Invalid application suite.')
        app_names[app['id']] = app['name']
    ids = set()
    for p in value['packages']:
        if not re.fullmatch('[a-z0-9][a-z0-9.-]{0,79}', p.get('id', '')) or p['id'] in ids or (not HEX.fullmatch(p.get('sha256', ''))):
            raise ValueError('Invalid package catalogue.')
        ids.add(p['id'])
        if p.get('kind') not in ('app', 'course', 'runtime', 'tool-installer'):
            raise ValueError('Unsupported package kind.')
        clean_relative(p['target'])
        if p['kind'] == 'app' and p['target'] != 'Apps/' + app_names.get(p.get('app'), APPS.get(p.get('app'), 'invalid')):
            raise ValueError('Unexpected application destination.')
        if p['kind'] == 'course' and (p.get('app') != 'whiz' or not re.fullmatch('[a-z0-9][a-z0-9-]{0,39}', p.get('course', '')) or p['target'] != 'Shared/Courses/' + p['course']):
            raise ValueError('Unexpected course destination.')
        if p['kind'] != 'app' and (not p['target'].startswith('Shared/')):
            raise ValueError('Unexpected shared destination.')
    if value.get('distribution_policy') == 2 and release_version(value.get('release', '0.0.0')) >= (2, 2, 0):
        import distribution
        distribution.validate(value, inventory=True)
    return value

def https_request(url, data=None, token=None, max_bytes=2000000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Downloads and activation require HTTPS.')
    headers = {'User-Agent': 'G-Works-Installer/1.0'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token

    class Redirect(urllib.request.HTTPRedirectHandler):

        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            if token and urllib.parse.urlsplit(newurl).netloc != parsed.netloc:
                raise ValueError('An authenticated download redirected to another service.')
            if urllib.parse.urlsplit(newurl).scheme != 'https':
                raise ValueError('Download redirect did not use HTTPS.')
            return super().redirect_request(req, fp, code, msg, response_headers, newurl)
    opener = urllib.request.build_opener(Redirect(), urllib.request.ProxyHandler())
    response = opener.open(urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers), timeout=120)
    if max_bytes is None:
        return response
    with response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('The service response is too large.')
    return raw

def authorize(public, selected, code, key, workspace):
    if public.get('distribution_policy') == 2:
        import distribution
        distribution.validate(public)
        if not set(selected) <= {a['id'] for a in public['applications']}:
            raise ValueError('The selected apps belong to another suite.')
        return (public, None, None)
    public_apps = {a['id'] for a in public.get('applications', []) if a.get('visibility') == 'public'}
    private = set(selected) - public_apps
    if not private or public.get('channel') == 'owner':
        return (public, None, None)
    service = public.get('activation_service', '').rstrip('/')
    if not service:
        raise ValueError('Private downloads are not connected yet. Configure the activation service before distributing this installer.')
    if not isinstance(code, str) or not code.strip():
        raise ValueError('Enter an activation code for the selected private apps. For an owner bundle, turn off the release-channel check to use the included offline release.')
    result = json.loads(https_request(service + '/v1/activate', {'code': code, 'apps': sorted(private)}))
    token = result.get('token')
    if not isinstance(token, str) or len(token) > 4096:
        raise ValueError('Activation did not return a valid download session.')
    envelope = json.loads(https_request(service + '/v1/catalogue', token=token))
    raw = base64.b64decode(envelope['catalogue'], validate=True)
    path = Path(workspace) / 'private-catalogue.json'
    path.write_bytes(raw)
    signature = path.with_suffix('.sig')
    signature.write_text(envelope['signature'], 'ascii')
    private_catalogue = catalogue(path, signature, key)
    if not private <= set(result.get('apps', [])):
        raise ValueError('This activation does not allow all selected apps.')
    if private_catalogue.get('release') != public.get('release'):
        raise ValueError('The public and private release versions differ. Download the current installer.')
    merged = {p['id']: p for p in public['packages']}
    for package in private_catalogue['packages']:
        merged[package['id']] = package
    return ({**public, 'packages': list(merged.values())}, token, service)

def get_package(package, offline, cache, token=None, service=None):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (package['sha256'] + '.pkg')
    if target.is_file() and digest(target) == package['sha256']:
        return target
    source = package['source']
    partial = target.with_suffix('.part')
    if '://' not in source:
        origin = contained(Path(offline), source)
        if not origin.is_file():
            raise ValueError('Missing offline package ' + package['id'] + '. Download the complete bundle or configure its release URL.')
        shutil.copyfile(origin, partial)
    else:
        if token and (not service or urllib.parse.urlsplit(source).netloc != urllib.parse.urlsplit(service).netloc):
            raise ValueError('Private downloads must use the activation service.')
        with https_request(source, token=token, max_bytes=None) as response, partial.open('wb') as output:
            size = 0
            while (block := response.read(1024 * 1024)):
                size += len(block)
                if size > int(package.get('size', 0)) + 1024:
                    raise ValueError('A package download exceeded its signed size.')
                output.write(block)
    if digest(partial) != package['sha256']:
        partial.unlink(missing_ok=True)
        raise ValueError('A package checksum did not match. Nothing was installed.')
    os.replace(partial, target)
    return target

def extract(archive, destination, limit=40 * 1024 ** 3):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        seen = set()
        if len(entries) > 450000 or sum((x.file_size for x in entries)) > limit:
            raise ValueError('Package expands beyond its allowed size.')
        for entry in entries:
            name = entry.filename.rstrip('/')
            if not name:
                continue
            clean_relative(name)
            key = name.casefold()
            if key in seen:
                raise ValueError('Package contains conflicting filenames.')
            seen.add(key)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Packages may not contain links.')
        for entry in entries:
            name = entry.filename.rstrip('/')
            if not name:
                continue
            target = contained(destination, name)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output, 1024 * 1024)

def remove_link(link):
    if os.name == 'nt' and (not link.is_symlink()):
        link.rmdir()
    else:
        link.unlink()

def create_link(link, target):
    if os.name == 'nt':
        a = base64.b64encode(str(link).encode()).decode()
        b = base64.b64encode(str(target).encode()).decode()
        code = "$ErrorActionPreference='Stop';New-Item -ItemType Junction -Path ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + a + "'))) -Target ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + b + "'))) | Out-Null"
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(code.encode('utf-16-le')).decode()], check=True, creationflags=134217728)
    else:
        link.symlink_to(target, target_is_directory=True)

class Transaction:

    def __init__(self, root):
        self.root = Path(root)
        self.folder = self.root / '.gworks/transactions' / secrets.token_hex(12)
        self.folder.mkdir(parents=True)
        self.entries = []
        self.junctions = []
        self.directories = []
        self.trees = []
        self.local_runtimes = []
        self.moves = []
        self.save('staging')

    def save(self, state):
        json_write(self.folder / 'journal.json', {'state': state})

    def record(self, value):
        with (self.folder / 'operations.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(value) + '\n')
            log.flush()
            os.fsync(log.fileno())

    def put(self, source, relative, seed=False):
        target = contained(self.root, relative)
        if seed and target.exists():
            return
        if target.exists() and (not target.is_file() or target.is_symlink()):
            raise ValueError('Managed file is not a normal file.')
        index = len(self.entries)
        old = self.folder / (str(index) + '.old')
        existed = target.exists()
        if existed:
            shutil.copy2(target, old)
        entry = {'path': relative, 'old': str(index) + '.old' if existed else None}
        self.entries.append(entry)
        self.record({'type': 'file', **entry})
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.gworks-new')
        shutil.copy2(source, temp)
        os.replace(temp, target)

    def link(self, relative, target):
        link = contained(self.root, relative, allow_leaf_link=True)
        target = Path(target).resolve()
        old = None
        if link.exists() or linked(link):
            if linked(link) and link.resolve() == target:
                return
            if not linked(link):
                raise ValueError('A dependency folder already exists with different contents.')
            old = str(link.resolve())
            if not dependency_target(self.root, old):
                raise ValueError('An existing dependency link points outside Shared.')
        link.parent.mkdir(parents=True, exist_ok=True)
        self.junctions.append({'path': relative, 'old_target': old})
        self.record({'type': 'junction', 'path': relative, 'old_target': old})
        if linked(link):
            remove_link(link)
        create_link(link, target)

    def tree(self, source, relative, seed=False):
        target = contained(self.root, relative)
        if seed and target.exists():
            return
        if target.exists() and (not target.is_dir()):
            raise ValueError('Managed code is not a folder.')
        old = 'tree-' + str(len(self.trees)) + '.old' if target.exists() else None
        entry = {'path': relative, 'old': old}
        self.trees.append(entry)
        self.record({'type': 'tree', **entry})
        target.parent.mkdir(parents=True, exist_ok=True)
        if old:
            os.replace(target, self.folder / old)
        os.replace(source, target)

    def move(self, source_relative, destination_relative):
        source = contained(self.root, source_relative)
        target = contained(self.root, destination_relative)
        if not source.is_dir() or target.exists():
            raise ValueError('The renamed application folder is already occupied.')
        entry = {'source': source_relative, 'path': destination_relative}
        self.moves.append(entry)
        self.record({'type': 'move', **entry})
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)

    def local_runtime(self, relative, source):
        target = contained(self.root, relative, allow_leaf_link=True)
        source = Path(source).resolve()
        marker = source / '.gworks-package.json'
        if target.is_dir() and (not linked(target)) and marker.is_file() and (target / '.gworks-package.json').is_file() and (marker.read_bytes() == (target / '.gworks-package.json').read_bytes()):
            return
        if not dependency_target(self.root, source):
            raise ValueError('Runtime source is outside the verified package store.')
        for folder, dirs, files in os.walk(source):
            if any((linked(Path(folder) / name) for name in dirs + files)):
                raise ValueError('Python runtimes must contain local files only.')
        snapshot = self.folder / ('local-runtime-' + str(len(self.local_runtimes)) + '.new')
        shutil.copytree(source, snapshot)
        old_link = str(target.resolve()) if linked(target) else None
        if old_link and (not dependency_target(self.root, old_link)):
            raise ValueError('The old Python dependency points outside the package store.')
        old = 'local-runtime-' + str(len(self.local_runtimes)) + '.old' if target.exists() and (not old_link) else None
        entry = {'path': relative, 'old': old, 'old_link': old_link}
        self.local_runtimes.append(entry)
        self.record({'type': 'local-runtime', **entry})
        target.parent.mkdir(parents=True, exist_ok=True)
        if old_link:
            remove_link(target)
        elif old:
            os.replace(target, self.folder / old)
        os.replace(snapshot, target)

    def runtime(self, source, relative, package):
        target = self.root.joinpath(*clean_relative(relative).parts)
        if target.exists():
            marker = target / '.gworks-package.json'
            if not marker.is_file() or json.loads(marker.read_text('utf-8')).get('sha256') != package['sha256']:
                raise ValueError('A shared runtime version differs from this release. Use a new runtime version.')
            return
        target = contained(self.root, relative)
        json_write(Path(source) / '.gworks-package.json', {'sha256': package['sha256'], 'version': package['version']})
        target.parent.mkdir(parents=True, exist_ok=True)
        self.directories.append(relative)
        self.record({'type': 'directory', 'path': relative})
        os.replace(source, target)

    def rollback(self):
        for entry in reversed(self.local_runtimes):
            target = contained(self.root, entry['path'], allow_leaf_link=True)
            old = self.folder / entry['old'] if entry.get('old') else None
            if old and (not old.exists()):
                continue
            if linked(target):
                remove_link(target)
            elif target.exists():
                shutil.rmtree(target)
            if old:
                os.replace(old, target)
            elif entry.get('old_link'):
                create_link(target, Path(entry['old_link']))
        for entry in reversed(self.junctions):
            link = self.root.joinpath(*clean_relative(entry['path']).parts)
            if linked(link):
                remove_link(link)
            if entry.get('old_target'):
                create_link(link, Path(entry['old_target']))
        for entry in reversed(self.entries):
            target = contained(self.root, entry['path'])
            if entry['old']:
                shutil.copy2(self.folder / entry['old'], target)
            else:
                target.unlink(missing_ok=True)
        for relative in reversed(self.directories):
            path = contained(self.root, relative)
            if path.exists():
                shutil.rmtree(path)
        for entry in reversed(self.trees):
            target = contained(self.root, entry['path'])
            old = self.folder / entry['old'] if entry['old'] else None
            if old and (not old.exists()):
                continue
            if target.exists():
                shutil.rmtree(target)
            if old:
                os.replace(old, target)
        for entry in reversed(self.moves):
            target = contained(self.root, entry['path'])
            source = contained(self.root, entry['source'])
            if target.exists() and (not source.exists()):
                os.replace(target, source)
        self.save('rolled-back')

    def commit(self):
        self.save('committed')

    def compact(self):
        history = self.root / '.gworks/rollback'
        history.mkdir(exist_ok=True)
        archive = history / (self.folder.name + '.zip')
        partial = archive.with_suffix('.part')
        files = [p for p in self.folder.rglob('*') if p.is_file() and (p.name in ('journal.json', 'operations.jsonl') or any((x.endswith('.old') for x in p.relative_to(self.folder).parts)))]
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for file in files:
                if file.is_file():
                    z.write(file, file.relative_to(self.folder).as_posix())
        with zipfile.ZipFile(partial) as z:
            if z.testzip() is not None:
                raise ValueError('The update recovery archive could not be verified.')
        os.replace(partial, archive)
        assert self.folder.resolve().parent == (self.root / '.gworks/transactions').resolve()
        shutil.rmtree(self.folder)
        for old in sorted(history.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)[2:]:
            if old.is_file() and (not linked(old)):
                old.unlink()

def pid_alive(pid):
    if os.name == 'nt':
        import ctypes
        api = ctypes.windll.kernel32
        api.OpenProcess.restype = ctypes.c_void_p
        handle = api.OpenProcess(1048576, False, int(pid))
        if not handle:
            return False
        try:
            return api.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 258
        finally:
            api.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False

def recover(root):
    root = Path(root)
    base = root / '.gworks/transactions'
    if not base.exists():
        return
    for folder in sorted(base.iterdir()):
        if linked(folder) or not folder.is_dir():
            raise ValueError('Unexpected recovery folder.')
        state = json.loads((folder / 'journal.json').read_text('utf-8'))['state']
        if state in ('committed', 'rolled-back'):
            continue
        log = folder / 'operations.jsonl'
        operations = []
        if log.exists():
            lines = log.read_text('utf-8').splitlines()
            for index, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                except ValueError:
                    if index == len(lines) - 1:
                        break
                    raise ValueError('The recovery journal is damaged.')
                path = clean_relative(entry['path'])
                if path.parts[0] not in ('Apps', 'Shared', '.gworks', 'Application') and entry['path'] not in ('Install G-Works.exe', 'Install Application.exe'):
                    raise ValueError('Unexpected recovery path.')
                if entry['type'] == 'directory' and (path.parts[0] != 'Shared' or len(path.parts) < 3):
                    raise ValueError('Unexpected runtime recovery path.')
                if path.parts[0] == '.gworks' and entry['path'] not in ('.gworks/installation.json', '.gworks/root.json'):
                    raise ValueError('Unexpected installer recovery path.')
                if entry.get('old') and (not re.fullmatch('(?:tree-|local-runtime-)?\\d+\\.old', entry['old'])):
                    raise ValueError('Unexpected recovery backup.')
                if entry.get('old') and entry['type'] == 'file' and (not (folder / entry['old']).is_file() or linked(folder / entry['old'])):
                    raise ValueError('Recovery backup is unavailable; existing files were kept.')
                if entry.get('old_target') and (not dependency_target(root, entry['old_target'])):
                    raise ValueError('Unexpected recovery link target.')
                if entry.get('old_link') and (not dependency_target(root, entry['old_link'])):
                    raise ValueError('Unexpected local runtime recovery target.')
                if entry['type'] == 'move' and (path.parts[0] != 'Apps' or clean_relative(entry['source']).parts[0] != 'Apps'):
                    raise ValueError('Unexpected application move recovery path.')
                if entry['type'] == 'tree' and (path.parts[0] != 'Apps' or len(path.parts) < 3):
                    raise ValueError('Unexpected code recovery path.')
                operations.append(entry)
        transaction = Transaction.__new__(Transaction)
        transaction.root = root
        transaction.folder = folder
        transaction.entries = [{k: v for k, v in entry.items() if k != 'type'} for entry in operations if entry['type'] == 'file']
        transaction.junctions = [entry for entry in operations if entry['type'] == 'junction']
        transaction.directories = [entry['path'] for entry in operations if entry['type'] == 'directory']
        transaction.trees = [entry for entry in operations if entry['type'] == 'tree']
        transaction.local_runtimes = [entry for entry in operations if entry['type'] == 'local-runtime']
        transaction.moves = [entry for entry in operations if entry['type'] == 'move']
        transaction.rollback()

def archive_question_bank(transaction):
    """A fresh-bank choice keeps the complete previous bank in a local backup."""
    prefix = 'Apps/' + APPS['whiz'] + '/'
    relative = prefix + 'Data/Question Bank'
    active = contained(transaction.root, relative)
    source = active if active.is_dir() else None
    if source is None:
        legacy = contained(transaction.root, prefix + 'mh-git/exercise-bank')
        source = legacy if legacy.is_dir() else None
    if source is None:
        settings = contained(transaction.root, prefix + 'Data/settings.json')
        configured = json.loads(settings.read_text('utf-8-sig')) if settings.is_file() else {}
        repository = configured.get('repository')
        if isinstance(repository, str) and repository:
            repo = Path(repository)
            if not repo.is_absolute():
                repo = transaction.root / prefix / repo
            candidate = repo / 'exercise-bank'
            if candidate.is_dir():
                source = candidate
    if source is None:
        return None
    if linked(source):
        raise ValueError('Question-bank backups cannot follow links.')
    for folder, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if linked(Path(folder) / name):
                raise ValueError('Question-bank backups cannot follow links.')
    cat = source / 'catalog.json'
    original = json.loads(cat.read_text('utf-8-sig')) if cat.is_file() else {}
    fresh = {k: original[k] for k in ('schema_version', 'courses', 'topics', 'objectives', 'manuals', 'taxonomy_revision') if k in original}
    fresh.update(schema_version=fresh.get('schema_version', 1), status='ready', questions=[], archived_questions=[], trashed_questions=[], assets={})
    staging = transaction.folder / 'empty-question-bank'
    staging.mkdir()
    json_write(staging / 'catalog.json', fresh)
    snapshot = transaction.folder / 'question-bank-backup'
    shutil.copytree(source, snapshot)
    backup = prefix + 'Data/Question Bank Backups/' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4)
    transaction.tree(snapshot, backup, seed=True)
    transaction.tree(staging, relative)
    return backup

def install_app(transaction, unpacked, app):
    files = list(app_files(unpacked, app))
    prefix = 'Apps/' + APPS[app] + '/'
    profile = transaction.root / prefix / 'Data/edition.json'
    if app == 'whiz' and profile.is_file():
        current = json.loads(profile.read_text('utf-8-sig'))
        if current.get('edition') == 'math135-instructor':
            incoming = Path(unpacked) / 'Seed/edition.json'
            if incoming.is_file():
                value = json.loads(incoming.read_text('utf-8'))
                if value.get('edition') == 'materials':
                    transaction.put(incoming, prefix + 'Data/edition.json')
    trees = []
    if (unpacked / 'App').is_dir():
        trees.append((unpacked / 'App', prefix + 'App', False))
    if (unpacked / 'LocalTools').is_dir():
        for name in ('App', 'site', 'companions/Application/extension'):
            child = unpacked / 'LocalTools' / name
            if child.is_dir():
                trees.append((child, 'Application/' + name, False))
    if (unpacked / 'Tools').exists() and app == 'scope':
        trees.append((unpacked / 'Tools/Rubric Lens/extension', prefix + 'Tools/Rubric Lens/extension', False))
    if (unpacked / 'Tools').exists() and app == 'whiz':
        trees.append((unpacked / 'Tools/Course Organizer/extension', prefix + 'Tools/Course Organizer/extension', False))
    content = unpacked / 'Content'
    if content.exists():
        for child in content.iterdir():
            relative = prefix + ('Data/' if child.name == 'Question Bank' else '') + child.name
            if not child.is_dir():
                raise ValueError('Content must be a folder.')
            trees.append((child, relative, True))
    modules = unpacked / 'Modules'
    if modules.exists():
        for module in modules.iterdir():
            base = module if module.name == 'Math135' else module / 'tools'
            for child in base.iterdir():
                relative = prefix + 'Data/PrivateModules/' + module.name + ('' if module.name == 'Math135' else '/tools') + '/' + child.name
                if module.name == 'Math135' and child.name == 'App':
                    for name in ('Audit', 'Teaching Schedules', 'schedule-mappings.json'):
                        old = transaction.root / relative / name
                        fresh = child / name
                        if old.exists() and (not fresh.exists()):
                            if linked(old) or (old.is_dir() and any((linked(p) for p in old.rglob('*')))):
                                raise ValueError('A retained local module folder contains a link.')
                            if old.is_dir():
                                shutil.copytree(old, fresh)
                            else:
                                shutil.copy2(old, fresh)
                extension = {'Grader/Rubric Lens': 'extension', 'Integrity/Form Autofill': 'Chrome Extension'}.get(module.name + '/' + child.name)
                if extension:
                    trees.append((child / extension, relative + '/' + extension, False))
                else:
                    trees.append((child, relative, False))
    covered = [relative + '/' for _, relative, _ in trees]
    for source, relative, seed in files:
        if not any((relative.startswith(part) for part in covered)):
            transaction.put(source, relative, seed)
    for source, relative, seed in trees:
        transaction.tree(source, relative, seed)

def app_files(unpacked, app):
    for file in Path(unpacked).rglob('*'):
        if not file.is_file():
            continue
        rel = file.relative_to(unpacked)
        first = rel.parts[0]
        name = '/'.join(rel.parts[1:])
        if app == 'mods' and first == 'Binary' and (name == 'Application.exe'):
            yield (file, 'Apps/Application/build/Application.exe', False)
        elif app == 'mods' and first == 'Assets' and (name in ('branding/Application.svg', 'branding/Application.ico', 'branding/palette.json')):
            yield (file, 'Apps/Application/assets/' + name, False)
        elif app == 'mods' and first == 'Seed' and (name == 'catalog.json'):
            if json.loads(file.read_text('utf-8')) != {'schema': 1, 'games': []}:
                raise ValueError('Application seed must be an empty library with no local records.')
            yield (file, 'Apps/Application/Data/catalog.json', True)
        elif app == 'mods':
            raise ValueError('A Application package contains an unapproved file category.')
        elif app == 'schwing' and first == 'Binary' and (name == 'Application.exe'):
            yield (file, 'Apps/Application/build/Application.exe', False)
        elif app == 'schwing' and first == 'Assets' and (file.suffix.lower() in ('.svg', '.png', '.ico', '.json')):
            yield (file, 'Apps/Application/assets/' + name, False)
        elif app == 'schwing' and first == 'Marker' and (name == 'app.json'):
            yield (file, 'Apps/Application/app.json', False)
        elif first == 'App':
            yield (file, 'Apps/' + APPS[app] + '/App/' + name, False)
        elif first == 'LocalTools' and app == 'wizzy' and (rel.parts[1] in ('App', 'site') or name == 'THIRD-PARTY-NOTICES.txt' or name in ('scripts/open_party_test.ps1', 'scripts/stop_party_test.ps1') or (name in {'party/' + n for n in ('api.mjs', 'backup.mjs', 'd1-store.mjs', 'domain.mjs', 'local-server.mjs', 'sqlite-store.mjs', 'roll20-exporter.js')}) or (name in {'companions/Application/' + n for n in ('setup.py', 'setup.html', 'setup.mjs', 'Application.ico', 'icon.svg')}) or (name.startswith('companions/Application/extension/') and file.suffix.lower() in ('.js', '.json', '.html', '.css', '.png', '.svg', '.ico', '.txt'))):
            yield (file, 'Application/' + name, False)
        elif first == 'Tools' and app == 'whiz' and (len(rel.parts) > 3) and (tuple(rel.parts[1:3]) == ('Course Organizer', 'extension')) and (file.suffix.lower() in ('.js', '.json', '.html', '.css', '.png', '.svg', '.txt', '.ico')):
            yield (file, 'Apps/G-Whiz/Tools/' + name, False)
        elif first == 'Tools' and app == 'scope' and (len(rel.parts) > 3) and (tuple(rel.parts[1:3]) == ('Rubric Lens', 'extension')) and (file.suffix.lower() in ('.js', '.json', '.html', '.css', '.png', '.svg', '.txt')):
            yield (file, 'Apps/G-Scope/Tools/' + name, False)
        elif first == 'Seed':
            yield (file, 'Apps/' + APPS[app] + '/Data/' + name, True)
        elif first == 'Content' and rel.parts[1] in ('mh-git', 'dnd-git', 'Question Bank'):
            prefix = 'Data/' if rel.parts[1] == 'Question Bank' else ''
            yield (file, 'Apps/' + APPS[app] + '/' + prefix + name, True)
        elif first == 'Modules' and app == 'spot' and (len(rel.parts) > 4 and rel.parts[1] in ('Grader', 'Recommendations', 'Integrity') and (rel.parts[2] == 'tools') and (rel.parts[3] in ('App', 'vendor')) or (len(rel.parts) > 3 and rel.parts[1] == 'Math135' and (rel.parts[2] == 'App')) or (len(rel.parts) > 5 and tuple(rel.parts[1:5]) in {('Grader', 'tools', 'Rubric Lens', 'extension'), ('Integrity', 'tools', 'Form Autofill', 'Chrome Extension')} and (file.suffix.lower() in ('.js', '.json', '.html', '.css', '.png', '.svg', '.txt')))):
            yield (file, 'Apps/G-Vault/Data/PrivateModules/' + name, False)
        elif first == 'Framework' and app == 'spot' and (file.suffix.lower() in ('.py', '.cls', '.sty')):
            yield (file, 'Apps/G-Vault/Data/PrivateSource/' + name, False)
        else:
            raise ValueError('An app package contains an unapproved file category.')

def install_course(transaction, unpacked, package):
    """Replace only a verified course base; personal questions never enter this tree."""
    manifest = Path(unpacked) / 'manifest.json'
    value = json.loads(manifest.read_text('utf-8'))
    if value.get('schema') != 1 or value.get('course') != package['course'] or (not isinstance(value.get('files'), dict)):
        raise ValueError('Invalid course ownership manifest.')
    actual = {p.relative_to(unpacked).as_posix() for p in Path(unpacked).rglob('*') if p.is_file()}
    if actual != {'manifest.json', *('Base/' + name for name in value['files'])}:
        raise ValueError('Course files differ from their ownership manifest.')
    for name, checksum in value['files'].items():
        if not HEX.fullmatch(checksum) or digest(contained(Path(unpacked) / 'Base', name)) != checksum:
            raise ValueError('Course content checksum differs from its ownership manifest.')
    if not (Path(unpacked) / 'Base').is_dir():
        raise ValueError('A course package has no base content.')
    transaction.tree(Path(unpacked) / 'Base', package['target'] + '/Base')
    transaction.put(manifest, package['target'] + '/manifest.json')

def process_running(app_root):
    if os.name != 'nt':
        return False
    value = base64.b64encode(str(Path(app_root).absolute()).encode()).decode()
    script = "$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + value + '\'));$n=@(Get-CimInstance Win32_Process -Filter "Name=\'pythonw.exe\' OR Name=\'python.exe\'" | Where-Object {$_.CommandLine -and $_.CommandLine.IndexOf($p,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -match \'desktop.py\'}).Count;[Console]::Write($n)'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()], capture_output=True, text=True, creationflags=134217728)
    if result.returncode:
        raise ValueError('Could not check running desktop apps.')
    return int(result.stdout.strip() or '0') > 0

def stop_idle_backend(app_root):
    status = Path(app_root) / 'Temp/server-status.json'
    if not status.is_file():
        return
    value = json.loads(status.read_text('utf-8-sig'))
    url = value.get('url', '')
    if not re.fullmatch('http://127\\.0\\.0\\.1:\\d+', url):
        raise ValueError('The app service address is invalid.')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(route):
        with opener.open(url + route, timeout=3) as response:
            return json.load(response)
    try:
        health = get('/api/health')
    except OSError:
        return
    expected = 'GScope' if Path(app_root).name == 'G-Scope' else 'GWhizDnD' if Path(app_root).name == 'Application' else 'GWhiz'
    if Path(health.get('root', '')).resolve() != Path(app_root).resolve() or health.get('app') != expected:
        raise ValueError('The service does not belong to this installation.')
    token = get('/api/bootstrap')['token']
    request = urllib.request.Request(url + '/api/installer-stop', data=b'{}', headers={'Content-Type': 'application/json', 'X-App-Token': token})
    try:
        with opener.open(request, timeout=25) as response:
            json.load(response)
    except OSError:
        raise ValueError('The app service could not stop safely. Finish its work, reopen and close the app, then retry setup.')
    for _ in range(50):
        try:
            get('/api/health')
        except OSError:
            return
        time.sleep(0.1)
    raise ValueError('The app service is still running; no update was applied.')

def stop_local_tools(app_root):
    root = Path(app_root).parent.parent / 'Application'
    state = root / 'Data/server-state.json'
    if not state.is_file():
        return
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = 'http://127.0.0.1:5095'

    def health():
        with opener.open(url + '/__wizzy/health', timeout=3) as response:
            return json.load(response)
    try:
        value = health()
    except OSError:
        return
    if value.get('app') != 'Application-local-v1' or Path(value.get('root', '')).resolve() != root.resolve():
        raise ValueError('Another local Application installation is running.')
    token = json.loads(state.read_text('utf-8'))['token']
    request = urllib.request.Request(url + '/__wizzy/stop', data=b'{}', headers={'X-Wizzy-Token': token})
    with opener.open(request, timeout=5) as response:
        json.load(response)
    for _ in range(50):
        try:
            health()
        except OSError:
            return
        time.sleep(0.1)
    raise ValueError('Local Application could not stop safely.')

def selected_apps(apps):
    if not apps or set(apps) - set(APPS):
        raise ValueError('Choose one or more G-Works apps.')
    selected = list(dict.fromkeys(apps))
    if 'scope' in selected and 'whiz' not in selected:
        selected.insert(0, 'whiz')
    return selected

def validate_custom_course(value):
    if not value:
        return None
    from setup_content import course
    return course(value)

def require_course_workspace(root, courses, custom=None):
    root = Path(root)
    app = root / 'Apps/G-Whiz'
    saved = app / 'Data/custom-courses.json'
    registered = json.loads(saved.read_text('utf-8-sig')).get('courses', []) if saved.is_file() else []
    if custom:
        code = custom['code']
        if code in courses or any((row.get('code') == code for row in registered)) or (root / 'Shared/Courses' / code / 'manifest.json').is_file() or (app / 'mh-git' / ('mh-' + code + '-course-documents')).is_dir():
            raise ValueError('That course is already selected or installed. Choose a different number for a new empty course.')
        return
    if any((code not in ('136', 'discontinued') for code in courses)):
        return
    if any(((p / 'manifest.json').is_file() and p.name not in ('136', 'discontinued') for p in (root / 'Shared/Courses').glob('*'))):
        return
    if registered:
        return
    if any((p.is_dir() and p.name != 'mh-136-course-documents' for p in (app / 'mh-git').glob('mh-*-course-documents'))):
        return
    raise ValueError('Select at least one course pack or create an empty course workspace for G-Whiz.')

def plan(catalog, apps, courses=None):
    apps = selected_apps(apps)
    available = {p['course'] for p in catalog['packages'] if p.get('kind') == 'course'}
    selected = set(courses or []) if 'whiz' in apps else set()
    if selected - available:
        raise ValueError('A selected course is not available in this release.')
    needed = {p['id']: p for p in catalog['packages'] if p.get('app') in apps and (p['kind'] != 'course' or p['course'] in selected)}
    if set(apps) - {p.get('app') for p in needed.values() if p['kind'] == 'app'}:
        raise ValueError('A selected app is not available in this release channel.')
    index = {p['id']: p for p in catalog['packages']}
    pending = list(needed.values())
    while pending:
        for ident in pending.pop().get('requires', []):
            if ident not in index:
                raise ValueError('Release dependency is missing.')
            if ident not in needed:
                needed[ident] = index[ident]
                pending.append(index[ident])
    return sorted(needed.values(), key=lambda p: (p['kind'] == 'app', p['id']))

def require_migrated_layout(root, catalog, apps):
    """Do not let a code update hide records that still belong to the 1.x layout."""
    if release_version(catalog['release']) < (2, 0, 0) or not set(apps) & {'spot', 'whiz', 'scope'}:
        return
    record = root / '.gworks/installation.json'
    if not record.is_file():
        return
    previous = json.loads(record.read_text('utf-8-sig'))
    if release_version(previous.get('release', '0.0.0')) >= (2, 0, 0):
        return
    current = {name for ident, name in APPS.items() if APP_SUITES[ident] == 'professional'}
    legacy = any(((app / 'mh-git').exists() or any((app / 'Data/Question Bank').glob('*')) or (app / 'Data/PrivateModules/Grader/grader.sqlite').is_file() for app in (root / 'Apps').glob('*') if app.is_dir() and app.name not in current))
    if legacy:
        raise ValueError('This existing installation needs the G-Works 2.0 data migration before Setup can update it. Keep this installation folder and complete the owner migration first; your materials and grading records have not been moved or changed.')

def install(catalog, options, key, offline, *, report=emit, configure=None):
    root = validate_root(options['root'])
    apps = selected_apps(options['apps'])
    options['apps'] = apps
    require_migrated_layout(root, catalog, apps)
    suite = installation_suite(root, apps, options.get('suite'))
    legacy_dependencies = require_suite_release(catalog, options, suite)
    if configure:
        from prerequisites import validate_ai_ownership
        validate_ai_ownership(root, options)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.gworks/install.lock'
    lock.parent.mkdir(exist_ok=True)
    marker = root / '.gworks/root.json'
    if not marker.exists():
        json_write(marker, {'schema': 1, 'id': secrets.token_hex(16), 'suite': suite})
    if lock.exists():
        try:
            old = json.loads(lock.read_text('utf-8'))
            alive = pid_alive(old['pid'])
        except Exception:
            alive = True
        if alive:
            raise ValueError('An install is already running. Close it before continuing.')
        if not options.get('repair'):
            raise ValueError('An install was interrupted. Choose Recover interrupted setup before continuing.')
        lock.unlink()
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('Another installer started. Wait for it to finish.')
    with os.fdopen(lock_fd, 'w') as stream:
        json.dump({'pid': os.getpid()}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    transaction = None
    try:
        installed = root / '.gworks/installation.json'
        prior = json.loads(installed.read_text('utf-8')) if installed.is_file() else {}
        previous_names = previous_app_names(root, prior)
        if any((process_running(root / 'Apps' / name) for app in apps for name in {APPS[app], previous_names.get(app, APPS[app])})):
            raise ValueError('Close the selected desktop apps before updating them.')
        dependencies_only = bool(options.get('dependencies_only'))
        if dependencies_only and any((app not in prior.get('apps', {}) or not (root / 'Apps' / APPS[app] / ('build/' + APPS[app] + '.exe' if app in ('mods', 'schwing') else 'App')).exists() for app in apps)):
            raise ValueError('Install the selected apps before changing only their dependencies.')
        for app in apps:
            previous = prior.get('apps', {}).get(app, {}).get('version')
            if previous and release_version(catalog['release']) < release_version(previous):
                raise ValueError('This installer is older than the installed app. Download the current release.')
        recover(root)
        transaction = Transaction(root)
        for app, old_name in previous_names.items():
            if app in apps and (root / 'Apps' / old_name).is_dir() and (not (root / 'Apps' / APPS[app]).exists()):
                stop_idle_backend(root / 'Apps' / old_name)
                transaction.move('Apps/' + old_name, 'Apps/' + APPS[app])
        catalog, token, service = authorize(catalog, apps, options.pop('activation_code', ''), key, transaction.folder)
        require_suite_release(catalog, options, suite)
        available = {p['course'] for p in catalog['packages'] if p.get('kind') == 'course'}
        selected_courses = [code for code in options.get('courses', prior.get('courses', [])) if code in available]
        custom = validate_custom_course(options.get('custom_course'))
        if not dependencies_only and 'whiz' in apps and (release_version(catalog['release']) >= (2, 2, 0)):
            require_course_workspace(root, selected_courses, custom)
        planned = plan(catalog, apps, selected_courses)
        app_manifests = [p for p in planned if p['kind'] == 'app']
        if any((p.get('app') not in apps or APP_SUITES.get(p.get('app')) != suite for p in app_manifests)):
            raise ValueError('An app dependency belongs to a different suite.')
        selected = [p for p in planned if not dependencies_only or p['kind'] not in ('app', 'course')]
        staged = []
        if legacy_dependencies:
            selected = [p for p in selected if p['kind'] == 'tool-installer' or p.get('runtime_role') in DEPENDENCY_ROLES]
            report('Maintaining dependencies only. The pre-split app and launcher packages will not be applied.')
        if configure:
            from prerequisites import select_tools
            selected = select_tools(selected, options)
        for package in selected:
            report('Verifying ' + package['id'])
            private = package.get('app') in {a['id'] for a in catalog.get('applications', []) if a.get('visibility') == 'private'} and catalog.get('channel') != 'owner'
            archive = get_package(package, offline, root / '.gworks/downloads', token if private else None, service)
            unpacked = transaction.folder / package['id']
            if package['kind'] == 'tool-installer' and package.get('format') == 'exe':
                unpacked.mkdir()
                shutil.copy2(archive, unpacked / 'setup.exe')
            else:
                extract(archive, unpacked, package.get('expanded_limit', 40 * 1024 ** 3))
            staged.append((package, unpacked, archive))
        for package, unpacked, _ in staged:
            if package['kind'] == 'runtime':
                transaction.runtime(unpacked, package['target'], package)
        if configure:
            configure(root, staged, options, report)
        if any((process_running(root / 'Apps' / APPS[a]) for a in apps)):
            raise ValueError('Close the selected desktop apps before updating them.')
        for app in apps:
            app_root = contained(root, 'Apps/' + APPS[app])
            stop_idle_backend(app_root)
            if app == 'wizzy':
                stop_local_tools(app_root)
        for app in apps:
            if dependencies_only:
                continue
            parts = [(package, unpacked) for package, unpacked, _ in staged if package['kind'] == 'app' and package['app'] == app]
            combined = parts[0][1]
            if len(parts) > 1:
                combined = transaction.folder / ('merged-' + app)
                combined.mkdir()
                for package, unpacked in parts:
                    list(app_files(unpacked, app))
                    for source in unpacked.rglob('*'):
                        if not source.is_file():
                            continue
                        target = contained(combined, source.relative_to(unpacked).as_posix())
                        if target.exists():
                            raise ValueError('App package parts contain overlapping files.')
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, target)
            if app == 'whiz' and options.get('keep_custom_questions', True) is False:
                backup = archive_question_bank(transaction)
                if backup:
                    report('Previous question bank saved locally; starting a fresh bank.')
            report('Installing ' + APPS[app])
            install_app(transaction, combined, app)
            launcher = transaction.folder / (app + '.cmd')
            launcher.write_text('@echo off\nstart "" "%~dp0build\\' + APPS[app] + '.exe" %*\n' if app in ('mods', 'schwing') else '@echo off\nstart "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0App\\Launch.ps1" -Desktop %*\n', 'utf-8')
            transaction.put(launcher, 'Apps/' + APPS[app] + '/Open ' + APPS[app] + '.cmd')
        for package, unpacked, _ in staged:
            if package['kind'] == 'course':
                install_course(transaction, unpacked, package)
        runtime_index = {p['id']: p for p in selected if p['kind'] == 'runtime'}
        for package in app_manifests:
            for name, ident in package.get('runtime_links', {}).items():
                if name not in ('python', 'DesktopRuntime', 'poppler', 'GeneralAI', 'texlive', 'TeachingApp', 'TeachingSupport', 'ScopeVendor'):
                    raise ValueError('Unexpected runtime link.')
                if legacy_dependencies and ident not in runtime_index:
                    continue
                (transaction.local_runtime if name in ('python', 'GeneralAI', 'ScopeVendor', 'DesktopRuntime') else transaction.link)('Apps/' + APPS[package['app']] + '/Dependencies/' + name, root / runtime_index[ident]['target'])
            for relative in package.get('module_runtime_links', []):
                if package['app'] != 'spot' or not re.fullmatch('Data/PrivateModules/(?:Math135/runtime|(?:Recommendations|Integrity)/tools/runtime)/python', relative):
                    raise ValueError('Unexpected module runtime path.')
                ident = package.get('module_runtime_overrides', {}).get(relative, package['runtime_links']['python'])
                if legacy_dependencies and ident not in runtime_index:
                    continue
                transaction.local_runtime('Apps/G-Vault/' + relative, root / runtime_index[ident]['target'])
            if package.get('local_tools_runtime'):
                if package['app'] != 'wizzy':
                    raise ValueError('Unexpected local tools runtime.')
                transaction.local_runtime('Application/Runtime/python', root / runtime_index[package['runtime_links']['python']]['target'])
        if not dependencies_only and 'whiz' in apps and custom:
            prefix = 'Apps/G-Whiz/Data/'
            path = root / prefix / 'custom-courses.json'
            saved = json.loads(path.read_text('utf-8-sig')) if path.is_file() else {'schema': 1, 'courses': []}
            if not any((row['code'] == custom['code'] for row in saved['courses'])):
                saved['courses'].append(custom)
            source = transaction.folder / 'custom-courses.json'
            json_write(source, saved)
            transaction.put(source, prefix + 'custom-courses.json')
        profile = options.get('instructor_profile')
        if profile:
            from setup_content import profile as validate_profile
            profile = validate_profile(profile)
            for app in apps:
                if APP_SUITES[app] != 'professional':
                    continue
                source = transaction.folder / (app + '-instructor-profile.json')
                json_write(source, profile)
                transaction.put(source, 'Apps/' + APPS[app] + '/Data/instructor-profile.json', True)
        if configure:
            from prerequisites import seed_configuration
            seed_configuration(root, apps, options, transaction)
        record = root / '.gworks/installation.json'
        previous = json.loads(record.read_text('utf-8')) if record.exists() else {'schema': 1, 'apps': {}}
        if not dependencies_only:
            for app in apps:
                previous['apps'][app] = {'name': APPS[app], 'version': catalog['release']}
        if not dependencies_only and 'whiz' in apps:
            previous['courses'] = sorted(set(prior.get('courses', [])) | {p['course'] for p in selected if p['kind'] == 'course'})
        launcher = next((p for p in selected if p.get('runtime_role') == 'Launcher'), None)
        if launcher:
            launcher_name = SUITE_NAMES[suite] + '.exe'
            previous['launcher'] = launcher['target'] + '/' + launcher_name
            previous['launcher_version'] = catalog['release']
            transaction.put(contained(root, previous['launcher']), 'Shared/Launcher/' + launcher_name)
        commands = next((p for p in selected if p.get('runtime_role') == 'Commands'), None)
        if commands and suite == 'professional':
            for name in ('gitbash.sh', 'Git-Bash-Commands.txt'):
                source = contained(root, commands['target'] + '/' + name)
                if source.is_file():
                    transaction.put(source, 'Shared/Commands/' + name)
        if options.get('installer_exe'):
            installer_name = 'Install ' + SUITE_NAMES[suite] + '.exe'
            source = Path(options['installer_exe']).absolute()
            target = root / installer_name
            if source.suffix.casefold() != '.exe' or not source.is_file() or linked(source):
                raise ValueError('The setup executable is unavailable.')
            if source.resolve() != target.resolve():
                transaction.put(source, installer_name)
        previous.update({'suite': suite, 'release': previous.get('release', catalog['release']) if legacy_dependencies else catalog['release'], 'installed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'channel': catalog.get('channel', 'public')})
        root_record = json.loads((root / '.gworks/root.json').read_text('utf-8-sig'))
        root_record['suite'] = suite
        root_marker = transaction.folder / 'root.json'
        json_write(root_marker, root_record)
        transaction.put(root_marker, '.gworks/root.json')
        marker = transaction.folder / 'installation.json'
        json_write(marker, previous)
        transaction.put(marker, '.gworks/installation.json')
        transaction.commit()
        try:
            transaction.compact()
        except OSError:
            report('Installation is complete; its local recovery folder was retained.')
        if not options.get('keep_downloads'):
            for package in selected:
                cached = contained(root, '.gworks/downloads/' + package['sha256'] + '.pkg')
                try:
                    cached.unlink(missing_ok=True)
                except OSError:
                    report('A downloaded package is still in use; its cache copy was retained.')
        report('Installation complete.', complete=True, root=str(root), apps=apps)
        return previous
    except BaseException:
        for package in locals().get('selected', []):
            with contextlib.suppress(OSError):
                contained(root, '.gworks/downloads/' + package['sha256'] + '.part').unlink(missing_ok=True)
        if transaction and transaction.folder.exists():
            transaction.rollback()
            try:
                transaction.compact()
            except OSError:
                pass
        raise
    finally:
        lock.unlink(missing_ok=True)

def main():
    if sys.argv[1:] == ['--detect']:
        from prerequisites import discover
        raw = '' if sys.stdin.isatty() else sys.stdin.read()
        options = json.loads(raw) if raw.strip() else {}
        print(json.dumps(discover(options.get('root'))))
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalogue', required=True)
    parser.add_argument('--signature', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--offline', required=True)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    key = json.loads(Path(args.key).read_text('utf-8'))
    value = catalogue(args.catalogue, args.signature, key)
    options = json.load(sys.stdin)
    if options.get('check_updates') and value.get('catalogue_url'):
        try:
            envelope = json.loads(https_request(value['catalogue_url']))
            raw = base64.b64decode(envelope['catalogue'], validate=True)
            updated = Path(args.catalogue).with_name('updated-catalogue.json')
            updated.write_bytes(raw)
            signature = updated.with_suffix('.sig')
            signature.write_text(envelope['signature'], 'ascii')
            candidate = catalogue(updated, signature, key)
            selected = select_release_update(value, candidate)
            if selected is value:
                emit('No newer release is available; using the verified bundled release.')
            elif value.get('channel') == 'owner':
                emit('A newer online release is available. Private app downloads use an activation code; uncheck the release-channel option to use the owner bundle offline.')
            value = selected
        except (OSError, urllib.error.URLError):
            emit('The update channel is unavailable; using the verified bundled release.')
    if args.plan:
        emit('Installation plan', packages=[p['id'] for p in plan(value, options['apps'], options.get('courses'))])
        return
    from prerequisites import configure
    install(value, options, key, args.offline, configure=configure)
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit(str(error), error=True)
        raise SystemExit(1)
