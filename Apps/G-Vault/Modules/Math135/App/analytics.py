import teacher_links
import record_filters
"""Local Math 135 report calculations. Standard library only; no network access."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math
import re
import statistics as statistics_lib

GRADE_POINTS = {"A": 4.0, "B+": 3.5, "B": 3.0, "C+": 2.5,
                "C": 2.0, "D": 1.0, "F": 0.0, "XF": 0.0}
GRADE_ORDER = ["A", "B+", "B", "C+", "C", "D", "F", "XF", "W", "TZ"]
LETTER_STEPS = ["F", "D", "C", "C+", "B", "B+", "A"]
DEFAULT_THRESHOLDS = {"A": 85, "B+": 78, "B": 70, "C+": 63, "C": 55, "D": 52}
CURRENT_WEIGHTS = {"homework": 4, "wrappers": 4, "quiz": 20,
                   "midterm1": 18, "midterm2": 18, "final": 36}


def finite_number(value):
    """Blanks, invalid text and infinities never become a numeric zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def normalize_grade(value):
    value = str(value or "").strip().upper()
    return "TZ" if value in ("TF", "TTZ") else value


def round_half_up(value, digits=0):
    number = finite_number(value)
    if number is None:
        return None
    unit = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(unit, rounding=ROUND_HALF_UP))


def normalize_score(score, maximum=100):
    score, maximum = finite_number(score), finite_number(maximum)
    if score is None or maximum is None or maximum <= 0:
        return None
    return score * 100.0 / maximum


def percentile(ordered, fraction):
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def score_statistics(values, exclude_zeros=False, bin_width=10):
    """Population standard deviation; inclusive linear-interpolated quartiles."""
    values = list(values)
    numeric = [finite_number(value) for value in values]
    missing = sum(value is None for value in numeric)
    zeros = sum(value == 0 for value in numeric if value is not None)
    scores = sorted(value for value in numeric if value is not None and
                    not (exclude_zeros and value == 0))
    width = finite_number(bin_width)
    if width is None or width <= 0:
        raise ValueError("Histogram width must be a positive number.")
    # The last ordinary bin includes exactly 100; extra credit has its own bin.
    bins = []
    below = sum(value < 0 for value in scores)
    if below:
        bins.append({"label": "Below 0", "lower": None, "upper": 0, "count": below})
    start = 0.0
    while start < 100:
        stop = min(start + width, 100.0)
        count = sum(start <= value < stop or stop == 100 and value == 100
                    for value in scores)
        bins.append({"label": f"{start:g}–{stop:g}", "lower": start,
                     "upper": stop, "count": count})
        start = stop
    above = sum(value > 100 for value in scores)
    if above:
        bins.append({"label": "Above 100", "lower": 100, "upper": None, "count": above})
    result = {"total": len(values), "count": len(scores), "missing": missing,
              "blank_excluded": missing, "zero_count": zeros,
              "zeros_excluded": zeros if exclude_zeros else 0,
              "exclude_zeros": bool(exclude_zeros), "histogram": bins,
              "mean": None, "median": None, "standard_deviation": None,
              "minimum": None, "maximum": None, "q1": None, "q3": None}
    if scores:
        result.update(mean=statistics_lib.fmean(scores), median=statistics_lib.median(scores),
                      standard_deviation=statistics_lib.pstdev(scores),
                      minimum=scores[0], maximum=scores[-1],
                      q1=percentile(scores, .25), q3=percentile(scores, .75))
    result["stddev"] = result["standard_deviation"]
    return result


