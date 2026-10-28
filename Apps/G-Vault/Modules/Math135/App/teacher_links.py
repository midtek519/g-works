"""Local semester/section links to public teaching assignments."""
from pathlib import Path
from collections import defaultdict
import hashlib,json

SCHEMA='''
CREATE TABLE IF NOT EXISTS app_teacher_people(instructor_id TEXT PRIMARY KEY,name TEXT NOT NULL,profile_url TEXT);
CREATE TABLE IF NOT EXISTS app_teaching_assignments(semester TEXT NOT NULL,section TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('lecturer','recitation')),instructor_id TEXT NOT NULL REFERENCES app_teacher_people(instructor_id),raw_name TEXT NOT NULL,source_url TEXT,source_section TEXT,source_kind TEXT NOT NULL DEFAULT 'schedule',email TEXT,PRIMARY KEY(semester,section,role,instructor_id));
CREATE INDEX IF NOT EXISTS app_teaching_lookup ON app_teaching_assignments(semester,section,role,instructor_id);
CREATE TABLE IF NOT EXISTS app_teaching_sources(semester TEXT PRIMARY KEY,url TEXT NOT NULL,sha256 TEXT NOT NULL,fetched TEXT NOT NULL,issues TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_teaching_overrides(semester TEXT NOT NULL,section TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(semester,section,role));
CREATE TABLE IF NOT EXISTS app_section_observations(observation_id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES sources(source_id),source_row INTEGER NOT NULL,kind TEXT NOT NULL,semester TEXT NOT NULL,ruid TEXT,netid TEXT,section TEXT NOT NULL,UNIQUE(source_id,source_row,kind));
'''

def ensure_teaching(d, mapping_file):
    d.executescript(SCHEMA)
    p=Path(mapping_file)
    if not p.exists():return
    data=p.read_bytes();checksum=hashlib.sha256(data).hexdigest()
    previous=d.execute("SELECT value FROM app_settings WHERE key='teaching_schedule_seed'").fetchone()
    if previous and previous[0]==checksum:return
    for schedule in json.loads(data.decode('utf8')):
        term=schedule['semester']
        d.execute('INSERT OR REPLACE INTO app_teaching_sources VALUES(?,?,?,?,?)',(term,schedule['url'],schedule['sha256'],schedule['fetched'],json.dumps(schedule['issues'])))
        # Refresh only public assignments. Explicit local corrections survive.
        overridden={(r[0],r[1])for r in d.execute("SELECT section,role FROM app_teaching_overrides WHERE semester=?",(term,))}
        d.execute("DELETE FROM app_teaching_assignments WHERE semester=? AND source_kind='schedule'",(term,))
        for r in schedule['assignments']:
            d.execute('INSERT INTO app_teacher_people VALUES(?,?,?) ON CONFLICT(instructor_id) DO UPDATE SET name=excluded.name,profile_url=excluded.profile_url',(r['instructor_id'],r['name'],r['profile_url']))
            if(r['section'],r['role'])in overridden:continue
            d.execute('INSERT OR IGNORE INTO app_teaching_assignments VALUES(?,?,?,?,?,?,?,?,?)',(term,r['section'],r['role'],r['instructor_id'],r['name'],r['source_url'],r['source_section'],'schedule',None))
    d.execute("INSERT OR REPLACE INTO app_settings VALUES('teaching_schedule_seed',?)",(checksum,))
    d.commit()

def filter_clauses(params, alias='e', roster='rs'):
    clauses=[];args=[]
    for role in ('lecturer','recitation'):
        selected=params.get(role,[])
        selected=selected if isinstance(selected,(list,tuple))else[selected]if selected else[]
        if not selected:continue
        base=f't.semester={alias}.semester AND t.section={roster}.section AND t.role=?'
        ids=[v for v in selected if v!='__unmapped__']
        parts=[];role_args=[]
        if ids:
            parts.append('EXISTS(SELECT 1 FROM app_teaching_assignments t WHERE '+base+' AND t.instructor_id IN ('+','.join('?'for _ in ids)+'))')
            role_args.extend([role,*ids])
        if '__unmapped__'in selected:
            parts.append('NOT EXISTS(SELECT 1 FROM app_teaching_assignments t WHERE '+base+')');role_args.append(role)
        clauses.append('('+' OR '.join(parts)+')');args.extend(role_args)
    return clauses,args

