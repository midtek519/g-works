"""Track and apply shared app updates without rebuilding instructor user data."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, shutil, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from distribution_policy import APP_DEVELOPMENT_DIRS, APP_DEVELOPMENT_FILES, prune_folder
from package_layout import instructor_folder

EXCLUDE = APP_DEVELOPMENT_DIRS

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def app_files(root):
    app = Path(root).resolve() / 'App'
    files = {}
    for folder, dirs, names in os.walk(app):
        rel = Path(folder).relative_to(app)
        dirs[:] = [d for d in dirs if d not in EXCLUDE and not (rel.parts == ('course_adapters',) and d != '135')]
        for name in names:
            p = Path(folder) / name
            if not rel.parts and name in APP_DEVELOPMENT_FILES:
                continue
            if p.suffix in {'.pyc', '.pyo'}:
                continue
            files[p.relative_to(app).as_posix()] = p
    return files

def manifest(root):
    return {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in app_files(root).items()}

def paths(root):
    root = Path(root).resolve()
    target = instructor_folder(root)
    profile = target / 'Data/edition.json'
    if not profile.is_file():
        profile = target / 'edition.json'
    if not profile.is_file():
        raise ValueError('The independent G-Whiz teaching folder is missing.')
    edition = json.loads(profile.read_text('utf-8-sig'))
    if edition.get('edition') != 'math135-instructor' or target.is_symlink() or target.is_junction():
        raise ValueError('Expected the independent Math 135 instructor folder.')
    log = root / 'Maintenance/Instructor Updates'
    log.mkdir(parents=True, exist_ok=True)
    return root, target, log

def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.new')
    temporary.write_text(json.dumps(value, indent=2) + '\n', 'utf-8')
    os.replace(temporary, path)

def status(root):
    root, target, log = paths(root)
    source, installed = manifest(root), manifest(target)
    pending = {'checked': stamp(), 'source': str(root), 'target': str(target),
               'changed': sorted(n for n in source.keys() & installed.keys() if source[n] != installed[n]),
               'missing': sorted(source.keys() - installed.keys()),
               'extra': sorted(installed.keys() - source.keys())}
    state_path = log / 'SYNC_STATE.json'
    state = json.loads(state_path.read_text('utf-8')) if state_path.exists() else {}
    baseline = state.get('installed_app_sha256', {})
    pending['instructor_changes_since_last_sync'] = sorted(n for n in installed if n in baseline and installed[n] != baseline[n])
    write_json(log / 'PENDING.json', pending)
    lines = ['G-Whiz Instructor pending shared app updates', 'Checked: ' + pending['checked'], '',
             'Run App/sync_instructor.py status after shared G-Whiz edits.',
             'Run App/sync_instructor.py update --zip when an instructor update is requested.',
             'Status compares actual app bytes; a new pending list does not update the instructor app.', '']
    for field, title in [('changed', 'Changed shared files'), ('missing', 'New shared files'), ('extra', 'Instructor-only app files'), ('instructor_changes_since_last_sync', 'Instructor edits since baseline')]:
        lines += [title + ':'] + (['  ' + n for n in pending[field]] or ['  None']) + ['']
    (log / 'PENDING.txt').write_text('\n'.join(lines), 'utf-8')
    return pending

def record_release(root, target, reason='Clean instructor package generated'):
    root = Path(root).resolve()
    if Path(target).resolve() != instructor_folder(root):
        return
    _, _, log = paths(root)
    write_json(log / 'SYNC_STATE.json', {'updated': stamp(), 'reason': reason,
               'source_app_sha256': manifest(root), 'installed_app_sha256': manifest(target)})
    with (log / 'CHANGELOG.txt').open('a', encoding='utf-8') as stream:
        stream.write('\n' + stamp() + ' — ' + reason + '\n')
    status(root)

def update(root):
    root, target, log = paths(root)
    pending = status(root)
    files = app_files(root)
    if not any(pending[k] for k in ('changed', 'missing', 'extra')):
        return {'updated': False, 'message': 'Instructor shared app files are current.'}
    key = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = log / 'Backups' / key
    backup.mkdir(parents=True, exist_ok=False)
    # Metadata proof only: never read private saved work or course records.
    profile = target / 'Data/edition.json'
    if not profile.is_file():
        profile = target / 'edition.json'
    protected = [profile, target / 'Data', target / 'mh-git', target / 'Dependencies']
    before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in protected}
    for name in pending['changed'] + pending['extra']:
        old = target / 'App' / name
        copy = backup / 'App' / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, copy)
    for name in pending['changed'] + pending['missing']:
        destination = target / 'App' / name
        assert destination.resolve().is_relative_to((target / 'App').resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + '.sync-new')
        shutil.copy2(files[name], temporary)
        os.replace(temporary, destination)
    for name in pending['extra']:
        stale = target / 'App' / name
        assert stale.resolve().is_relative_to((target / 'App').resolve())
        stale.unlink()
    assert before == {str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in protected}, 'Protected instructor folders changed'
    assert manifest(root) == manifest(target), 'Shared app files differ after synchronization'
    write_json(backup / 'Update.json', pending)
    with (log / 'CHANGELOG.txt').open('a', encoding='utf-8') as stream:
        stream.write('\n' + stamp() + ' — Shared app update; instructor settings, data, content and runtime preserved.\n')
        for field in ('changed', 'missing', 'extra'):
            stream.write(field + ': ' + ', '.join(pending[field]) + '\n')
        stream.write('Recovery copy: ' + str(backup) + '\n')
    record_release(root, target, 'Shared app synchronized; authoring UI, typography and CodeMirror parity verified by file hash')
    return {'updated': True, 'changed': pending['changed'], 'added': pending['missing'], 'removed': pending['extra'], 'backup': str(backup)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'update'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--zip', action='store_true', help='Refresh the instructor ZIP after an update; does not rebuild its saved work.')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    result = update(args.root) if args.action == 'update' else status(args.root)
    if args.action == 'update':
        from package_layout import prepare_layout
        prepare_layout(args.root, paths(args.root)[1])
        _, target, log = paths(args.root)
        backup=log/'Backups'/('release-cleanup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        removed=prune_folder(target,backup)
        if removed:
            write_json(backup/'Removed.json',removed)
            result['release_files_removed']=len(removed)
    if args.zip:
        if args.action != 'update':
            parser.error('--zip requires update')
        from package_beta import make_zip
        result['zip'] = make_zip(paths(args.root)[1])
    if not args.quiet:
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
