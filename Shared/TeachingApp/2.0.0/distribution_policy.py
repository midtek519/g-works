"""Release-only file policy. Authoring tools stay in the personal installation."""
from pathlib import Path
import json, os, shutil

APP_DEVELOPMENT_DIRS={'Editor','Tests','launchers','node_modules','__pycache__','.git'}
APP_DEVELOPMENT_FILES={'package_beta.py','package_layout.py','sync_instructor.py','distribution_policy.py','private_modules.py','private_module_embed.py'}

def omission_reason(relative):
    rel=Path(relative);parts=rel.parts
    if not parts:return None
    if rel.name in {'.DS_Store','Thumbs.db','desktop.ini'}:return 'Operating-system housekeeping'
    if rel.name in {'.gitignore','.gitattributes','.gitmodules','.gitkeep'} or '.git' in parts:return 'Git housekeeping'
    if parts[0]=='App':
        if any(p in APP_DEVELOPMENT_DIRS for p in parts[1:-1]):return 'Application development/build source'
        if len(parts)==2 and rel.name in APP_DEVELOPMENT_FILES:return 'Author-only release/update tooling'
        if rel.suffix in {'.pyc','.pyo'}:return 'Generated Python bytecode'
    if parts[0]=='mh-git':
        if rel.suffix.lower()=='.md':return 'Repository and authoring notes; not a compilation input'
        if rel.suffix.lower() in {'.aux','.log','.fls','.fdb_latexmk','.toc','.bak','.tmp'}:return 'Compilation or editor intermediate'
    return None

def prune_folder(folder, backup=None):
    base=Path(folder).resolve()
    profile=base/'Data/edition.json'
    if not profile.is_file():profile=base/'edition.json'
    if not profile.is_file() or json.loads(profile.read_text('utf-8-sig')).get('edition') not in {'math135-instructor','full-beta'}:
        raise ValueError('Cleanup requires a generated G-Whiz distribution, never the authoring folder.')
    if Path(folder).is_symlink() or Path(folder).is_junction():raise ValueError('Distribution must be a physical directory.')
    removed=[]
    for current,dirs,files in os.walk(base):
        dirs[:]=[d for d in dirs if not (Path(current)/d).is_symlink() and not (Path(current)/d).is_junction()]
        for name in files:
            path=Path(current)/name;rel=path.relative_to(base);reason=omission_reason(rel)
            if not reason:continue
            if not path.resolve().is_relative_to(base):raise ValueError('Cleanup path escaped distribution.')
            if backup:
                copy=Path(backup)/rel;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,copy)
            removed.append({'file':rel.as_posix(),'bytes':path.stat().st_size,'reason':reason})
            path.unlink()
    # Remove empty developer/source wrappers, keeping runtime and saved-work folders.
    app=base/'App'
    for name in APP_DEVELOPMENT_DIRS:
        directory=app/name
        if directory.is_dir():
            for p in sorted(directory.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if p.is_dir() and not p.is_symlink() and not p.is_junction():p.rmdir()
            directory.rmdir()
    return removed
