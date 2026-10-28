"""Self-contained local checks; original exports are not required."""
from pathlib import Path
import sqlite3,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from backup_archive import available_snapshot
ROOT=Path(__file__).resolve().parent.parent
DB=ROOT/'Math_135_Central.sqlite'
d=sqlite3.connect('file:'+DB.as_posix()+'?mode=ro',uri=True)
def count(sql):return d.execute(sql).fetchone()[0]
checks={'integrity_ok':d.execute('PRAGMA integrity_check').fetchone()[0]=='ok','foreign_key_errors':len(d.execute('PRAGMA foreign_key_check').fetchall()),'enrollments':count('SELECT COUNT(*) FROM enrollments'),'raw_scores':count('SELECT COUNT(*) FROM raw_scores'),'selected_numeric_scores':count('SELECT COUNT(*) FROM assessment_scores WHERE percent IS NOT NULL'),'normalized_grade_errors':count("SELECT COUNT(*) FROM enrollments WHERE official_grade IN ('TF','TTZ')"),'withdrawn_average_errors':count("SELECT COUNT(*) FROM enrollments WHERE official_grade='W' AND (course_average IS NOT NULL OR calculated_course_average IS NOT NULL)"),'score_link_errors':count('''SELECT COUNT(*) FROM assessment_scores s JOIN json_each(s.selected_raw_ids) j JOIN raw_scores r ON r.raw_score_id=j.value JOIN canvas_observations c USING(canvas_row_id) JOIN input_columns i USING(input_id) WHERE c.ruid<>s.ruid OR c.semester<>s.semester OR i.assessment_id<>s.assessment_id'''),'grade_distribution_count_difference':count('SELECT (SELECT COUNT(official_grade) FROM enrollments)-(SELECT SUM(students) FROM grade_distributions)'),'managed_undo_files_missing':sum(not available_snapshot(r[0]).exists()for r in d.execute("SELECT backup_path FROM app_imports WHERE status='committed'"))}
d.close()
print(json.dumps(checks))
if not checks['integrity_ok']or any(checks[k]for k in ['foreign_key_errors','normalized_grade_errors','withdrawn_average_errors','score_link_errors','grade_distribution_count_difference','managed_undo_files_missing']):raise SystemExit(1)
