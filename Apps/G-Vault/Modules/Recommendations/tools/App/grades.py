"""Read-only local grade lookup for recommendation drafting.

This module never imports the grades app's Store: constructing that Store performs
migrations. Each request instead opens SQLite with mode=ro and query_only enabled.
No student information is logged, sent over a network, or written by this module.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import math
import re
import sqlite3


class GradesUnavailableError(ValueError):
    """A display-safe failure that does not expose database data or paths."""


_UNAVAILABLE = "The local grades database is unavailable or has an unsupported format."
_REQUIRED = {
    "ruid", "semester", "name", "netid", "unit", "class", "curric",
    "official_grade", "course_average",
}
RANKING_NOTES = [
    "Ranks compare saved course averages among active student-semester records. "
    "Withdrawals and missing or nonnumeric averages are excluded.",
    "Equal averages share a competition rank: 1 plus the number strictly above. "
    "Percentile is 100 × (number below + half the number tied) / cohort size; "
    "higher percentiles indicate higher averages.",
    "An academic year includes Fall and the following Spring (for example, "
    "Fall 2025 and Spring 2026). Summer is excluded from academic-year comparisons.",
    "Academic-year and overall cohorts count course attempts, not unique students. "
    "Grading policies and assessments vary across semesters; these broader ranks "
    "are contextual comparisons rather than a common standardized measure.",
    "Attempts count active records with a saved letter grade, including W; "
    "pending and inactive records do not count.",
]


@contextmanager
def _connect(database_path):
    db = None
    try:
        path = Path(database_path).expanduser().resolve(strict=True)
        if not path.is_file():
            raise OSError("Not a file")
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=4)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(enrollments)")}
        if not _REQUIRED <= columns:
            raise sqlite3.DatabaseError("Unsupported schema")
        state_columns = {row["name"] for row in db.execute("PRAGMA table_info(app_roster_state)")}
        use_state = {"ruid", "semester", "active"} <= state_columns
        db.execute("BEGIN")
        yield db, columns, use_state
    except (OSError, sqlite3.Error, TypeError, RuntimeError):
        raise GradesUnavailableError(_UNAVAILABLE) from None
    finally:
        if db is not None:
            db.close()


def _order(semester):
    match = re.fullmatch(r"(Sp|Su|Fa)(\d{2}|\d{4})", str(semester or ""), re.I)
    if not match:
        return (0, 0, str(semester or ""))
    year = int(match[2])
    if year < 100:
        year += 2000
    month = {"sp": 1, "su": 6, "fa": 9}[match[1].lower()]
    return year, month, str(semester)


def _academic_year(semester):
    year, month, _ = _order(semester)
    if not year or month == 6:
        return None
    start = year if month >= 7 else year - 1
    return f"{start}–{start + 1}"


def _join(use_state):
    return (" LEFT JOIN app_roster_state rs ON rs.ruid=e.ruid AND rs.semester=e.semester"
            if use_state else "")


def _select(columns, use_state):
    fields = ["e.ruid", "e.semester", "e.name", "e.netid", "e.unit", 'e."class"',
              "e.curric", "e.official_grade", "e.course_average"]
    for optional in ("average_status", "roster_status"):
        fields.append(f"e.{optional}" if optional in columns else f"NULL AS {optional}")
    fields.append("COALESCE(rs.active,1) AS active" if use_state else "1 AS active")
    return ",".join(fields)


def _average(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _rank(sorted_averages, average):
    if average is None or not sorted_averages:
        return None
    lower = bisect_left(sorted_averages, average)
    upper = bisect_right(sorted_averages, average)
    total = len(sorted_averages)
    return {"rank": 1 + total - upper, "total": total,
            "percentile": round(100 * (lower + (upper - lower) / 2) / total, 2),
            "tied": upper - lower}


def search_students(database_path, query, limit=20):
    """Find distinct local students by literal name, RUID or NetID text.

    Blank queries deliberately return no records. SQL wildcard characters are
    treated literally rather than granting an accidental all-students search.
    """
    query = str(query or "").strip()
    if not query:
        return {"students": []}
    query = query[:160]
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError, OverflowError):
        limit = 20
    literal = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%" + literal + "%"
    with _connect(database_path) as (db, columns, use_state):
        # Limit distinct identities before loading history. Identity fields can
        # differ between semesters, so search every saved enrollment record.
        matches = db.execute(
            "SELECT ruid, MIN(name) AS sort_name FROM enrollments WHERE "
            "name LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "ruid LIKE ? ESCAPE '\\' OR netid LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "GROUP BY ruid ORDER BY sort_name COLLATE NOCASE, ruid LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        students = []
        for match in matches:
            rows = db.execute(
                "SELECT ruid,semester,name,netid FROM enrollments WHERE ruid=?",
                (match["ruid"],),
            ).fetchall()
            rows.sort(key=lambda row: _order(row["semester"]), reverse=True)
            latest = rows[0]
            students.append({"ruid": latest["ruid"], "name": latest["name"],
                             "netid": latest["netid"],
                             "semesters": [row["semester"] for row in rows]})
    return {"students": students}


def student_records(database_path, ruid):
    """Return one student's local history and reproducible average ranks."""
    identity = str(ruid or "").strip()
    if not identity or len(identity) > 80:
        return {"records": [], "attempts": 0, "notes": list(RANKING_NOTES)}
    with _connect(database_path) as (db, columns, use_state):
        rows = [dict(row) for row in db.execute(
            "SELECT " + _select(columns, use_state) + " FROM enrollments e" +
            _join(use_state) + " WHERE e.ruid=?", (identity,)
        )]
        rows.sort(key=lambda row: _order(row["semester"]), reverse=True)
        if not rows:
            return {"records": [], "attempts": 0, "notes": list(RANKING_NOTES)}
        # Only the aggregate comparison values leave this query. No other
        # student's identity is fetched while computing the comparison cohorts.
        cohort = db.execute(
            "SELECT e.semester,e.course_average FROM enrollments e" + _join(use_state) +
            " WHERE e.course_average IS NOT NULL AND "
            "UPPER(TRIM(COALESCE(e.official_grade,'')))<>'W'" +
            (" AND COALESCE(rs.active,1)=1" if use_state else "")
        ).fetchall()
        semesters = defaultdict(list)
        years = defaultdict(list)
        overall = []
        for member in cohort:
            average = _average(member["course_average"])
            if average is None:
                continue
            semesters[member["semester"]].append(average)
            year = _academic_year(member["semester"])
            if year:
                years[year].append(average)
            overall.append(average)
        overall.sort()
        for values in list(semesters.values()) + list(years.values()):
            values.sort()
        records = []
        attempts = 0
        for row in rows:
            active = bool(row["active"])
            grade = str(row["official_grade"] or "").strip().upper() or None
            if grade in ("TF", "TTZ"):
                grade = "TZ"
            if active and grade:
                attempts += 1
            average = _average(row["course_average"])
            # Invalid old withdrawn averages must never be surfaced as a course
            # result even if an inconsistent external database contains one.
            if grade == "W":
                average = None
            eligible = active and grade != "W" and average is not None
            year = _academic_year(row["semester"])
            records.append({
                "semester": row["semester"], "grade": grade, "average": average,
                "unit": row["unit"], "class": row["class"], "curric": row["curric"],
                "active": active, "average_status": row["average_status"],
                "roster_status": row["roster_status"], "academic_year": year,
                "semester_rank": _rank(semesters[row["semester"]], average) if eligible else None,
                "year_rank": _rank(years[year], average) if eligible and year else None,
                "overall_rank": _rank(overall, average) if eligible else None,
            })
        latest = rows[0]
        return {"ruid": latest["ruid"], "name": latest["name"], "netid": latest["netid"],
                "records": records, "attempts": attempts, "notes": list(RANKING_NOTES)}
