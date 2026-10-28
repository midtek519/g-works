"""Build counted filter choices from saved enrollments, never from lookup keys."""
import re
from collections import defaultdict

def build_filter_options(connection, lookups):
    filters = {}
    by_semester = defaultdict(dict)
    for key in ('unit', 'class', 'curric', 'section'):
        field = 'rs.section' if key == 'section' else 'e."' + key + '"'
        rows = connection.execute(
            'SELECT e.semester, ' + field + ', COUNT(*) FROM enrollments e '
            'LEFT JOIN app_roster_state rs USING(ruid,semester) '
            'WHERE ' + field + ' IS NOT NULL AND TRIM(' + field + ")<>'' "
            'GROUP BY e.semester, ' + field
        ).fetchall()
        totals = defaultdict(int)
        terms = defaultdict(dict)
        for term, value, count in rows:
            value = str(value)
            totals[value] += count
            terms[term][value] = count

        def option(value, count):
            full = lookups.get(key, {}).get(value)
            short = lookups.get(key + '_short', {}).get(value, full)
            label = value + ' — ' + short if short else value
            if key == 'class':
                label = '20' + value if re.fullmatch(r'\d{2}', value) and 10 <= int(value) <= 60 else value
            return {'value': value, 'label': label, 'count': count,
                    'full_label': value + ' — ' + full if full else label}

        filters[key] = [option(value, totals[value]) for value in sorted(totals)]
        for term, values in terms.items():
            by_semester[term][key] = [option(value, values[value]) for value in sorted(values)]
    return filters, dict(by_semester)
