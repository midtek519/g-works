"""Suite release boundaries. Private repository access never permits bundling records."""
from pathlib import Path
import json
SUITES = {'professional': {'name': 'G-Works', 'repository': 'midtek519/g-works', 'visibility': 'public', 'apps': ('whiz', 'scope', 'spot')}}
APPS = [{'id': 'whiz', 'name': 'G-Whiz', 'suite': 'professional', 'visibility': 'public', 'description': 'Teaching materials for every course'}, {'id': 'scope', 'name': 'G-Scope', 'suite': 'professional', 'visibility': 'public', 'description': 'Grading with G-Whiz handouts'}, {'id': 'spot', 'name': 'G-Vault', 'suite': 'professional', 'visibility': 'public', 'description': 'Course grades, recommendations and integrity'}]

def validate(value, inventory=False):
    if value.get('distribution_policy') != 2:
        raise ValueError('A new release must use the separate public G-Works and private collection distribution policy.')
    suite = value.get('suite')
    if inventory and suite == 'local-inventory' and (value.get('channel') == 'owner'):
        return
    if suite not in SUITES:
        raise ValueError('Unknown release suite.')
    policy = SUITES[suite]
    expected = {a['id']: a for a in APPS if a['suite'] == suite}
    if value.get('suite_layout') != 1 or value.get('repository') != policy['repository'] or value.get('channel') != policy['visibility']:
        raise ValueError('Release repository, visibility or suite routing is inconsistent.')
    apps = value.get('applications', [])
    if len(apps) != len(expected) or {a.get('id') for a in apps} != set(expected):
        raise ValueError('The release must contain exactly its suite application definitions.')
    for app in apps:
        if any((app.get(key) != expected[app['id']][key] for key in ('name', 'suite', 'visibility'))):
            raise ValueError('Application visibility or suite routing is inconsistent.')
    if value.get('activation_service'):
        raise ValueError('The new suite releases do not use an activation service.')
    if suite == 'personal' and (value.get('catalogue_url') or value.get('access') != 'repository'):
        raise ValueError('Private suite updates require authenticated repository access.')
    if any((p.get('app') and p['app'] not in expected for p in value.get('packages', []))):
        raise ValueError("A release includes another suite's package.")
    if any((p.get('suite', suite) != suite for p in value.get('packages', []))):
        raise ValueError('A runtime package belongs to another suite.')
    if suite == 'personal' and any(('://' in p.get('source', '') and p.get('kind') != 'tool-installer' for p in value.get('packages', []))):
        raise ValueError('Private application and runtime packages must be downloaded with the complete repository bundle.')

def selected_packages(packages, apps):
    index = {p['id']: p for p in packages}
    if len(index) != len(packages):
        raise ValueError('Release package IDs must be unique.')
    needed = {p['id']: p for p in packages if p.get('app') in apps}
    pending = list(needed.values())
    while pending:
        for ident in pending.pop().get('requires', []):
            if ident not in index:
                raise ValueError('Release dependency is missing: ' + ident)
            if ident not in needed:
                needed[ident] = index[ident]
                pending.append(index[ident])
    if any((p.get('app') and p['app'] not in apps for p in needed.values())):
        raise ValueError('An application dependency crosses suite boundaries.')
    return sorted(needed.values(), key=lambda p: p['id'])

def catalogues(version, packages, courses):
    result = {}
    for suite, policy in SUITES.items():
        value = {'schema': 1, 'suite_layout': 1, 'distribution_policy': 2, 'suite': suite, 'channel': policy['visibility'], 'repository': policy['repository'], 'release': version, 'applications': [dict(a) for a in APPS if a['suite'] == suite], 'courses': courses if suite == 'professional' else [], 'activation_service': '', 'catalogue_url': 'https://github.com/' + policy['repository'] + '/releases/latest/download/public-catalogue-envelope.json' if suite == 'professional' else '', 'access': 'public' if suite == 'professional' else 'repository', 'packages': selected_packages(packages, set(policy['apps']))}
        validate(value)
        result[policy['visibility']] = value
    result['owner'] = {'schema': 1, 'suite_layout': 1, 'distribution_policy': 2, 'suite': 'local-inventory', 'channel': 'owner', 'release': version, 'applications': APPS, 'packages': packages, 'courses': courses}
    return result

def verify_local_policy():
    path = Path(__file__).resolve().parent.parent / 'Distribution/suites.json'
    value = json.loads(path.read_text('utf-8'))
    if value.get('schema') != 2 or value.get('package_local_records') is not False:
        raise ValueError('Invalid local distribution policy.')
    for suite, expected in SUITES.items():
        actual = value.get(suite, {})
        if any((actual.get(k) != expected[k] for k in ('name', 'repository', 'visibility'))) or tuple(actual.get('apps', [])) != expected['apps'] or actual.get('activation_required') is not False:
            raise ValueError('Local distribution policy differs from the installer.')
    return value
