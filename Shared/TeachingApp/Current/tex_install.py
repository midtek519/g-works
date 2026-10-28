"""Install official TeX Live into G-Whiz when no usable installation exists."""
from pathlib import Path, PurePosixPath
import argparse
import json
import os
import secrets
import stat
import subprocess
import sys
import urllib.request
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))

INSTALLER_URL = 'https://mirror.ctan.org/systems/texlive/tlnet/install-tl.zip'


def install_plan(root, destination=None, variant="full"):
    root = Path(root).resolve()
    target = Path(destination).expanduser().resolve() if destination else root / 'Dependencies/texlive'
    if not str(target).isascii():
        raise ValueError('TeX Live requires an installation folder without accented or other non-ASCII characters. Choose one with -TeXInstallDir, for example C:\\G-Whiz-TeX.')
    if any(char in str(target) for char in '\r\n') or target == Path(target.anchor):
        raise ValueError('Choose a TeX Live folder inside a drive, not the drive itself.')
    if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
        raise ValueError('Choose a normal TeX Live folder, not a link.')
    if variant not in {'full','essentials'}:raise ValueError('Choose essentials or full.')
    if variant=='essentials':
        from instructor_tex import enabled
        if not enabled(root):raise ValueError('G-Whiz Essentials is available only in the teaching distribution.')
    return {'url': INSTALLER_URL, 'destination': str(target), 'scheme': 'scheme-basic' if variant=='essentials' else 'scheme-full', 'variant': variant}


def extract_installer(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 15000 or sum(item.file_size for item in entries) > 512 * 1024 * 1024:
            raise ValueError('The downloaded installer archive is unexpectedly large.')
        for item in entries:
            parts = PurePosixPath(item.filename.replace('\\', '/'))
            if parts.is_absolute() or '..' in parts.parts or any(':' in part for part in parts.parts):
                raise ValueError('The installer archive contains an unsafe path.')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('The installer archive contains an unexpected link.')
        bad = package.testzip()
        if bad:
            raise ValueError('The installer download is damaged: ' + bad)
        package.extractall(destination)
    scripts = list(destination.glob('install-tl-*/install-tl'))
    if len(scripts) != 1:
        raise ValueError('The official TeX Live installer was not found in the download.')
    folder = scripts[0].parent
    if not (folder / 'tlpkg/tlperl/bin/perl.exe').is_file():
        raise ValueError('The downloaded installer does not contain its Windows runtime.')
    return folder


def profile_text(target, variant="full"):
    base = Path(target).resolve().as_posix()
    # Keep all TeX files with this installation. No PATH, file associations, or
    # desktop integration is changed; G-Whiz invokes the selected tools directly.
    values = {
        'selected_scheme': 'scheme-basic' if variant=='essentials' else 'scheme-full', 'binary_windows': '1',
        'TEXDIR': base, 'TEXMFLOCAL': base + '/texmf-local',
        'TEXMFSYSCONFIG': base + '/texmf-config', 'TEXMFSYSVAR': base + '/texmf-var',
        'TEXMFCONFIG': base + '/user-config', 'TEXMFVAR': base + '/user-var',
        'TEXMFHOME': base + '/texmf-home',
        'instopt_adjustpath': '0', 'instopt_adjustrepo': '1', 'instopt_letter': '1',
        'tlpdbopt_install_docfiles': '0', 'tlpdbopt_install_srcfiles': '0',
        'tlpdbopt_desktop_integration': '0', 'tlpdbopt_file_assocs': '0',
        'tlpdbopt_w32_multi_user': '0', 'tlpdbopt_create_formats': '1',
    }
    return '\n'.join(key + ' ' + value for key, value in values.items()) + '\n'


def prepare(root, destination=None, variant="full"):
    plan = install_plan(root, destination, variant)
    target = Path(plan['destination'])
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('The TeX Live destination is not empty. Existing files were kept. Use -TeXBin for an existing installation, or -TeXInstallDir to choose an empty folder.')
    work = Path(root).resolve() / 'Temp/Installers' / ('texlive-' + secrets.token_hex(6))
    work.mkdir(parents=True)
    archive = work / 'install-tl.zip'
    print('Downloading the official TeX Live installer over HTTPS...', flush=True)
    request = urllib.request.Request(INSTALLER_URL, headers={'User-Agent': 'G-Whiz-Setup/1.0'})
    with urllib.request.urlopen(request, timeout=90) as response, archive.open('wb') as output:
        if not response.geturl().lower().startswith('https://'):
            raise ValueError('The installer mirror did not use HTTPS. Please rerun setup.')
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > 100 * 1024 * 1024:
                raise ValueError('The installer download is unexpectedly large.')
            output.write(chunk)
    installer = extract_installer(archive, work / 'unpacked')
    profile = work / 'g-whiz.profile'
    profile.write_text(profile_text(target, variant), encoding='ascii')
    return plan, installer, profile


def run_install(root, destination=None, prepare_only=False, variant="full"):
    plan, installer, profile = prepare(root, destination, variant)
    if prepare_only:
        return {**plan, 'installer': str(installer), 'profile': str(profile), 'prepared_only': True}
    if os.name != 'nt':
        raise ValueError('Use the Mac setup command on macOS.')
    perl = installer / 'tlpkg/tlperl/bin/perl.exe'
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('PERL')}
    env['PERL5LIB'] = str(installer / 'tlpkg/tlperl/lib')
    env['PATH'] = str(perl.parent) + os.pathsep + env.get('PATH', '')
    env['TEXLIVE_PREFER_OWN'] = '1'
    print('Installing TeX Live in ' + plan['destination'], flush=True)
    print('This first-time download can take a long time. Keep this window open.', flush=True)
    result = subprocess.run([str(perl), str(installer / 'install-tl'), '-no-gui', '-profile', str(profile)], cwd=installer, env=env)
    if result.returncode:
        raise ValueError('TeX Live setup did not finish. Download/install logs are in ' + str(profile.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tex_setup
    folder = Path(plan['destination']) / 'bin/windows'
    if variant=='essentials':
        from instructor_tex import requirements
        manager=Path(plan['destination'])/'texmf-dist/scripts/texlive/tlmgr.pl'
        result=subprocess.run([str(Path(plan['destination'])/'tlpkg/tlperl/bin/perl.exe'),str(manager),'install',*requirements()['texlive_packages']],env=env)
        if result.returncode:raise ValueError('Required package installation did not finish. Rerun setup and choose the existing installation to repair it.')
    if not tex_setup.usable(folder):
        raise ValueError('TeX Live finished but a required compiler or package is missing. See ' + str(profile.parent))
    settings = Path(root).resolve() / 'Data/settings.json'
    data = json.loads(settings.read_text(encoding='utf-8-sig')) if settings.is_file() else {}
    root = Path(root).resolve()
    data['texlive_bin'] = folder.relative_to(root).as_posix() if folder.is_relative_to(root) else str(folder)
    from instructor_tex import enabled
    if enabled(root):
        data['tex_bin']=data['texlive_bin']
        data['tex_distribution']='texlive'
        data.pop('tex_setup',None)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'destination': plan['destination'], 'installed': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--variant',choices=['essentials','full'],default='full')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    try:
        result = install_plan(args.root, args.destination,args.variant) if args.plan else run_install(args.root, args.destination,args.prepare_only,args.variant)
        print(json.dumps(result, indent=2))
    except Exception as error:
        print('G-Whiz TeX Live setup: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
