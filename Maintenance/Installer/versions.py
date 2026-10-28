"""Semantic Versioning precedence; release structure is governed by epochs."""
import re
PATTERN = '(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?(?:\\+([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?'

def key(value):
    m = re.fullmatch(PATTERN, value) if isinstance(value, str) else None
    if not m:
        raise ValueError('Invalid semantic release version.')
    pre = m[4]
    parts = []
    for part in pre.split('.') if pre else []:
        if part.isdigit():
            if len(part) > 1 and part.startswith('0'):
                raise ValueError('Invalid numeric prerelease identifier.')
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return (*map(int, m.group(1, 2, 3)), 0 if pre else 1, tuple(parts))

def is_prerelease(value):
    return key(value)[3] == 0

def epoch(value):
    key(value)
    m = re.fullmatch(PATTERN, value)
    pre = m[4]
    if not pre:
        return 'stable-' + m[1]
    parts = pre.split('.')
    return parts[0].lower() + '-' + parts[1] if len(parts) > 1 and parts[1].isdigit() else 'prerelease-' + '.'.join(m.group(1, 2, 3))

def display(value):
    key(value)
    m = re.fullmatch(PATTERN, value)
    return 'Beta ' + m[4][5:] if m[4] and m[4].startswith('beta.') else 'Version ' + value

def windows(value):
    values = key(value)[:3]
    m = re.fullmatch(PATTERN, value)
    tail = 0
    if m[4] and m[4].startswith('beta.') and m[4].split('.')[1].isdigit():
        tail = int(m[4].split('.')[1])
    if any((n > 65535 for n in (*values, tail))):
        raise ValueError('Version exceeds Windows file-version limits.')
    return '.'.join(map(str, (*values, tail)))

def chrome(value):
    """Numeric Chrome update version; version_name carries the exact SemVer."""
    values = key(value)[:3]
    pre = re.fullmatch(PATTERN, value)[4]
    serial = 65535
    if pre:
        match = re.fullmatch('(alpha|beta|rc)\\.(\\d+)(?:\\.(\\d+))?', pre)
        if not match:
            raise ValueError('Chrome builds require alpha.N, beta.N or rc.N with an optional patch number.')
        number, patch = (int(match[2]), int(match[3] or 0))
        if number >= 200 or patch >= 100:
            raise ValueError('Chrome prerelease counters exceed their numeric slots.')
        serial = {'alpha': 0, 'beta': 20000, 'rc': 40000}[match[1]] + number * 100 + patch
    if any((n > 65535 for n in (*values, serial))) or not any((*values, serial)):
        raise ValueError('Version exceeds Chrome manifest limits.')
    return '.'.join(map(str, (*values, serial)))