def grade_statistics(grades, include_w=True, include_tz=True):
    grades = [normalize_grade(grade) for grade in grades]
    counts = Counter(grades)
    display_counts = counts.copy()
    display_counts["F"] += display_counts["XF"]
    visible = [grade for grade in GRADE_ORDER if grade != "XF"
               if (include_w or grade != "W") and (include_tz or grade != "TZ")]
    total_displayed = sum(display_counts[grade] for grade in visible)
    points = [GRADE_POINTS[grade] for grade in grades if grade in GRADE_POINTS]
    completed = sum(counts[grade] for grade in GRADE_POINTS)
    failures = counts["D"] + counts["F"] + counts["XF"]
    dfw_denominator = completed + counts["W"]
    distribution = [{"grade": grade, "count": display_counts[grade],
                     "percent": 100 * display_counts[grade] / total_displayed if total_displayed else None}
                    for grade in visible]
    return {"roster_count": len(grades), "total": len(grades),
            "withdrawn": counts["W"], "non_withdrawn": len(grades) - counts["W"],
            "withdrawal_rate": 100 * counts["W"] / len(grades) if grades else None,
            "pending": counts[""], "tz": counts["TZ"],
            "xf_count": counts["XF"],
            "other_grades": {grade: count for grade, count in counts.items()
                             if grade and grade not in GRADE_ORDER},
            "count": total_displayed, "distribution": distribution,
            "gpa_count": len(points),
            "mean_gpa": statistics_lib.fmean(points) if points else None,
            "median_gpa": statistics_lib.median(points) if points else None,
            "df_count": failures, "df_denominator": completed,
            "df_rate": 100 * failures / completed if completed else None,
            "dfw_count": failures + counts["W"], "dfw_denominator": dfw_denominator,
            "dfw_rate": 100 * (failures + counts["W"]) / dfw_denominator if dfw_denominator else None,
            "rate_note": "XF is included with F in letter distributions, GPA and rates. Individual records retain XF. TZ, pending and non-letter grades are excluded from DF/DFW denominators."}


def semester_order(semester):
    match = re.fullmatch(r"(Sp|Su|Fa)(\d{2})", str(semester))
    return (2000 + int(match[2]), {"Sp": 0, "Su": 1, "Fa": 2}[match[1]]) if match else (0, 0)


def default_policy(semester):
    """Only the current/future grading policy is inferred; never rewrite history."""
    future = semester_order(semester) >= semester_order("Sp27")
    if semester != "Fa26" and not future:
        return None
    return {"weights": dict(CURRENT_WEIGHTS), "thresholds": dict(DEFAULT_THRESHOLDS),
            "final_thresholds": dict(DEFAULT_THRESHOLDS), "round_course_average": True,
            "round_final_score": True, "bump_enabled": True,
            "bump_minimum_rounded_average": 48 if future else None,
            "status": "future_template" if future else "current",
            "rule": "Processed homework/quiz averages are weighted directly. A higher final-exam letter raises the base letter one step."}


def letter_for_score(score, thresholds=None, rounded=True):
    number = round_half_up(score) if rounded else finite_number(score)
    if number is None:
        return None
    thresholds = thresholds or DEFAULT_THRESHOLDS
    for letter in reversed(LETTER_STEPS[1:]):
        if letter in thresholds and number >= float(thresholds[letter]):
            return letter
    return "F"


