import numpy as np
import pandas as pd

from src.pipelines.face_pipeline import build_gallery, match_encodings
from src.pipelines.voice_pipeline import cosine_similarity, identify_speaker
from src.services import attendance as svc


def test_build_session_marks_everyone_enrolled():
    enrolled = [{"student_id": 2, "name": "Bo"}, {"student_id": 1, "name": "Al"}]
    df, logs = svc.build_session(enrolled, {1: "Photo 1"}, 9, "2026-01-01T10:00:00+00:00")
    assert list(df["Name"]) == ["Al", "Bo"]
    assert list(df["Status"]) == ["Present", "Absent"]
    assert [(l["student_id"], l["is_present"]) for l in logs] == [(1, True), (2, False)]
    assert all(l["subject_id"] == 9 and l["timestamp"] == "2026-01-01T10:00:00+00:00" for l in logs)


def test_attendance_rate_edge_cases():
    assert svc.attendance_rate(0, 0) is None
    assert svc.attendance_rate(1, 3) == 33.3


def test_parse_ts_handles_naive_and_utc():
    assert svc.parse_ts("2026-01-01T10:00:00") is not None
    assert svc.parse_ts("2026-01-01T10:00:00Z") is not None
    assert svc.parse_ts("garbage") is None and svc.parse_ts(None) is None


def test_summary_and_overview():
    recs = [
        {"timestamp": "2026-01-01T10:00:00+00:00", "is_present": True, "student_id": 1, "students": {"name": "A"}, "subjects": {"name": "Math", "subject_code": "M1"}},
        {"timestamp": "2026-01-01T10:00:00+00:00", "is_present": False, "student_id": 2, "students": {"name": "B"}, "subjects": {"name": "Math", "subject_code": "M1"}},
        {"timestamp": "2026-01-02T10:00:00+00:00", "is_present": True, "student_id": 1, "students": {"name": "A"}, "subjects": {"name": "Math", "subject_code": "M1"}},
    ]
    detail = svc.records_to_frame(recs)
    summ = svc.session_summary(detail)
    assert len(summ) == 2 and summ.iloc[0]["Present"] == 1 and summ.iloc[0]["Total"] == 1  # newest first
    assert svc.subject_rates(detail).iloc[0]["Rate %"] == 66.7
    o = svc.teacher_overview([{"total_students": 2}], detail)
    assert o == {"subjects": 1, "students": 2, "sessions": 2, "rate": 66.7}
    assert svc.session_summary(svc.records_to_frame([])).empty


def test_student_stats():
    s = svc.student_stats([{"subject_id": 1, "is_present": True}, {"subject_id": 1, "is_present": False}])
    assert s == {1: {"total": 2, "attended": 1}}


# ------------------------------------------------------------- matching logic
def _gallery():
    rng = np.random.default_rng(0)
    base = {1: rng.normal(size=128), 2: rng.normal(size=128), 3: rng.normal(size=128)}
    rows = [{"student_id": k, "face_embedding": v.tolist()} for k, v in base.items()]
    return base, *build_gallery(rows)


def test_match_picks_nearest_within_threshold():
    base, ids, mat = _gallery()
    noisy = base[2] + np.random.default_rng(1).normal(scale=0.001, size=128)
    r = match_encodings([noisy], ids, mat, threshold=0.6)
    assert set(r.matched) == {2} and r.num_faces == 1 and r.unmatched == 0


def test_unknown_face_is_not_matched():
    _, ids, mat = _gallery()
    stranger = np.random.default_rng(99).normal(size=128)
    assert match_encodings([stranger], ids, mat, threshold=0.6).matched == {}


def test_allowed_ids_restricts_candidates():
    base, ids, mat = _gallery()
    r = match_encodings([base[2]], ids, mat, allowed_ids={1, 3})
    assert r.matched == {}  # student 2 is not enrolled in this subject
    assert match_encodings([base[2]], ids, mat, allowed_ids=set()).matched == {}


def test_empty_gallery_and_no_faces():
    ids, mat = build_gallery([])
    assert match_encodings([np.zeros(128)], ids, mat).matched == {}
    base, ids, mat = _gallery()
    assert match_encodings([], ids, mat).num_faces == 0


def test_same_student_twice_keeps_best_distance():
    base, ids, mat = _gallery()
    near, far = base[1], base[1] + 0.05
    r = match_encodings([far, near], ids, mat)
    assert r.matched[1] == min(r.matched.values()) and r.matched[1] < 1e-9


def test_voice_identify():
    rng = np.random.default_rng(3)
    a, b = rng.normal(size=256), rng.normal(size=256)
    cands = {1: a.tolist(), 2: b.tolist(), 3: None}
    sid, score = identify_speaker(a + rng.normal(scale=0.01, size=256), cands)
    assert sid == 1 and score > 0.99
    sid, _ = identify_speaker(rng.normal(size=256), cands)
    assert sid is None
    assert identify_speaker(None, cands) == (None, 0.0)
    assert cosine_similarity(np.zeros(3), np.ones(3)) == 0.0


def test_students_at_risk_trend_and_student_warning():
    def rec(ts, present, sid, name):
        return {"timestamp": ts, "is_present": present, "student_id": sid, "subject_id": 1, "students": {"name": name}, "subjects": {"name": "Math", "subject_code": "M1"}}
    recs = [rec(f"2026-01-0{d}T10:00:00+00:00", p, sid, nm) for d in (1, 2, 3, 4) for sid, nm, p in ((1, "Ann", d != 2), (2, "Bob", d == 1))]
    detail = svc.records_to_frame(recs)
    risk = svc.students_at_risk(detail, 75)
    assert list(risk["Student"]) == ["Bob"] and risk.iloc[0]["Rate %"] == 25.0
    assert list(svc.students_at_risk(detail, 20)["Student"]) == []          # configurable threshold
    assert svc.students_at_risk(svc.records_to_frame([]), 75).empty
    t = svc.attendance_trend(detail)
    assert list(t["Rate %"]) == [100.0, 0.0, 50.0, 50.0] and len(t) == 4   # oldest first
    assert svc.low_attendance_subjects({1: {"total": 4, "attended": 1}, 2: {"total": 4, "attended": 4}, 3: {"total": 0, "attended": 0}}) == [1]
