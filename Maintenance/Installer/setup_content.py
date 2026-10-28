"""Installer validation for course workspaces and local instructor profiles."""
import re

def course(value):
    if not isinstance(value, dict):
        raise ValueError('Enter a course number and optional name.')
    code = str(value.get('code', '')).strip()
    name = str(value.get('name', '')).strip()
    if not re.fullmatch('\\d{3}', code) or code == '136':
        raise ValueError('Enter an active three-digit Rutgers Math course number (136 is discontinued).')
    if len(name) > 100 or any((ord(c) < 32 for c in name)):
        raise ValueError('Check the course name.')
    return {'code': code, 'name': name or 'Math ' + code}

def profile(value):
    if not isinstance(value, dict):
        raise ValueError('Enter your instructor details.')
    result = {'schema': 1, 'institution': 'Rutgers University', 'department': 'Department of Mathematics'}
    for key in ('name', 'title', 'email', 'phone', 'office', 'website'):
        item = value.get(key, '')
        if not isinstance(item, str) or len(item) > 300 or any((ord(c) < 32 for c in item)):
            raise ValueError('Check your ' + key + '.')
        result[key] = item.strip()
    if not result['name']:
        raise ValueError('Enter your name.')
    return result
