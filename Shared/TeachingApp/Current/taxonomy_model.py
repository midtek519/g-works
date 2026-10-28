"""Course-specific classifications and topic-bound objectives."""
from copy import deepcopy
import re


def all_questions(cat):
    return cat.get('questions', []) + cat.get('archived_questions', []) + cat.get('merged_questions', []) + cat.get('trashed_questions', [])


def course_copy(q, code):
    """Select only this course's metadata; leave saved revisions untouched."""
    if q.get('archived') and q.get('archive_classification'):
        copy = deepcopy(q)
        entry = copy['archive_classification']
        copy['topics'] = [entry['topic']] if entry.get('topic') else []
        copy['objectives'] = entry.get('objectives', [])
        copy.pop('tex', None)
        return copy
    entry = q.get('classifications', {}).get(code)
    if entry is None:
        return q
    copy = deepcopy(q)
    copy['topics'] = [entry['topic']] if entry.get('topic') else []
    copy['objectives'] = entry.get('objectives', [])
    copy.pop('tex', None)
    return copy


def validate_classifications(cat, payload, suitability):
    topics = {t['id']: t for t in cat['topics'] if not t.get('retired')}
    objectives = {o['id']: o for o in cat['objectives'] if not o.get('retired')}
    values = payload.get('classifications')
    if values is None:
        values = {}
        for code in suitability:
            ids = [tid for tid in payload.get('topics', []) if code in topics.get(tid, {}).get('course_labels', {})]
            if len(ids) > 1:
                raise ValueError('Choose one primary topic for Math '+code+'.')
            tid = ids[0] if ids else ''
            values[code] = {'topic': tid, 'objectives': [oid for oid in payload.get('objectives', []) if tid in objectives.get(oid, {}).get('topic_ids', [])]}
    if not isinstance(values, dict):
        raise ValueError('Check the course classifications.')
    result = {}
    for code, entry in values.items():
        if code not in suitability:
            continue
        if not isinstance(entry, dict):
            raise ValueError('Choose a topic and its learning objectives.')
        tid = entry.get('topic', '')
        ids = entry.get('objectives', [])
        if not isinstance(ids, list) or len(ids) > 10 or any(not isinstance(oid, str) for oid in ids):
            raise ValueError('Choose valid learning objectives.')
        if tid and (tid not in topics or code not in topics[tid].get('course_labels', {})):
            raise ValueError('Choose a topic available for Math '+code+'.')
        if any(oid not in objectives or tid not in objectives[oid].get('topic_ids', []) for oid in ids):
            raise ValueError('Choose objectives belonging to the selected topic.')
        result[code] = {'topic': tid, 'objectives': list(dict.fromkeys(ids)), 'status': 'reviewed' if tid and ids else 'unassigned'}
    for code in suitability:
        result.setdefault(code, {'topic': '', 'objectives': [], 'status': 'unassigned'})
    return result


def set_classifications(q, values):
    q['classifications'] = values
    q['topics'] = list(dict.fromkeys(v['topic'] for v in values.values() if v.get('topic')))
    q['objectives'] = list(dict.fromkeys(oid for v in values.values() for oid in v.get('objectives', [])))


def header_title(label, fallback):
    # The full header is explicit; an empty section prevents a second prefix.
    return label.get('header_name') or label.get('title') or fallback


def fresh_question_id(cat):
    used = [int(q['id'][1:]) for q in all_questions(cat) if re.fullmatch(r'Q\d+', q['id'])]
    return 'Q'+str(max(max(used+[0])+1,int(cat.get('next_question_number',1)))).zfill(6)