def _calculate_grade(scores, policy, semester=None):
    """Reconstruct a weighted grade without altering official or proposed grades."""
    if policy is None:
        return {"status": "policy_missing", "missing": [], "anticipated_letter": None}
    policy = dict(policy)
    for target, alias in (("thresholds", "cutoffs"),
                          ("bump_minimum_rounded_average", "minimum_bump_average"),
                          ("round_course_average", "round_average"),
                          ("round_final_score", "round_final")):
        if target not in policy and alias in policy:
            policy[target] = policy[alias]
    weights = {key: finite_number(weight) for key, weight in policy.get("weights", {}).items()}
    if not weights or any(weight is None or weight < 0 for weight in weights.values()):
        return {"status": "policy_invalid", "missing": [], "anticipated_letter": None,
                "message": "Grading weights have not been configured."}
    values = {key: finite_number(scores.get(key)) for key in weights}
    missing = [key for key in weights if weights[key] > 0 and values[key] is None]
    available_weight = sum(weight for key, weight in weights.items() if values[key] is not None)
    provisional = (sum(values[key] * weight for key, weight in weights.items()
                       if values[key] is not None) / available_weight if available_weight else None)
    result = {"status": "incomplete" if missing else "complete", "missing": missing,
              "provisional_average": provisional, "graded_weight": available_weight,
              "course_average": None, "rounded_average": None, "base_letter": None,
              "final_exam_letter": None, "anticipated_letter": None,
              "bump_applied": False, "bump_reason": "Incomplete data" if missing else "Not configured",
              "contributions": {}, "dropped": []}
    if missing:
        return result
    active = [key for key, weight in weights.items() if weight > 0]
    drops = int(policy.get("drop_lowest_midterm", 0))
    midterms = sorted((key for key in active if key.startswith("midterm")), key=lambda key: (values[key], key))
    if drops < 0 or drops >= len(midterms) and drops:
        result.update(status="policy_invalid", message="Invalid number of dropped midterms.")
        return result
    result["dropped"] = midterms[:drops]
    active = [key for key in active if key not in result["dropped"]]
    if abs(sum(weights[key] for key in active) - 100) > .000001:
        result.update(status="policy_invalid", message="Active weights must total 100%.")
        return result
    effective = dict(values)
    if policy.get("final_replaces_lowest_midterm") and "final" in effective:
        retained = [key for key in active if key.startswith("midterm")]
        if retained:
            lowest = min(retained, key=lambda key: (effective[key], key))
            effective[lowest] = max(effective[lowest], effective["final"])
    contributions = {key: float(Decimal(str(effective[key])) * Decimal(str(weights[key])) / 100)
                     for key in active}
    average = float(sum(Decimal(str(effective[key])) * Decimal(str(weights[key])) / 100 for key in active))
    rounded_average = round_half_up(average)
    result.update(course_average=average, rounded_average=rounded_average,
                  contributions=contributions)
    # Historical policies without cutoffs must not inherit today's letter scale.
    if not policy.get("thresholds"):
        result.update(status="average_only", bump_reason="Historical letter cutoffs are not configured")
        return result
    base = letter_for_score(average, policy["thresholds"], policy.get("round_course_average", True))
    final = letter_for_score(values.get("final"), policy.get("final_thresholds") or policy["thresholds"],
                             policy.get("round_final_score", True))
    result.update(base_letter=base, final_exam_letter=final, anticipated_letter=base)
    if not policy.get("bump_enabled", False):
        result["bump_reason"] = "No bump policy"
    elif final is None:
        result.update(status="incomplete", missing=["final"], anticipated_letter=None,
                      bump_reason="Final-exam score is missing")
    elif LETTER_STEPS.index(final) <= LETTER_STEPS.index(base):
        result["bump_reason"] = "Final-exam letter is not higher"
    else:
        minimum = policy.get("bump_minimum_rounded_average")
        if minimum is not None and rounded_average < float(minimum):
            result["bump_reason"] = "Rounded course average is below the qualifying minimum"
        else:
            result.update(anticipated_letter=LETTER_STEPS[min(LETTER_STEPS.index(base) + 1, len(LETTER_STEPS) - 1)],
                          bump_applied=True, bump_reason="Higher final-exam letter; one-step bump applied")
    return result


def calculate_grade(scores, policy, semester=None):
    """Public calculation result with stable aliases for importers and screens."""
    result = _calculate_grade(scores, policy, semester)
    for alias, key in (("weighted_average", "course_average"),
                       ("base_grade", "base_letter"),
                       ("final_exam_grade", "final_exam_letter"),
                       ("anticipated_grade", "anticipated_letter")):
        result[alias] = result.get(key)
    if policy is not None:
        normalized = dict(policy)
        for canonical, alias in (("thresholds", "cutoffs"),
                                 ("bump_minimum_rounded_average", "minimum_bump_average"),
                                 ("round_course_average", "round_average"),
                                 ("round_final_score", "round_final")):
            if canonical in normalized or alias in normalized:
                value = normalized.get(canonical, normalized.get(alias))
                normalized[canonical] = normalized[alias] = value
        result["policy"] = normalized
    return result


def compare_proposal(calculation, proposed):
    proposed = normalize_grade(proposed)
    expected = calculation.get("anticipated_letter")
    if not proposed:
        return "not_proposed"
    if calculation.get("status") != "complete" or not expected:
        return "incomplete_data"
    if proposed not in GRADE_POINTS:
        return "special_grade_review"
    return "match" if ("F" if proposed == "XF" else proposed) == expected else "discrepancy"


def statistics(values, exclude_zero=False):
    """Stable public statistics interface used by the local web app."""
    result = score_statistics(values, exclude_zeros=exclude_zero)
    result["min"] = result["minimum"]
    result["max"] = result["maximum"]
    return result


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _values(value):
    if value is None or value == "":
        return []
    return [str(item) for item in value if item is not None and str(item) != ""] if isinstance(value, (list, tuple, set)) else [str(value)]


