import pandas as pd
import pytest

from src.database import db
from src.services import attendance as svc

TS = "2026-02-01T09:00:00+00:00"


@pytest.fixture()
def world(fake_db):
    db.create_teacher("t1", "password-1", "T1"); db.create_teacher("t2", "password-2", "T2")
    t1, t2 = db.teacher_login("t1", "password-1"), db.teacher_login("t2", "password-2")
    sub = db.create_subject("S1", "Sub", "A", t1["teacher_id"])[0]["subject_id"]
    stu = [db.create_student(n, [float(i)] * 128)[0]["student_id"] for i, n in enumerate("ABC")]
    for s in stu[:2]:
        db.enroll_student_to_subject(s, sub)
    return fake_db, t1["teacher_id"], t2["teacher_id"], sub, stu


def logs(sub, ids, present=True, ts=TS):
    return [{"student_id": i, "subject_id": sub, "timestamp": ts, "is_present": present, "source": "auto", "match_score": 0.2, "method": "face"} for i in ids]


def test_save_checks_ownership_enrolment_and_shape(world):
    fake, t1, t2, sub, stu = world
    with pytest.raises(db.PermissionDenied):
        db.save_attendance_session(logs(sub, stu[:2]), teacher_id=t2)          # someone else's subject
    with pytest.raises(db.DatabaseError, match="not enrolled"):
        db.save_attendance_session(logs(sub, stu), teacher_id=t1)              # student C is not enrolled
    with pytest.raises(db.DatabaseError, match="more than once"):
        db.save_attendance_session(logs(sub, [stu[0], stu[0]]), teacher_id=t1)
    mixed = logs(sub, stu[:1]) + logs(sub, stu[1:2], ts="2026-02-02T09:00:00+00:00")
    with pytest.raises(db.DatabaseError, match="single session"):
        db.save_attendance_session(mixed, teacher_id=t1)
    assert fake.tables["attendance_logs"] == []                                 # nothing leaked through
    assert db.save_attendance_session(logs(sub, stu[:2]), teacher_id=t1) == 2
    assert db.save_attendance_session(logs(sub, stu[:2]), teacher_id=t1) == 0   # repeat upload
    row = fake.tables["attendance_logs"][0]
    assert row["source"] == "auto" and row["marked_by"] == t1 and row["match_score"] == 0.2


def test_works_on_unmigrated_database(world):
    fake, t1, _, sub, stu = world
    fake.missing_columns["attendance_logs"] = {"source", "match_score", "method", "marked_by"}
    assert db.save_attendance_session(logs(sub, stu[:2]), teacher_id=t1) == 2
    assert "source" not in fake.tables["attendance_logs"][0]


def test_database_level_unique_blocks_a_race(world):
    fake, t1, _, sub, stu = world
    from tests.fake_supabase import APIError
    fake.table("attendance_logs").insert(logs(sub, stu[:1])).execute()
    with pytest.raises(APIError) as e:  # a second concurrent writer that skipped the app check
        fake.table("attendance_logs").insert(logs(sub, stu[:1])).execute()
    assert e.value.code == "23505"


def test_correction_updates_audits_and_is_authorised(world):
    fake, t1, t2, sub, stu = world
    db.save_attendance_session(logs(sub, stu[:2], present=False), teacher_id=t1)
    assert db.correct_attendance(t1, sub, TS, stu[0], True, "Was in class, camera missed them") is True
    rec = [r for r in fake.tables["attendance_logs"] if r["student_id"] == stu[0]][0]
    assert rec["is_present"] is True and rec["source"] == "corrected"
    (audit,) = fake.tables["attendance_audit"]
    assert (audit["old_present"], audit["new_present"], audit["changed_by"]) == (False, True, t1) and "camera" in audit["reason"]
    assert db.correct_attendance(t1, sub, TS, stu[0], True, "again") is False   # no-op, no new audit row
    assert len(fake.tables["attendance_audit"]) == 1
    with pytest.raises(db.PermissionDenied):
        db.correct_attendance(t2, sub, TS, stu[1], True, "not my class")
    with pytest.raises(db.DatabaseError, match="reason"):
        db.correct_attendance(t1, sub, TS, stu[1], True, " ")
    with pytest.raises(db.DatabaseError, match="does not exist"):
        db.correct_attendance(t1, sub, "2030-01-01T00:00:00+00:00", stu[1], True, "typo")
    assert len(db.get_audit_trail(t1, sub)) == 1
    with pytest.raises(db.PermissionDenied):
        db.get_audit_trail(t2, sub)


# --------------------------------------------------------- review table (pure logic)
def test_review_table_lists_flagged_students_first_and_edits_are_marked_manual():
    enrolled = [{"student_id": 1, "name": "Zed"}, {"student_id": 2, "name": "Amy"}, {"student_id": 3, "name": "Bob"}]
    df, lg = svc.build_review_session(enrolled, {1: "Photo 1"}, 7, TS, scores={1: 0.21}, review_notes={3: "Photo 1, face 2: ambiguous match"})
    assert list(df["Name"])[0] == "Bob" and df.loc[df.Name == "Zed", "Present"].item() is True
    edited = df.copy(); edited.loc[edited.Name == "Bob", "Present"] = True
    out = {l["student_id"]: l for l in svc.apply_review_edits(lg, edited)}
    assert out[3]["is_present"] and out[3]["source"] == "manual"
    assert out[1]["source"] == "auto" and out[1]["match_score"] == 0.21 and not out[2]["is_present"]


def test_tampered_review_table_cannot_add_students():
    enrolled = [{"student_id": 1, "name": "A"}]
    _, lg = svc.build_review_session(enrolled, {}, 7, TS)
    forged = pd.DataFrame([{"ID": 1, "Present": False}, {"ID": 999, "Present": True}])
    assert [l["student_id"] for l in svc.apply_review_edits(lg, forged)] == [1]


def test_merge_photo_results_combines_status_and_notes():
    from src.pipelines.face_pipeline import FaceMatch, PhotoResult
    r1 = PhotoResult(3, [FaceMatch(0, status="matched", student_id=1, distance=0.2),
                         FaceMatch(1, status="ambiguous", candidates=[2, 3]), FaceMatch(2, status="unknown", flags=["small_face"])])
    r2 = PhotoResult(1, [FaceMatch(0, status="matched", student_id=1, distance=0.1)])
    present, scores, notes, totals = svc.merge_photo_results([r1, r2], {1, 2})
    assert present == {1: "Photo 1"} and scores == {1: 0.2}
    assert notes == {2: "Photo 1, face 2: ambiguous match"}  # student 3 not in class -> not mentioned
    assert totals == {"faces": 4, "matched": 2, "ambiguous": 1, "duplicate": 0, "unknown": 1, "small": 1}
