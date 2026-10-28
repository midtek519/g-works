"""Export a reviewed public program-source snapshot without installed user data.

Inputs are the hash-checked public release archives, the corresponding staged
installer source, and explicitly named launcher source/resources. An existing
output directory is never overwritten. This command does not access Git/network.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile

PUBLIC_PRODUCTS = {'g-works', 'g-whiz', 'g-scope', 'g-vault', 'g-view', 'g-rater', 'g-report', 'g-keeper'}
PUBLIC_IDENTIFIERS = PUBLIC_PRODUCTS | {'g-extension', 'g-motif', 'g-p', 'g-h', 'g-m', 'g-a'}
PRODUCT = re.compile(r'\bG-[A-Za-z]+\b', re.I)
MACHINE_PATH = re.compile(r'(?:[A-Za-z]:[/\\]+Users[/\\]+(?!Public\b|Default\b)[^/\\\s"\']+|\.cache[/\\]+codex-runtimes|Documents[/\\]+Codex|\.codex[/\\])', re.I)
CODE_SUFFIXES = {'.py', '.js', '.cjs', '.mjs', '.cs', '.css', '.html', '.json', '.sql', '.ps1', '.cmd', '.bat', '.sh', '.md', '.txt', '.tex', '.cls', '.sty', '.bib', '.bst', '.lua'}
IMAGE_SUFFIXES = {'.png', '.ico', '.svg'}
EXCLUDED_PARTS = {'data', 'audit', 'audits', 'teaching schedules', 'backups', 'records', 'credentials', 'output', 'outputs', 'temp', 'vendor', 'node_modules', '__pycache__', '.git', '.gworks'}
STATE_NAMES = {'settings.json', 'author-profile.json', 'instructor-profile.json', 'vault-workspaces.json', 'schedule-mappings.json', 'signature.json'}
LAUNCHER_SOURCES = ('Hub.cs', 'HubArt.cs', 'ReleaseUpdates.cs')
LAUNCHER_BRANDS = ('g-works', 'g-whiz', 'g-scope', 'g-vault', 'g-view', 'g-rater', 'g-report', 'chrome-extensions', 'settings')
INSTALLER_SOURCES = ('engine.py', 'prerequisites.py', 'distribution.py', 'setup_content.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clean_name(name):
    """Validate a ZIP-relative path before reading or joining any entry."""
    if not name or '\\' in name or ':' in name or '\0' in name:
        raise ValueError('Unsafe archive member path.')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Unsafe archive member path.')
    if any(p.endswith((' ', '.')) for p in path.parts):
        raise ValueError('Ambiguous archive member path.')
    return path


def allowed_member(name):
    p = clean_name(name)
    if any(part.casefold() in EXCLUDED_PARTS for part in p.parts):
        return False
    if p.name.casefold() in STATE_NAMES:
        return False
    if p.suffix.lower() == '.json':
        # JSON is also a record format: copy only known program metadata.
        return name in ('tex_requirements.json', 'Seed/edition.json', 'Modules/Math135/App/lookups.json') or bool(re.fullmatch(r'course_adapters/\d{3}/project\.json', name)) or name in (
            'Tools/Course Organizer/extension/manifest.json',
            'Tools/Rubric Lens/extension/manifest.json',
            'Modules/Integrity/tools/Form Autofill/Chrome Extension/manifest.json',
            'Modules/Integrity/tools/Form Autofill/Chrome Extension/form-schema.json',
        )
    if p.suffix.lower() in CODE_SUFFIXES:
        return True
    if p.suffix.lower() in IMAGE_SUFFIXES:
        # Only interface artwork and the institutional letterhead marks.
        return 'icons' in p.parts or p.name.lower().startswith(('g-', 'brand-', 'rsunj_', 'settings.', 'chrome-extensions.'))
    return p.name in ('latexmkrc', 'LICENSE', 'NOTICE')


def inspect_content(label, data):
    if any(m.group().casefold() not in PUBLIC_IDENTIFIERS for m in PRODUCT.finditer(label)):
        raise ValueError('Unapproved product name in source path: ' + label)
    if Path(label).suffix.lower() in IMAGE_SUFFIXES - {'.svg'}:
        return
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Non-text program source: ' + label) from exc
    if MACHINE_PATH.search(text):
        raise ValueError('Machine-specific user/runtime path in source: ' + label)
    if any(m.group().casefold() not in PUBLIC_IDENTIFIERS for m in PRODUCT.finditer(text)):
        raise ValueError('Unapproved product name in source: ' + label)


def archive_members(path):
    with zipfile.ZipFile(path) as archive:
        seen = set()
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = str(clean_name(info.filename))
            if name.casefold() in seen:
                raise ValueError('Duplicate archive member path.')
            seen.add(name.casefold())
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Linked archive member is not a program source.')
            if info.file_size > 20_000_000:
                # Source snapshots do not contain large assets/bundles.
                if allowed_member(name):
                    raise ValueError('Oversized program source entry.')
                continue
            if allowed_member(name):
                yield name, archive.read(info)


def build_snapshot(release, installer):
    release = Path(release).resolve()
    installer = Path(installer).resolve()
    manifest = json.loads((release / 'public-upload-manifest.json').read_text('utf-8'))
    catalogue = json.loads((release / 'public-catalogue.json').read_text('utf-8'))
    if manifest.get('visibility') != 'public' or manifest.get('suite') != 'professional':
        raise ValueError('A public professional release is required.')
    if {a['name'] for a in catalogue.get('applications', [])} != {'G-Whiz', 'G-Scope', 'G-Vault'}:
        raise ValueError('Unexpected application catalogue.')
    version = catalogue['release']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version.')
    inputs = {e['name']: e for e in manifest['files']}
    entries = {}
    provenance = []
    source_archives = []

    def add(target, data, origin):
        target = str(clean_name(target))
        if target.casefold() in {p.casefold() for p in entries}:
            raise ValueError('Source destination collision: ' + target)
        inspect_content(target, data)
        entries[target] = data
        provenance.append({'path': target, 'sha256': sha(data), 'bytes': len(data), 'source': origin})

    def checked_archive(name):
        if name not in inputs:
            raise ValueError('Program archive is absent from public upload manifest: ' + name)
        expected = inputs[name]
        path = release / name
        data = path.read_bytes()
        if sha(data) != expected['sha256'] or len(data) != expected['bytes']:
            raise ValueError('Release artifact changed after manifest generation: ' + name)
        source_archives.append({'name': name, 'sha256': sha(data)})
        return path

    mappings = {
        'shared-teaching-app.zip': 'Shared/TeachingApp/2.0.0',
        'shared-commands.zip': 'Shared/Commands',
        'teaching-support.zip': 'Shared/TeachingSupport',
        f'whiz-{version}.zip': 'Apps/G-Whiz',
        f'scope-{version}.zip': 'Apps/G-Scope',
        f'spot-{version}.zip': 'Apps/G-Vault',
    }
    for name, target in mappings.items():
        for member, data in archive_members(checked_archive(name)):
            add(target + '/' + member, data, name + '!' + member)

    # Read installer Python from the built bootstrap, then require the staged
    # readable sources to match it exactly before including Wizard.cs.
    bootstrap = release / 'bootstrap-public.zip'
    staged = release / 'professional-setup-source'
    with zipfile.ZipFile(bootstrap) as archive:
        for name in INSTALLER_SOURCES:
            data = archive.read('Installer/' + name)
            if data != (staged / name).read_bytes():
                raise ValueError('Staged installer differs from built release: ' + name)
            add('Maintenance/Installer/' + name, data, bootstrap.name + '!Installer/' + name)
        public_key = archive.read('Installer/public-key.json')
        if public_key != (installer / 'public-key.json').read_bytes():
            raise ValueError('Release public key differs from launcher key.')
        add('Maintenance/Installer/public-key.json', public_key, bootstrap.name + '!Installer/public-key.json')
    add('Maintenance/Installer/Wizard.cs', (staged / 'Wizard.cs').read_bytes(), 'professional-setup-source/Wizard.cs')
    source_archives.append({'name': bootstrap.name, 'sha256': sha(bootstrap.read_bytes())})
    for name in LAUNCHER_SOURCES:
        add('Maintenance/Installer/Hub/' + name, (installer / 'Hub' / name).read_bytes(), 'reviewed-launcher/' + name)
    for name in LAUNCHER_BRANDS:
        member = 'Hub/Assets/brand-' + name + '.png'
        add('Maintenance/Installer/' + member, (installer / member).read_bytes(), 'reviewed-launcher/' + member)
    add('Maintenance/Installer/Hub/g-works.ico', (installer / 'Hub/g-works.ico').read_bytes(), 'reviewed-launcher/g-works.ico')
    add('Maintenance/Installer/Hub/build.ps1', LAUNCHER_BUILD.encode(), 'generated/public-launcher-build')
    add('Maintenance/Installer/export_sources.py', Path(__file__).read_bytes(), 'reviewed-exporter/export_sources.py')
    add('README.md', README.format(version=version).encode(), 'generated/readme')
    add('.gitignore', GITIGNORE.encode(), 'generated/gitignore')
    receipt = {
        'schema': 1, 'release': version, 'policy': 'public-program-source-only',
        'included': ['professional program code', 'professional interface artwork', 'Rutgers Mathematics TeX framework', 'professional installer and launcher source'],
        'excluded': ['installed user data and settings', 'credentials and signatures', 'historical audits and schedules', 'course banks and handouts', 'runtime and third-party vendor code', 'compiled executables and libraries'],
        'source_archives': sorted(source_archives, key=lambda r: r['name']),
        'files': sorted(provenance, key=lambda r: r['path']),
    }
    entries['SOURCE_MANIFEST.json'] = (json.dumps(receipt, indent=2, ensure_ascii=False) + '\n').encode()
    return entries, receipt


def write_snapshot(destination, entries):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Choose a new source snapshot directory; existing files are preserved.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.source-export-', dir=destination.parent) as stage:
        root = Path(stage) / 'snapshot'
        root.mkdir()
        for name, data in entries.items():
            path = root / clean_name(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # Rename only the newly created snapshot. Never delete a checkout.
        root.rename(destination)
    return destination


LAUNCHER_BUILD = '''$ErrorActionPreference = 'Stop'
$launcherRoot = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$resources = @('/resource:' + (Join-Path $launcherRoot '../public-key.json') + ',gworks-public-key.json')
foreach ($brand in @('g-works','g-whiz','g-scope','g-vault','g-view','g-rater','g-report','chrome-extensions','settings')) {
    $resources += '/resource:' + (Join-Path $launcherRoot ('Assets/brand-' + $brand + '.png')) + ',Brand.' + $brand + '.png'
}
$arguments = @('/nologo','/target:winexe',('/out:' + (Join-Path $launcherRoot 'G-Works.exe')),('/win32icon:' + (Join-Path $launcherRoot 'g-works.ico'))) + $resources
foreach ($library in @('System.Windows.Forms','System.Drawing','System.Web.Extensions','System.Numerics')) { $arguments += '/reference:' + $library + '.dll' }
foreach ($source in @('Hub.cs','HubArt.cs','ReleaseUpdates.cs')) { $arguments += Join-Path $launcherRoot $source }
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
'''
README = '''# G-Works

G-Works is a local desktop suite for Rutgers Mathematics instructors.

| App | Purpose | Chrome companion |
| --- | --- | --- |
| G-Whiz | Course materials, questions and handouts | G-View |
| G-Scope | Scans, rubrics and grading | G-Rater |
| G-Vault | Course grades, recommendations and integrity records | G-Report |

This is the reviewed program-source snapshot for release **{version}**.
`SOURCE_MANIFEST.json` records the origin and SHA-256 of every exported file.
Installable releases supply the required Python, desktop and PDF runtimes and
optional course packages. Those dependencies, third-party vendor files, course
content, compiled binaries and user records are excluded from this source tree.

G-Scope currently requires G-Whiz. G-Vault starts with empty libraries and lets
each instructor configure their profile and course databases. The Rutgers
Mathematics framework and institutional letterhead remain available.

The shared application source is in `Shared/TeachingApp/2.0.0`; app entries and
Vault module sources use their release-package layouts under `Apps`.
Build the Windows launcher with `Maintenance/Installer/Hub/build.ps1`.
This source snapshot is not a complete offline installer build environment:
release assembly and signing require the matching runtime packages and signing
configuration. No signing secrets or installed user configuration are included.

To create a new snapshot from a reviewed local release, run:

```powershell
python Maintenance/Installer/export_sources.py --release <release-folder> --destination <new-snapshot-folder>
```

The exporter only reads approved public package inputs and explicitly named
launcher sources. It refuses existing output directories and does not push Git.
'''
GITIGNORE = '''__pycache__/
*.py[cod]
*.exe
*.dll
*.pyd
*.sqlite*
*.db
*.pem
*.pfx
*.key
**/Data/
**/Dependencies/
**/.gworks/
**/Output/
**/Outputs/
**/Temp/
**/Backups/
**/Audit/
node_modules/
Releases/
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    entries, receipt = build_snapshot(args.release, Path(__file__).resolve().parent)
    output = write_snapshot(args.destination, entries)
    print(json.dumps({'destination': str(output), 'release': receipt['release'], 'files': len(entries), 'bytes': sum(map(len, entries.values())), 'manifest_sha256': sha(entries['SOURCE_MANIFEST.json'])}))


if __name__ == '__main__':
    main()