def _where(params, alias="e", roster_alias="rs"):
    clauses, args = [f"COALESCE({roster_alias}.active,1)=1"], []
    for name, column in (("semester", f"{alias}.semester"), ("section", f"{roster_alias}.section")):
        selected = _values(params.get(name))
        if selected:
            clauses.append(column + " IN (" + ",".join("?" for _ in selected) + ")")
            args.extend(selected)
    filter_clause, filter_args = record_filters.group_clause(params, alias, roster_alias)
    if filter_clause:
        clauses.append(filter_clause)
        args.extend(filter_args)
    query = params.get("q", "")
    if isinstance(query, (list, tuple)):
        query = query[-1] if query else ""
    query = str(query or "").strip()
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(f"({alias}.name LIKE ? ESCAPE '\\' OR {alias}.ruid LIKE ? ESCAPE '\\' OR {alias}.netid LIKE ? ESCAPE '\\')")
        args.extend(["%" + escaped + "%"] * 3)
    return " AND ".join(clauses), args


def _mapping(row):
    return dict(row) if row is not None else {}


def report(db, params):
    """Aggregate filtered roster and score reports. All student rows stay local."""
    params = params or {}
    where, args = _where(params)
    join = " FROM enrollments e LEFT JOIN app_roster_state rs ON rs.ruid=e.ruid AND rs.semester=e.semester "
    grades = [row[0] for row in db.execute("SELECT e.official_grade" + join + "WHERE " + where, args)]
    grade_stats = grade_statistics(grades, _bool(params.get("include_w"), True),
                                   _bool(params.get("include_tz"), False))
    summary = {key: grade_stats[key] for key in
               ("dfw_count", "dfw_denominator", "dfw_rate", "df_count", "df_denominator", "df_rate",
                "mean_gpa", "median_gpa", "gpa_count", "pending", "tz", "withdrawal_rate", "xf_count")}
    summary.update(enrolled=grade_stats["roster_count"], withdrawn=grade_stats["withdrawn"],
                   remaining=grade_stats["non_withdrawn"], other_grades=grade_stats["other_grades"],
                   displayed_letters=grade_stats["count"])
    tz_rows = [dict(row) for row in db.execute(
        "SELECT e.name,e.ruid,e.netid,e.semester,rs.section,i.instructor,i.email" + join +
        "LEFT JOIN app_instructors i ON i.semester=e.semester AND i.section=rs.section " +
        "WHERE " + where + " AND e.official_grade IN ('TZ','TTZ','TF') ORDER BY e.semester,rs.section,e.name", args)]
    for row in tz_rows:
        row.update(teacher_links.section_names(db,row['semester'],row.get('section')))
        row['instructor']=row['lecturer']or row.get('instructor')or row['recitation']
    result = {"summary": summary, "letters": grade_stats["distribution"], "assessment": None,
              "tz_rows": tz_rows, "notes": [grade_stats["rate_note"],
                    "Enrolled means everyone on the selected roster. Remaining means everyone without W.",
                    "Assessment statistics use percentages; blanks are excluded and extra credit is retained."]}
    aid = params.get("assessment_id")
    if isinstance(aid, (list, tuple)):
        aid = aid[-1] if aid else None
    if aid:
        definition = db.execute("SELECT * FROM assessment_definitions WHERE assessment_id=?", (aid,)).fetchone()
        if definition is None:
            raise ValueError("Select a valid assessment.")
        definition = dict(definition)
        custom_label = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_assessment_labels'").fetchone():
            custom = db.execute("SELECT label FROM app_assessment_labels WHERE assessment_id=?", (aid,)).fetchone()
            custom_label = custom[0] if custom and custom[0] else None
        # Roster members with no score row still count as missing.
        score_rows = db.execute("SELECT s.percent" + join +
            "LEFT JOIN assessment_scores s ON s.ruid=e.ruid AND s.semester=e.semester AND s.assessment_id=? " +
            "WHERE " + where + " AND e.semester=?", [aid] + args + [definition["semester"]]).fetchall()
        stats = statistics([row[0] for row in score_rows], _bool(params.get("exclude_zero"), False))
        result["assessment"] = {"name": definition["semester"] + " " + (custom_label or assessment_label(definition["assessment_key"])),
                                "assessment_id": aid, "semester": definition["semester"],
                                "stats": {key: value for key, value in stats.items() if key != "histogram"},
                                "bins": stats["histogram"]}
    return result


