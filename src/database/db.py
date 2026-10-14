"""All database access lives here. UI code must not talk to Supabase directly."""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

import bcrypt

from src.database.config import ConfigError, get_supabase

log = logging.getLogger("smartattend.db")

MAX_PASSWORD_BYTES = 72  # bcrypt silently truncates beyond this
MIN_PASSWORD_LEN = 8
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


class DatabaseError(RuntimeError):
    """A database operation failed. The message is safe to show to users."""


class DuplicateError(DatabaseError):
    """A uniqueness constraint was violated."""


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "code", None) == "23505" or "23505" in str(exc) or "duplicate key" in str(exc).lower()


def _run(builder, action: str) -> list[dict[str, Any]]:
    try:
        return builder.execute().data or []
    except ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - convert to a user-safe error
        if _is_unique_violation(exc):
            raise DuplicateError(f"Could not {action}: that value already exists.") from exc
        log.exception("Database error while trying to %s", action)
        raise DatabaseError(f"Could not {action}. Please try again.") from exc


def _t(name: str):
    try:
        return get_supabase().table(name)
    except ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - never leak client internals to the UI
        log.exception("Could not open table %s", name)
        raise DatabaseError("The database is currently unavailable. Please try again.") from exc


# --------------------------------------------------------------------- passwords
def hash_pass(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()


def check_pass(pwd: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pwd.encode(), hashed.encode())
    except ValueError:
        return False


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_registration(username: str, name: str, password: str, confirm: str) -> Optional[str]:
    """Return an error message, or None when the input is valid."""
    if not username or not name.strip() or not password:
        return "All fields are required."
    if not USERNAME_RE.match(normalize_username(username)):
        return "Username must be 3-32 characters: letters, numbers, dot, dash or underscore."
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return "Password is too long (max 72 bytes)."
    if password != confirm:
        return "Passwords do not match."
    return None


# ---------------------------------------------------------------------- teachers
def check_teacher_exists(username: str) -> bool:
    rows = _run(_t("teachers").select("username").eq("username", normalize_username(username)), "check the username")
    return len(rows) > 0


def create_teacher(username: str, password: str, name: str):
    data = {"username": normalize_username(username), "password": hash_pass(password), "name": name.strip()}
    return _run(_t("teachers").insert(data), "create the teacher account")


def teacher_login(username: str, password: str) -> Optional[dict]:
    rows = _run(_t("teachers").select("*").eq("username", normalize_username(username)), "sign in")
    if rows and check_pass(password, rows[0]["password"]):
        teacher = dict(rows[0])
        teacher.pop("password", None)  # never keep the hash in session state
        return teacher
    return None


# ---------------------------------------------------------------------- students
def get_face_gallery() -> list[dict]:
    """Minimal rows needed for face matching (no voice data, no extra columns)."""
    rows = _run(_t("students").select("student_id, face_embedding"), "load enrolled faces")
    return [r for r in rows if r.get("face_embedding")]


def get_student(student_id: int) -> Optional[dict]:
    rows = _run(_t("students").select("student_id, name").eq("student_id", student_id), "load the student")
    return rows[0] if rows else None


def create_student(new_name: str, face_embedding=None, voice_embedding=None):
    data = {"name": new_name.strip(), "face_embedding": face_embedding, "voice_embedding": voice_embedding}
    return _run(_t("students").insert(data), "create the student profile")


# ---------------------------------------------------------------------- subjects
def normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", (code or "")).upper()


def create_subject(subject_code: str, name: str, section: str, teacher_id: int):
    data = {
        "subject_code": normalize_code(subject_code),
        "name": name.strip(),
        "section": section.strip(),
        "teacher_id": teacher_id,
    }
    try:
        return _run(_t("subjects").insert(data), "create the subject")
    except DuplicateError as exc:
        raise DuplicateError("That subject code is already in use. Choose a different one.") from exc


def get_subject_by_code(code: str) -> Optional[dict]:
    rows = _run(
        _t("subjects").select("subject_id, name, subject_code, section").eq("subject_code", normalize_code(code)),
        "look up the subject",
    )
    return rows[0] if rows else None


def get_teacher_subjects(teacher_id: int) -> list[dict]:
    subjects = _run(
        _t("subjects")
        .select("*, subject_students(count), attendance_logs(timestamp)")
        .eq("teacher_id", teacher_id),
        "load your subjects",
    )
    for sub in subjects:
        enrolled = sub.pop("subject_students", None) or []
        sub["total_students"] = enrolled[0].get("count", 0) if enrolled else 0
        logs = sub.pop("attendance_logs", None) or []
        sub["total_classes"] = len({log_["timestamp"] for log_ in logs})
    return subjects


# -------------------------------------------------------------------- enrollment
def is_enrolled(student_id: int, subject_id: int) -> bool:
    rows = _run(
        _t("subject_students").select("student_id").eq("student_id", student_id).eq("subject_id", subject_id),
        "check enrollment",
    )
    return bool(rows)


def enroll_student_to_subject(student_id: int, subject_id: int) -> bool:
    """Idempotent. Returns True if newly enrolled, False if already enrolled."""
    if is_enrolled(student_id, subject_id):
        return False
    try:
        _run(_t("subject_students").insert({"student_id": student_id, "subject_id": subject_id}), "enroll")
    except DuplicateError:
        return False  # lost a race with another request; still enrolled
    return True


def unenroll_student_to_subject(student_id: int, subject_id: int):
    return _run(
        _t("subject_students").delete().eq("student_id", student_id).eq("subject_id", subject_id), "unenroll"
    )


def get_enrolled_students(subject_id: int) -> list[dict]:
    rows = _run(
        _t("subject_students").select("student_id, students(student_id, name, voice_embedding)").eq("subject_id", subject_id),
        "load enrolled students",
    )
    return [r["students"] for r in rows if r.get("students")]


def get_student_subjects(student_id: int):
    return _run(_t("subject_students").select("*, subjects(*)").eq("student_id", student_id), "load your subjects")


# -------------------------------------------------------------------- attendance
def get_student_attendance(student_id: int):
    return _run(_t("attendance_logs").select("*, subjects(*)").eq("student_id", student_id), "load your attendance")


class PermissionDenied(DatabaseError):
    """The signed-in user may not perform this operation."""


def assert_teacher_owns_subject(teacher_id: int, subject_id: int) -> dict:
    """Server-side authorisation: enforced here, not just by hiding buttons in the UI."""
    rows = _run(_t("subjects").select("subject_id, name, teacher_id").eq("subject_id", subject_id), "check permissions")
    if not rows or rows[0]["teacher_id"] != teacher_id:
        raise PermissionDenied("You do not have permission to manage this subject.")
    return rows[0]


def get_enrolled_face_rows(subject_id: int) -> list[dict]:
    """Enrolled students with stored face embedding (for data-quality checks only)."""
    rows = _run(
        _t("subject_students").select("student_id, students(student_id, name, face_embedding)").eq("subject_id", subject_id),
        "load enrolled students",
    )
    return [r["students"] for r in rows if r.get("students")]


_EXTENDED_COLS = ("source", "match_score", "method", "marked_by")


def _is_missing_column(exc: Exception) -> bool:
    return getattr(exc, "code", None) in ("PGRST204", "42703") or "schema cache" in str(exc) or "does not exist" in str(exc)


def save_attendance_session(logs: Iterable[dict], teacher_id: int | None = None) -> int:
    """Persist one attendance session. Safe to call twice with the same logs.

    Server-side invariants (not dependent on the UI):
      * every row is for the same subject and timestamp (one session)
      * the teacher owns the subject (when teacher_id is given)
      * every student is currently enrolled in the subject
      * a student appears at most once; repeated saves are a no-op
    The DB unique constraint (subject_id, student_id, timestamp) is the final guard against races.
    Works on databases without migration 002: extended columns are dropped on a schema error.
    """
    logs = [dict(l) for l in logs]
    if not logs:
        return 0
    subject_id, ts = logs[0]["subject_id"], logs[0]["timestamp"]
    if any(l["subject_id"] != subject_id or l["timestamp"] != ts for l in logs):
        raise DatabaseError("Attendance rows must belong to a single session.")
    ids = [l["student_id"] for l in logs]
    if len(set(ids)) != len(ids):
        raise DatabaseError("A student appears more than once in this session.")
    if teacher_id is not None:
        assert_teacher_owns_subject(teacher_id, subject_id)
    enrolled = {s["student_id"] for s in get_enrolled_students(subject_id)}
    outsiders = set(ids) - enrolled
    if outsiders:
        raise DatabaseError("Some students are not enrolled in this subject; refresh the page and try again.")
    existing = _run(
        _t("attendance_logs").select("student_id").eq("subject_id", subject_id).eq("timestamp", ts),
        "check for an existing session",
    )
    if existing:
        return 0
    if teacher_id is not None:
        for l in logs:
            l.setdefault("marked_by", teacher_id)
    try:
        return len(_run(_t("attendance_logs").insert(logs), "save attendance"))
    except DuplicateError:
        return 0
    except DatabaseError as exc:
        if not isinstance(exc.__cause__, Exception) or not _is_missing_column(exc.__cause__):
            raise
        log.warning("attendance_logs lacks migration-002 columns; saving legacy columns only")
        legacy = [{k: v for k, v in l.items() if k not in _EXTENDED_COLS} for l in logs]
        try:
            return len(_run(_t("attendance_logs").insert(legacy), "save attendance"))
        except DuplicateError:
            return 0


def get_session_logs(teacher_id: int, subject_id: int, timestamp: str) -> list[dict]:
    assert_teacher_owns_subject(teacher_id, subject_id)
    return _run(
        _t("attendance_logs").select("*, students(name)").eq("subject_id", subject_id).eq("timestamp", timestamp),
        "load the session",
    )


def correct_attendance(teacher_id: int, subject_id: int, timestamp: str, student_id: int, new_present: bool, reason: str) -> bool:
    """Change one student's attendance in a saved session and record who/when/why.

    Returns False if nothing changed. Requires migration 002 (attendance_audit); we refuse to
    change attendance without an audit trail.
    """
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise DatabaseError("Please give a reason for the correction.")
    assert_teacher_owns_subject(teacher_id, subject_id)
    rows = _run(
        _t("attendance_logs").select("*").eq("subject_id", subject_id).eq("timestamp", timestamp).eq("student_id", student_id),
        "load the record",
    )
    if not rows:
        raise DatabaseError("That attendance record does not exist.")
    old = bool(rows[0]["is_present"])
    if old == bool(new_present):
        return False
    try:
        _run(
            _t("attendance_audit").insert({
                "subject_id": subject_id, "student_id": student_id, "session_timestamp": timestamp,
                "old_present": old, "new_present": bool(new_present), "reason": reason, "changed_by": teacher_id,
            }),
            "write the audit entry",
        )
    except DatabaseError as exc:
        raise DatabaseError("Corrections need the audit table. Run supabase/migrations/002_attendance_integrity.sql.") from exc
    patch = {"is_present": bool(new_present), "source": "corrected"}
    try:
        _run(_t("attendance_logs").update(patch).eq("subject_id", subject_id).eq("timestamp", timestamp).eq("student_id", student_id), "update attendance")
    except DatabaseError as exc:
        if exc.__cause__ is not None and _is_missing_column(exc.__cause__):
            _run(_t("attendance_logs").update({"is_present": bool(new_present)}).eq("subject_id", subject_id).eq("timestamp", timestamp).eq("student_id", student_id), "update attendance")
        else:
            raise
    return True


def get_audit_trail(teacher_id: int, subject_id: int) -> list[dict]:
    assert_teacher_owns_subject(teacher_id, subject_id)
    return _run(_t("attendance_audit").select("*, students(name)").eq("subject_id", subject_id), "load the audit trail")


def get_attendance_for_teacher(teacher_id: int) -> list[dict]:
    try:
        return _run(
            _t("attendance_logs")
            .select("*, subjects!inner(*), students(name)")
            .eq("subjects.teacher_id", teacher_id),
            "load attendance records",
        )
    except DatabaseError:
        # Fallback for databases without the attendance_logs -> students foreign key.
        return _run(
            _t("attendance_logs").select("*, subjects!inner(*)").eq("subjects.teacher_id", teacher_id),
            "load attendance records",
        )


# ------------------------------------------------------------------------- marks
def create_assessment(teacher_id: int, subject_id: int, name: str, max_marks: float, assessed_on=None) -> dict:
    assert_teacher_owns_subject(teacher_id, subject_id)
    name = (name or "").strip()
    if not name or len(name) > 60:
        raise DatabaseError("Assessment name is required (max 60 characters).")
    if not (0 < float(max_marks) <= 100000):
        raise DatabaseError("Maximum marks must be greater than zero.")
    row = {"subject_id": subject_id, "name": name, "max_marks": float(max_marks), "published": False, "created_by": teacher_id}
    if assessed_on:
        row["assessed_on"] = str(assessed_on)
    try:
        return _run(_t("assessments").insert(row), "create the assessment")[0]
    except DuplicateError as exc:
        raise DuplicateError("This subject already has an assessment with that name.") from exc


def list_assessments(teacher_id: int, subject_id: int) -> list[dict]:
    assert_teacher_owns_subject(teacher_id, subject_id)
    return _run(_t("assessments").select("*").eq("subject_id", subject_id), "load assessments")


def _owned_assessment(teacher_id: int, assessment_id: int) -> dict:
    rows = _run(_t("assessments").select("*").eq("assessment_id", assessment_id), "load the assessment")
    if not rows:
        raise DatabaseError("That assessment does not exist.")
    assert_teacher_owns_subject(teacher_id, rows[0]["subject_id"])
    return rows[0]


def set_published(teacher_id: int, assessment_id: int, published: bool) -> None:
    _owned_assessment(teacher_id, assessment_id)
    patch = {"published": bool(published)}
    _run(_t("assessments").update(patch).eq("assessment_id", assessment_id), "change publication")


def get_marks(teacher_id: int, assessment_id: int) -> list[dict]:
    _owned_assessment(teacher_id, assessment_id)
    rows = _run(_t("marks").select("*, students(name)").eq("assessment_id", assessment_id), "load marks")
    return [{"student_id": r["student_id"], "name": (r.get("students") or {}).get("name", r["student_id"]), "obtained": r["obtained"]} for r in rows]


def import_marks(teacher_id: int, assessment_id: int, rows: list[dict]) -> int:
    """Save marks atomically: ONE upsert request = one transaction. If any row is rejected
    (the app re-validates here; DB triggers enforce max marks and enrolment too), nothing is saved."""
    from src.services.marks import validate_mark

    a = _owned_assessment(teacher_id, assessment_id)
    enrolled = {s["student_id"] for s in get_enrolled_students(a["subject_id"])}
    payload, seen = [], set()
    for r in rows:
        sid = int(r["student_id"])
        value, why = validate_mark(r["obtained"], a["max_marks"])
        if sid not in enrolled:
            raise DatabaseError(f"Student {sid} is not enrolled in this subject.")
        if why:
            raise DatabaseError(f"Student {sid}: {why}.")
        if sid in seen:
            raise DatabaseError(f"Student {sid} appears twice.")
        seen.add(sid)
        payload.append({"assessment_id": assessment_id, "student_id": sid, "obtained": float(value), "updated_by": teacher_id})
    if not payload:
        return 0
    return len(_run(_t("marks").upsert(payload, on_conflict="assessment_id,student_id"), "save marks"))


def get_marks_audit(teacher_id: int, assessment_id: int) -> list[dict]:
    _owned_assessment(teacher_id, assessment_id)
    return _run(_t("marks_audit").select("*").eq("assessment_id", assessment_id), "load the audit trail")


def get_student_marks(student_id: int) -> list[dict]:
    """A student's own PUBLISHED marks only (the published filter is part of the query)."""
    rows = _run(
        _t("marks").select("*, assessments!inner(*)").eq("student_id", student_id).eq("assessments.published", True),
        "load your marks",
    )
    sub_ids = sorted({r["assessments"]["subject_id"] for r in rows})
    names = {}
    if sub_ids:
        subs = _run(_t("subjects").select("subject_id, name, subject_code").in_("subject_id", sub_ids), "load subjects")
        names = {s["subject_id"]: s for s in subs}
    out = []
    for r in rows:
        a = r["assessments"]
        s = names.get(a["subject_id"], {})
        out.append({"subject": s.get("name", "?"), "code": s.get("subject_code", "?"), "assessment": a["name"],
                    "assessed_on": a.get("assessed_on"), "obtained": r["obtained"], "max_marks": a["max_marks"]})
    return out


def get_student_pending_assessments(student_id: int) -> list[dict]:
    """Names of unpublished assessments in the student's subjects (never any marks)."""
    sub_ids = [r["subject_id"] for r in get_student_subjects(student_id)]
    if not sub_ids:
        return []
    rows = _run(_t("assessments").select("name, subject_id, published, assessed_on").in_("subject_id", sub_ids), "load assessments")
    return [{"assessment": r["name"], "subject_id": r["subject_id"]} for r in rows if not r["published"]]