def filter_options(d):
    filters={};by_term=defaultdict(dict)
    for role in ('lecturer','recitation'):
        rows=d.execute('''SELECT e.semester,p.instructor_id,p.name,COUNT(DISTINCT e.ruid)
            FROM enrollments e LEFT JOIN app_roster_state rs USING(ruid,semester)
            JOIN app_teaching_assignments t ON t.semester=e.semester AND t.section=rs.section
            JOIN app_teacher_people p USING(instructor_id) WHERE t.role=?
            GROUP BY e.semester,p.instructor_id,p.name''',(role,)).fetchall()
        missing=d.execute('''SELECT e.semester,COUNT(*) FROM enrollments e
            LEFT JOIN app_roster_state rs USING(ruid,semester)
            WHERE NOT EXISTS(SELECT 1 FROM app_teaching_assignments t WHERE t.semester=e.semester AND t.section=rs.section AND t.role=?)
            GROUP BY e.semester''',(role,)).fetchall()
        totals=defaultdict(int);names={};terms=defaultdict(list)
        for term,identity,name,count in rows:
            names[identity]=name;totals[identity]+=count
            terms[term].append({'value':identity,'label':name,'full_label':name,'count':count})
        for term,count in missing:
            if count:
                identity='__unmapped__';names[identity]='Unmapped / missing';totals[identity]+=count
                terms[term].append({'value':identity,'label':names[identity],'full_label':'No confirmed '+role+' mapping for this student-semester record','count':count})
        filters[role]=sorted([{'value':i,'label':names[i],'full_label':names[i],'count':count}for i,count in totals.items()],key=lambda x:(x['value']=='__unmapped__',x['label'].casefold()))
        for term,options in terms.items():by_term[term][role]=sorted(options,key=lambda x:(x['value']=='__unmapped__',x['label'].casefold()))
    return filters,dict(by_term)

def assignment_rows(d):
    return [dict(r)for r in d.execute('''SELECT t.*,p.name,p.profile_url FROM app_teaching_assignments t
        JOIN app_teacher_people p USING(instructor_id) ORDER BY t.semester,t.section,t.role,p.name''')]

def section_names(d,term,section):
    result={'lecturer':[],'recitation':[]}
    if not d.execute("SELECT 1 FROM sqlite_master WHERE name='app_teaching_assignments'").fetchone():return {role:''for role in result}
    for role,name in d.execute('''SELECT t.role,p.name FROM app_teaching_assignments t JOIN app_teacher_people p USING(instructor_id)
        WHERE t.semester=? AND t.section=? ORDER BY p.name''',(term,section or'')):result[role].append(name)
    return {role:'; '.join(names)for role,names in result.items()}

def apply_instructor_row(d,term,record):
    sec=record['section']
    if 'lecturer'in record or 'recitation'in record:
        for role in ('lecturer','recitation'):
            if role in record:save_assignment(d,term,sec,role,record[role],record.get(role+'_email',''))
        current=section_names(d,term,sec)
        name=current['lecturer']or current['recitation']or record.get('instructor','')
    else:
        # Old generic instructor files retain their original meaning; assigning
        # a lecturer/recitation role requires an explicitly labeled column.
        name=record.get('instructor','')
    d.execute('INSERT OR REPLACE INTO app_instructors VALUES(?,?,?,?)',(term,sec,name,record.get('lecturer_email')or record.get('email','')))

def save_assignment(d,term,section,role,names,email=''):
    if role not in ('lecturer','recitation'):raise ValueError('Unknown teaching role.')
    if isinstance(names,str):names=[s.strip()for s in names.split(';')if s.strip()]
    d.execute('INSERT OR IGNORE INTO app_teaching_overrides VALUES(?,?,?)',(term,section,role))
    d.execute('DELETE FROM app_teaching_assignments WHERE semester=? AND section=? AND role=?',(term,section,role))
    for name in names:
        matches=d.execute('SELECT instructor_id FROM app_teacher_people WHERE LOWER(name)=LOWER(?)',(name,)).fetchall()
        identity=matches[0][0]if len(matches)==1 else'manual:'+hashlib.sha256(name.casefold().encode('utf8')).hexdigest()[:24]
        d.execute('INSERT OR IGNORE INTO app_teacher_people VALUES(?,?,NULL)',(identity,name))
        d.execute('INSERT INTO app_teaching_assignments VALUES(?,?,?,?,?,?,?,?,?)',(term,section,role,identity,name,None,section,'manual',email))

def save_section_observation(d,record,term,source_id,kind):
    sec=record.get('section')or''
    if not sec:return
    d.execute('INSERT OR REPLACE INTO app_section_observations(source_id,source_row,kind,semester,ruid,netid,section) VALUES(?,?,?,?,?,?,?)',(source_id,record['source_row'],kind,term,record.get('ruid'),record.get('netid'),sec))
    if kind=='canvas'and record.get('ruid'):
        # REGIS remains authoritative. Canvas fills a missing section but never
        # reactivates a removed roster record or replaces a known REGIS section.
        d.execute('''INSERT INTO app_roster_state(ruid,semester,section,active) VALUES(?,?,?,1)
          ON CONFLICT(ruid,semester) DO UPDATE SET section=excluded.section WHERE app_roster_state.section='' ''',(record['ruid'],term,sec))