def assessment_label(key):
    labels = {"homework": "Homework average", "quiz": "Quiz average", "recitation": "Recitation average",
              "wrappers": "Wrappers and surveys", "final": "Final exam", "precalculus": "Precalculus exam",
              "readiness": "Readiness test"}
    if key in labels:
        return labels[key]
    return re.sub(r"([a-z])([0-9])", r"\1 \2", key).replace("_", " ").title()


def grade_review(db, params):
    params = params or {}
    where, args = _where(params)
    join = " FROM enrollments e LEFT JOIN app_roster_state rs ON rs.ruid=e.ruid AND rs.semester=e.semester "
    enrollments = [dict(row) for row in db.execute(
        "SELECT e.*,rs.section,i.instructor,i.email,p.proposed_grade" + join +
        "LEFT JOIN app_instructors i ON i.semester=e.semester AND i.section=rs.section " +
        "LEFT JOIN app_proposals p ON p.ruid=e.ruid AND p.semester=e.semester " +
        "WHERE " + where + " ORDER BY e.name,e.semester", args)]
    policies = {}
    for row in db.execute("SELECT semester,policy_json FROM app_policies"):
        try:
            policies[row[0]] = json.loads(row[1])
        except (ValueError, TypeError):
            policies[row[0]] = None
    scores = defaultdict(dict)
    for row in db.execute("SELECT s.ruid,s.semester,d.assessment_key,s.percent "
                          "FROM assessment_scores s JOIN assessment_definitions d ON d.assessment_id=s.assessment_id "
                          "JOIN enrollments e ON e.ruid=s.ruid AND e.semester=s.semester "
                          "LEFT JOIN app_roster_state rs ON rs.ruid=e.ruid AND rs.semester=e.semester "
                          "WHERE " + where, args):
        scores[(row[0], row[1])][row[2]] = row[3]
    rows, summary = [], Counter()
    for enrollment in enrollments:
        semester = enrollment["semester"]
        policy = policies.get(semester)
        if policy is None:
            stored = db.execute("SELECT policy_json FROM semesters WHERE semester=?", (semester,)).fetchone()
            try:
                policy = json.loads(stored[0]) if stored else default_policy(semester)
            except (ValueError, TypeError):
                policy = None
        calculated = calculate_grade(scores[(enrollment["ruid"], semester)], policy, semester)
        official = normalize_grade(enrollment.get("official_grade"))
        proposed = normalize_grade(enrollment.get("proposed_grade"))
        comparison = compare_proposal(calculated, proposed)
        reason = calculated.get("bump_reason", calculated.get("message", "Grading policy is missing"))
        if official in ("W", "TZ"):
            status = "special_status"
            reason = "Withdrawn" if official == "W" else "Temporary grade; instructor follow-up required"
        elif comparison == "incomplete_data" or calculated.get("status") != "complete":
            status = "incomplete"
        elif comparison == "not_proposed":
            status = "no_proposal"
        elif comparison == "special_grade_review":
            status = "special_status"
            reason = "Instructor proposed a special grade; review manually"
        else:
            status = comparison
        summary[status] += 1
        row = {key: enrollment.get(key) for key in ("ruid", "name", "netid", "semester", "section", "instructor", "email")}
        row.update(teacher_links.section_names(db,row['semester'],row.get('section')))
        row['instructor']=row['lecturer']or row.get('instructor')or row['recitation']
        row.update(official_grade=official or None, proposed_grade=proposed or None,
                   course_average=calculated.get("course_average"),
                   saved_course_average=enrollment.get("course_average"),
                   rounded_average=calculated.get("rounded_average"),
                   provisional_average=calculated.get("provisional_average"),
                   base_grade=calculated.get("base_letter"),
                   final_exam_grade=calculated.get("final_exam_letter"),
                   anticipated_grade=calculated.get("anticipated_letter"),
                   bump_applied=calculated.get("bump_applied", False), status=status,
                   missing=calculated.get("missing", []), reason=reason,
                   contributions=calculated.get("contributions", {}))
        if official == "W":
            row.update(course_average=None, rounded_average=None, provisional_average=None,
                       base_grade=None, final_exam_grade=None, anticipated_grade=None, bump_applied=False)
        if _bool(params.get("mismatches_only")) and status != "discrepancy":
            continue
        if _bool(params.get("tz_only")) and official != "TZ":
            continue
        rows.append(row)
    summary["total"] = len(enrollments)
    summary["shown"] = len(rows)
    return {"rows": rows, "summary": dict(summary)}
