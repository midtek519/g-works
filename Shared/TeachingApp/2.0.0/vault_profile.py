"""Initialize empty private libraries from the owner's local instructor profile."""
from pathlib import Path
import json
from instructor_profile import read
from vault_workspaces import atomic_json


def initialize_library(root, module, app_root):
    root, app_root = Path(root), Path(app_root)
    tools = root / 'tools'
    tools.mkdir(parents=True, exist_ok=True)
    profile = read(app_root)
    sender = {'name': profile['name'], 'title': profile['title'],
              'department': 'Department of Mathematics, Rutgers University',
              'contact_lines': [profile[k] for k in ('email', 'phone', 'office', 'website') if profile.get(k)]}
    framework = app_root / 'Data/PrivateSource'
    runtime = app_root / 'Dependencies/texlive/bin/windows/pdflatex.exe'
    settings_path = tools / 'settings.json'
    settings = json.loads(settings_path.read_text('utf-8-sig')) if settings_path.exists() else {}
    if module == 'recommendations':
        settings.setdefault('grade_database', '')
        settings.setdefault('mh_git', str(framework))
        settings.setdefault('pdflatex', str(runtime))
        settings.setdefault('source_layout', 'consolidated')
        settings.setdefault('records_root', 'Records')
        profile_path = tools / 'author-profile.json'
        current = json.loads(profile_path.read_text('utf-8-sig')) if profile_path.exists() else {}
        # Never replace a configured author's letterhead or signature.
        if not current.get('sender', {}).get('name'):
            current.update(sender=sender)
            current.setdefault('signature_file', '')
            atomic_json(profile_path, current)
        for folder in ('Records', 'Letters', 'Needs Review'):
            (root / folder).mkdir(exist_ok=True)
    else:
        if not settings.get('sender', {}).get('name'):
            settings['sender'] = sender
        settings.setdefault('signature_file', '')
        settings.setdefault('renderer', str(framework / 'professional-correspondence/recommendations/render_letter.py'))
        settings.setdefault('pdflatex', str(runtime))
    if not settings_path.exists() or json.loads(settings_path.read_text('utf-8-sig')) != settings:
        atomic_json(settings_path, settings)
