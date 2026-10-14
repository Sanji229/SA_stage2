"""Pure attendance business logic (no Streamlit, no database) so it is unit-testable."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional

import pandas as pd


def new_session_timestamp() -> str:
    """UTC ISO-8601 timestamp that identifies one attendance session."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:  # legacy rows were stored as naive local time
        return parsed
    return parsed.astimezone()


def build_session(
    enrolled: Iterable[Mapping],
    present: Mapping[int, str],
    subject_id: int,
    timestamp: str,
    absent_notes: Optional[Mapping[int, str]] = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Build the review table and DB rows for one session.

    `present` maps student_id -> a human readable source ("Photo 1", "Voice 0.81").
    Every enrolled student gets a row: present if in `present`, otherwise absent.
    """
    rows, logs = [], []
    for student in sorted(enrolled, key=lambda s: str(s["name"]).lower()):
        sid = int(student["student_id"])
        source = present.get(sid)
        is_present = source is not None
        rows.append(
            {
                "Name": student["name"],
                "Status": "Present" if is_present else "Absent",
                "Evidence": source if is_present else (absent_notes or {}).get(sid, "-"),
            }
        )
        logs.append(
            {"student_id": sid, "subject_id": subject_id, "timestamp": timestamp, "is_present": is_present}
        )
    return pd.DataFrame(rows), logs


def attendance_rate(present: int, total: int) -> Optional[float]:
    return None if total == 0 else round(100.0 * present / total, 1)


def student_stats(logs: Iterable[Mapping]) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {}
    for log in logs:
        s = stats.setdefault(log["subject_id"], {"total": 0, "attended": 0})
        s["total"] += 1
        s["attended"] += 1 if log.get("is_present") else 0
    return stats


def records_to_frame(records: Iterable[Mapping]) -> pd.DataFrame:
    """Flatten teacher attendance rows into one detailed DataFrame."""
    data = []
    for r in records:
        parsed = parse_ts(r.get("timestamp"))
        student = r.get("students") or {}
        subject = r.get("subjects") or {}
        data.append(
            {
                "session": r.get("timestamp"),
                "subject_id": r.get("subject_id"),
                "student_id": r.get("student_id"),
                "when": parsed,
                "Subject": subject.get("name", "?"),
                "Subject Code": subject.get("subject_code", "?"),
                "Student": student.get("name", f"#{r.get('student_id')}"),
                "Present": bool(r.get("is_present")),
            }
        )
    return pd.DataFrame(
        data, columns=["session", "subject_id", "student_id", "when", "Subject", "Subject Code", "Student", "Present"]
    )


def session_summary(detail: pd.DataFrame) -> pd.DataFrame:
    """One row per attendance session, newest first."""
    if detail.empty:
        return pd.DataFrame(columns=["Date", "Subject", "Code", "Present", "Total", "Rate %"])
    g = (
        detail.groupby(["session", "Subject", "Subject Code"], dropna=False)
        .agg(Present=("Present", "sum"), Total=("Present", "count"), when=("when", "first"))
        .reset_index()
    )
    g["Rate %"] = (100 * g["Present"] / g["Total"]).round(1)
    g = g.sort_values("session", ascending=False)
    g["Date"] = g["when"].map(lambda d: d.strftime("%d %b %Y, %H:%M") if d is not None and pd.notna(d) else "Unknown")
    return g.rename(columns={"Subject Code": "Code"})[["Date", "Subject", "Code", "Present", "Total", "Rate %"]]


def subject_rates(detail: pd.DataFrame) -> pd.DataFrame:
    """Overall attendance rate per subject, computed from real log rows."""
    if detail.empty:
        return pd.DataFrame(columns=["Subject", "Rate %"])
    g = detail.groupby("Subject")["Present"].agg(["sum", "count"])
    g["Rate %"] = (100 * g["sum"] / g["count"]).round(1)
    return g[["Rate %"]].reset_index()


def teacher_overview(subjects: list[Mapping], detail: pd.DataFrame) -> dict:
    sessions = int(detail["session"].nunique()) if not detail.empty else 0
    present = int(detail["Present"].sum()) if not detail.empty else 0
    return {
        "subjects": len(subjects),
        "students": sum(int(s.get("total_students", 0)) for s in subjects),
        "sessions": sessions,
        "rate": attendance_rate(present, len(detail)),
    }


# ------------------------------------------------------------- teacher review layer
SOURCE_AUTO, SOURCE_MANUAL, SOURCE_CORRECTED = "auto", "manual", "corrected"


def build_review_session(
    enrolled: Iterable[Mapping],
    present: Mapping[int, str],
    subject_id: int,
    timestamp: str,
    scores: Optional[Mapping[int, float]] = None,
    review_notes: Optional[Mapping[int, str]] = None,
    method: str = "face",
) -> tuple[pd.DataFrame, list[dict]]:
    """Like build_session, but the table is editable and carries review flags.

    `present`: student_id -> evidence for confident automatic matches.
    `review_notes`: student_id -> why a human should look (ambiguous/duplicate/no profile...).
    Students with a note are listed first so the teacher sees them immediately.
    """
    scores, review_notes = scores or {}, review_notes or {}
    rows, logs = [], []
    ordered = sorted(enrolled, key=lambda s: (int(s["student_id"]) not in review_notes, str(s["name"]).lower()))
    for student in ordered:
        sid = int(student["student_id"])
        is_present = sid in present
        rows.append({
            "ID": sid,
            "Name": student["name"],
            "Present": is_present,
            "Evidence": present.get(sid, "-"),
            "Review": review_notes.get(sid, ""),
        })
        logs.append({
            "student_id": sid, "subject_id": subject_id, "timestamp": timestamp, "is_present": is_present,
            "source": SOURCE_AUTO, "match_score": scores.get(sid), "method": method,
        })
    return pd.DataFrame(rows, columns=["ID", "Name", "Present", "Evidence", "Review"]), logs


def apply_review_edits(logs: list[dict], edited: pd.DataFrame) -> list[dict]:
    """Merge the teacher's edits into the log rows; changed rows become source='manual'.

    Only the Present column is trusted from the browser, matched back by student ID, and
    unknown IDs are ignored (a tampered table cannot add students).
    """
    wanted = {int(r["ID"]): bool(r["Present"]) for _, r in edited.iterrows()}
    out = []
    for log in logs:
        new = dict(log)
        sid = int(log["student_id"])
        if sid in wanted and wanted[sid] != bool(log["is_present"]):
            new["is_present"], new["source"] = wanted[sid], SOURCE_MANUAL
        out.append(new)
    return out


def merge_photo_results(results, ids_in_class: set[int]) -> tuple[dict[int, str], dict[int, float], dict[int, str], dict[str, int]]:
    """Combine per-photo FaceMatch results into (present, scores, review_notes, totals)."""
    present: dict[int, str] = {}
    scores: dict[int, float] = {}
    notes: dict[int, list[str]] = {}
    totals = {"faces": 0, "matched": 0, "ambiguous": 0, "duplicate": 0, "unknown": 0, "small": 0}
    for p_idx, res in enumerate(results, start=1):
        for f in res.faces:
            totals["faces"] += 1
            totals[f.status] += 1
            totals["small"] += "small_face" in f.flags
            if f.status == "matched" and f.student_id not in present:
                present[f.student_id] = f"Photo {p_idx}"
                scores[f.student_id] = f.distance
            elif f.status in ("ambiguous", "duplicate"):
                label = "ambiguous match" if f.status == "ambiguous" else "face claimed twice"
                if "other_class_closer" in f.flags:
                    label = "may be a student from another class"
                for sid in f.candidates:
                    if sid in ids_in_class:
                        notes.setdefault(sid, []).append(f"Photo {p_idx}, face {f.index + 1}: {label}")
    return present, scores, {k: "; ".join(v) for k, v in notes.items()}, totals


# ------------------------------------------------------------------ analytics
DEFAULT_MIN_ATTENDANCE = 75.0


def students_at_risk(detail: pd.DataFrame, minimum: float = DEFAULT_MIN_ATTENDANCE) -> pd.DataFrame:
    """Student/subject pairs whose attendance rate is below `minimum` % (computed from saved logs)."""
    cols = ["Student", "Subject", "Classes", "Attended", "Rate %"]
    if detail.empty:
        return pd.DataFrame(columns=cols)
    g = detail.groupby(["Student", "Subject"]).agg(Classes=("Present", "count"), Attended=("Present", "sum")).reset_index()
    g["Rate %"] = (100 * g["Attended"] / g["Classes"]).round(1)
    return g[g["Rate %"] < minimum].sort_values("Rate %")[cols].reset_index(drop=True)


def attendance_trend(detail: pd.DataFrame) -> pd.DataFrame:
    """Class attendance rate per session, oldest first (for a line chart)."""
    s = session_summary(detail)
    if s.empty:
        return pd.DataFrame(columns=["Date", "Rate %"])
    return s.iloc[::-1][["Date", "Rate %"]].reset_index(drop=True)


def low_attendance_subjects(stats: Mapping[int, Mapping[str, int]], minimum: float = DEFAULT_MIN_ATTENDANCE) -> list[int]:
    """Subject ids where a student's own rate is below the minimum (needs at least one class)."""
    return [sid for sid, s in stats.items() if s["total"] and 100 * s["attended"] / s["total"] < minimum]
