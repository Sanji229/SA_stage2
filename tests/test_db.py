import pytest

from src.database import db


def _teacher(fake_db):
    db.create_teacher("Ananya", "correct-horse", "Ananya Roy")
    return db.teacher_login("ananya", "correct-horse")


def test_teacher_register_login_and_no_hash_leak(fake_db):
    t = _teacher(fake_db)
    assert t["name"] == "Ananya Roy" and "password" not in t
    assert db.teacher_login("ananya", "wrong-password") is None
    assert db.teacher_login("nobody", "x") is None
    assert fake_db.tables["teachers"][0]["password"].startswith("$2")  # bcrypt, not plaintext
    assert db.check_teacher_exists(" ANANYA ")


def test_duplicate_username_rejected(fake_db):
    _teacher(fake_db)
    with pytest.raises(db.DuplicateError):
        db.create_teacher("ananya", "another-pass1", "Imposter")


@pytest.mark.parametrize("u,n,p,c,ok", [
    ("ab", "N", "longenough", "longenough", False),
    ("good_user", "N", "short", "short", False),
    ("good_user", "N", "longenough", "different1", False),
    ("good_user", " ", "longenough", "longenough", False),
    ("good_user", "N", "x" * 80, "x" * 80, False),
    ("good_user", "N", "longenough", "longenough", True),
])
def test_validate_registration(u, n, p, c, ok):
    assert (db.validate_registration(u, n, p, c) is None) == ok


def test_subject_codes_unique_and_normalised(fake_db):
    t = _teacher(fake_db)
    db.create_subject(" cs 101 ", "Intro", "A", t["teacher_id"])
    assert db.get_subject_by_code("CS101")["name"] == "Intro"
    assert db.get_subject_by_code("cs101") is not None
    with pytest.raises(db.DuplicateError, match="already in use"):
        db.create_subject("CS101", "Other", "B", t["teacher_id"])


def test_enrollment_is_idempotent_and_reversible(fake_db):
    t = _teacher(fake_db)
    sub = db.create_subject("M1", "Math", "A", t["teacher_id"])[0]
    stu = db.create_student("Sam", [0.0] * 128, None)[0]
    assert db.enroll_student_to_subject(stu["student_id"], sub["subject_id"]) is True
    assert db.enroll_student_to_subject(stu["student_id"], sub["subject_id"]) is False
    assert len(fake_db.tables["subject_students"]) == 1
    assert [s["name"] for s in db.get_enrolled_students(sub["subject_id"])] == ["Sam"]
    assert db.get_teacher_subjects(t["teacher_id"])[0]["total_students"] == 1
    db.unenroll_student_to_subject(stu["student_id"], sub["subject_id"])
    assert db.get_enrolled_students(sub["subject_id"]) == []


def test_attendance_save_is_idempotent_and_counts_sessions(fake_db):
    t = _teacher(fake_db)
    sub = db.create_subject("M1", "Math", "A", t["teacher_id"])[0]
    a = db.create_student("A", [0.0] * 128)[0]["student_id"]
    b = db.create_student("B", [1.0] * 128)[0]["student_id"]
    for s in (a, b):
        db.enroll_student_to_subject(s, sub["subject_id"])
    logs = [
        {"student_id": a, "subject_id": sub["subject_id"], "timestamp": "2026-01-01T10:00:00+00:00", "is_present": True},
        {"student_id": b, "subject_id": sub["subject_id"], "timestamp": "2026-01-01T10:00:00+00:00", "is_present": False},
    ]
    assert db.save_attendance_session(logs) == 2
    assert db.save_attendance_session(logs) == 0  # double click / rerun: no duplicates
    assert len(fake_db.tables["attendance_logs"]) == 2
    assert db.get_teacher_subjects(t["teacher_id"])[0]["total_classes"] == 1
    assert db.save_attendance_session([]) == 0
    recs = db.get_attendance_for_teacher(t["teacher_id"])
    assert {r["students"]["name"] for r in recs} == {"A", "B"}


def test_teacher_cannot_see_other_teachers_records(fake_db):
    t1 = _teacher(fake_db)
    db.create_teacher("second", "password-two", "Second")
    t2 = db.teacher_login("second", "password-two")
    s1 = db.create_subject("A1", "One", "A", t1["teacher_id"])[0]
    stu = db.create_student("S", [0.0] * 128)[0]["student_id"]
    db.enroll_student_to_subject(stu, s1["subject_id"])
    db.save_attendance_session([{"student_id": stu, "subject_id": s1["subject_id"], "timestamp": "2026-01-01T10:00:00+00:00", "is_present": True}])
    assert db.get_attendance_for_teacher(t2["teacher_id"]) == []
    assert db.get_teacher_subjects(t2["teacher_id"]) == []
    assert len(db.get_attendance_for_teacher(t1["teacher_id"])) == 1


def test_database_failure_becomes_safe_error():
    from src.database import config

    class Boom:
        def table(self, _):
            raise RuntimeError("secret internals: key=abc")

    config.set_client_for_testing(Boom())
    try:
        with pytest.raises(db.DatabaseError) as e:
            db.get_teacher_subjects(1)
        assert "secret" not in str(e.value)
    finally:
        config.set_client_for_testing(None)
