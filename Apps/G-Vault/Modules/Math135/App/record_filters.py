"""Parameterized include/exclude logic shared by roster, reports and CSV exports."""
import json

FIELDS=('semester','lecturer','recitation','unit','class','curric')
MODES=('and','or','xor')

def _one(value,default=''):
    return (value[-1] if value else default) if isinstance(value,(list,tuple)) else value

def _values(value):
    if value in (None,''):return []
    rows=value if isinstance(value,(list,tuple)) else [value]
    if len(rows)>500:raise ValueError('Choose up to 500 values in a filter.')
    if any(not isinstance(v,(str,int)) or len(str(v))>250 for v in rows):raise ValueError('Check the filter values.')
    return list(dict.fromkeys(str(v) for v in rows))

def rules_from_params(params):
    raw=_one(params.get('filter_rules'))
    rules={}
    if raw:
        if not isinstance(raw,str) or len(raw)>48000:raise ValueError('The filters are too large.')
        try:rules=json.loads(raw)
        except (TypeError,ValueError):raise ValueError('The filter choices could not be read.') from None
        if not isinstance(rules,dict) or rules.get('version')!=1:raise ValueError('Reopen the filters and apply your choices again.')
    combine=rules.get('join','and');groups=rules.get('groups',{})
    if combine not in ('and','or','custom') or not isinstance(groups,dict) or set(groups)-set(FIELDS):raise ValueError('Choose valid filter logic.')
    out={}
    for field in FIELDS:
        # Legacy semester parameters remain an independent scope in the callers.
        value=groups.get(field,{} if field=='semester' else {'yes':_values(params.get(field))})
        if not isinstance(value,dict):raise ValueError('Check the filter group.')
        yes=_values(value.get('yes'));no=_values(value.get('no'))
        yes_mode=value.get('yes_mode','or');no_mode=value.get('no_mode','or');assignment=value.get('combine','and')
        if yes_mode not in MODES or no_mode not in MODES or assignment not in ('and','or') or set(yes)&set(no):raise ValueError('Check the Yes/No filter logic.')
        if field=='semester' and (yes_mode!='or' or no_mode!='or'):raise ValueError('Semester choices match any selected term.')
        if yes or no:out[field]={'yes':yes,'no':no,'yes_mode':yes_mode,'no_mode':no_mode,'combine':assignment}
    return combine,out

def _predicate(field,value,alias,roster):
    if field not in ('lecturer','recitation'):
        return 'COALESCE(CAST('+alias+'."'+field+'" AS TEXT),\'\')=?',[value]
    base='t.semester='+alias+'.semester AND t.section='+roster+'.section AND t.role=?'
    if value=='__unmapped__':return 'NOT EXISTS(SELECT 1 FROM app_teaching_assignments t WHERE '+base+')',[field]
    return 'EXISTS(SELECT 1 FROM app_teaching_assignments t WHERE '+base+' AND t.instructor_id=?)',[field,value]

def _combine(parts,mode):
    if len(parts)==1:return '('+parts[0]+')'
    if mode=='xor':return '(('+' + '.join('(CASE WHEN '+p+' THEN 1 ELSE 0 END)' for p in parts)+')=1)'
    return '('+(' AND ' if mode=='and' else ' OR ').join('('+p+')' for p in parts)+')'

def group_clause(params,alias='e',roster='rs'):
    """Semester always scopes the other groups, including OR and custom logic."""
    join,groups=rules_from_params(params);compiled=[];scope=None
    for field,group in groups.items():
        halves=[];args=[]
        for polarity in ('yes','no'):
            parts=[]
            for value in group[polarity]:
                sql,values=_predicate(field,value,alias,roster);parts.append(sql);args.extend(values)
            if parts:
                sql=_combine(parts,group[polarity+'_mode'])
                halves.append(('NOT '+sql) if polarity=='no' else sql)
        row=('('+' AND '.join(halves)+')',args,group['combine'])
        if field=='semester':scope=row
        else:compiled.append(row)
    if not compiled:return (scope[0],scope[1]) if scope else ('',[])
    if join!='custom':
        sql=_combine([sql for sql,_,_ in compiled],join);args=[value for _,args,_ in compiled for value in args]
        return ('('+scope[0]+' AND '+sql+')',scope[1]+args) if scope else (sql,args)
    # Every AND group must match, plus at least one active OR group when present.
    and_groups=[row for row in compiled if row[2]=='and'];or_groups=[row for row in compiled if row[2]=='or']
    pieces=[sql for sql,_,_ in and_groups];args=[value for _,values,_ in and_groups for value in values]
    if or_groups:
        pieces.append(_combine([sql for sql,_,_ in or_groups],'or'));args.extend(value for _,values,_ in or_groups for value in values)
    sql=_combine(pieces,'and')
    return ('('+scope[0]+' AND '+sql+')',scope[1]+args) if scope else (sql,args)
