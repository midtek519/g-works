"""One launcher per platform; supporting files stay inside the app."""
from pathlib import Path
import filecmp, shutil

def instructor_folder(root):
    root=Path(root).resolve()
    return root.with_name('G-Whiz') if root.name.casefold() in ('g-vault','g-keeper') else root/'G-Whiz-Instructor-Version'

def profile_path(folder):
    folder=Path(folder)
    current=folder/'Data/edition.json'
    return current if current.is_file() else folder/'edition.json'

def prepare_layout(root, destination, desktop_runtime=True):
    root=Path(root).resolve();destination=Path(destination).resolve()
    legacy=destination/'edition.json';profile=destination/'Data/edition.json'
    if legacy.is_file():
        profile.parent.mkdir(parents=True,exist_ok=True)
        if profile.exists():
            assert legacy.read_bytes()==profile.read_bytes()
            legacy.unlink()
        else:legacy.rename(profile)
    for name in ('Open G-Whiz.cmd',):
        source=root/'App/launchers'/name
        shutil.copy2(source,destination/name)
        if name.endswith('.command'):
            (destination/name).write_bytes((destination/name).read_bytes().replace(b'\r\n',b'\n'))
            (destination/name).chmod(0o755)
    instructions=root/'Maintenance/Instructor Updates/Templates/START HERE.txt'
    if not instructions.is_file():instructions=root/'Instructor Instructions.txt'
    shutil.copy2(instructions,destination/'START HERE.txt')
    if desktop_runtime:
        # A portable Windows release carries its small desktop runtime. Profiles
        # belong to the installed user's Data and are never copied from here.
        runtime=root/'Dependencies/DesktopRuntime'
        if not (runtime/'webview/__init__.py').is_file():
            raise ValueError('The Windows desktop runtime is missing from Dependencies/DesktopRuntime.')
        def copy_runtime(source,target):
            # Fresh package staging may already have hard-linked these files.
            if Path(target).exists() and (Path(source).samefile(target) or filecmp.cmp(source,target,shallow=False)):return target
            return shutil.copy2(source,target)
        shutil.copytree(runtime,destination/'Dependencies/DesktopRuntime',dirs_exist_ok=True,
                        copy_function=copy_runtime,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
    # Known old entry points only; course resources and saved work are untouched.
    for name in ('Install on Windows.cmd','Install on Mac.command','Open on Windows.cmd','Open on Mac.command','Install G-Whiz.ps1','Read Me.txt','TESTING.txt','THIRD-PARTY-NOTICES.txt','G-Whiz (Instructor Version).lnk','G-Whiz on Windows.cmd','G-Whiz on Mac.command'):
        p=destination/name
        if p.is_file():p.unlink()
