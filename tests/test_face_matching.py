import numpy as np
import pytest

from evaluation.face_eval import evaluate, run, split_identities
from src.pipelines.face_pipeline import (AMBIGUOUS, DUPLICATE, MATCHED, UNKNOWN, build_gallery,
                                         confusable_pairs, match_encodings)

rng = np.random.default_rng(5)


def vec(scale=1.0):
    v = rng.normal(size=128)
    return v / np.linalg.norm(v) * scale


def gallery(n=4):
    base = {i: vec(1.0) for i in range(1, n + 1)}  # unit vectors: inter-identity distance ~1.4
    ids, mat = build_gallery([{"student_id": k, "face_embedding": v.tolist()} for k, v in base.items()])
    return base, ids, mat


def nudge(v, d):
    r = vec(1.0)
    return v + r * d  # distance from v is exactly d


def test_clear_match_unknown_and_status_fields():
    base, ids, mat = gallery()
    res = match_encodings([nudge(base[2], 0.1), vec(1.0)], ids, mat, threshold=0.45, bboxes=[(0, 0, 100, 100), (0, 0, 100, 100)])
    a, b = res.faces
    assert (a.status, a.student_id) == (MATCHED, 2) and a.distance == pytest.approx(0.1)
    assert b.status == UNKNOWN and b.student_id is None
    assert res.summary() == {"faces": 2, MATCHED: 1, AMBIGUOUS: 0, DUPLICATE: 0, UNKNOWN: 1}


def test_unknown_is_never_forced_onto_nearest_student():
    base, ids, mat = gallery()
    f = match_encodings([vec(1.0)], ids, mat, threshold=0.45).faces[0]
    assert f.status == UNKNOWN and f.student_id is None and f.distance > 0.45


def test_ambiguous_when_two_students_are_close():
    base, ids, mat = gallery()
    twin = nudge(base[1], 0.20)  # student 5 is nearly identical to student 1
    ids2, mat2 = build_gallery([{"student_id": k, "face_embedding": v.tolist()} for k, v in {**base, 5: twin}.items()])
    f = match_encodings([nudge(base[1], 0.10)], ids2, mat2, threshold=0.45, margin=0.15).faces[0]
    assert f.status == AMBIGUOUS and set(f.candidates) == {1, 5} and f.student_id is None


def test_other_class_student_closer_is_flagged_not_assigned():
    base, ids, mat = gallery()
    probe = nudge(base[1], 0.10)  # really student 1, who is NOT in this subject
    # student 2 is in class but also "plausible": make 2 close to 1 so it would be the in-class winner
    base2 = {**base, 2: nudge(base[1], 0.30)}
    ids2, mat2 = build_gallery([{"student_id": k, "face_embedding": v.tolist()} for k, v in base2.items()])
    f = match_encodings([probe], ids2, mat2, threshold=0.45, allowed_ids={2, 3, 4}, margin=0.30).faces[0]
    assert f.status == AMBIGUOUS and "other_class_closer" in f.flags and f.student_id is None


def test_duplicate_claim_goes_to_review():
    base, ids, mat = gallery()
    res = match_encodings([nudge(base[3], 0.05), nudge(base[3], 0.30)], ids, mat, threshold=0.45, margin=0.05)
    st = sorted(f.status for f in res.faces)
    assert st == [DUPLICATE, MATCHED] and res.matched.keys() == {3}  # nearest face keeps the match
    res = match_encodings([nudge(base[3], 0.20), nudge(base[3], 0.21)], ids, mat, threshold=0.45, margin=0.05)
    assert [f.status for f in res.faces] == [DUPLICATE, DUPLICATE] and res.matched == {}  # cannot tell which is right


def test_small_face_flag_and_empty_inputs():
    base, ids, mat = gallery()
    f = match_encodings([nudge(base[1], 0.1)], ids, mat, bboxes=[(0, 0, 20, 20)]).faces[0]
    assert "small_face" in f.flags and f.status == MATCHED
    assert match_encodings([], ids, mat).num_faces == 0
    e_ids, e_mat = build_gallery([])
    assert match_encodings([vec()], e_ids, e_mat).faces[0].status == UNKNOWN
    assert match_encodings([vec()], ids, mat, allowed_ids=set()).faces[0].status == UNKNOWN


def test_confusable_pairs_detects_near_duplicate_enrolment():
    base, _, _ = gallery()
    rows = [{"student_id": k, "face_embedding": v.tolist()} for k, v in {**base, 9: nudge(base[2], 0.1)}.items()]
    pairs = confusable_pairs(rows, 0.45)
    assert [(a, b) for a, b, _ in pairs] == [(2, 9)]
    assert confusable_pairs(rows[:1]) == []


# --------------------------------------------------------------- evaluation framework
def synthetic_dataset(n_people=12, per=5, spread=0.08):
    return {f"p{i}": np.array([vec(1.0) for _ in range(1)][0] + np.array([vec(1.0) * spread for _ in range(per)])) for i in range(n_people)}


def test_split_has_no_identity_leakage():
    tune, test = split_identities([f"p{i}" for i in range(20)])
    assert not set(tune) & set(test) and len(tune) + len(test) == 20
    assert split_identities([f"p{i}" for i in range(20)]) == (tune, test)  # deterministic


def test_evaluate_counts_on_known_geometry():
    data = synthetic_dataset()
    ids = list(data)
    m = evaluate(data, threshold=0.5, margin=0.05, enrolled=ids[:6], unknown=ids[6:])
    assert m.genuine_probes == 6 * 4 and m.unknown_probes == 6 * 5
    assert m.recall == 1.0 and m.far == 0.0 and m.precision == 1.0
    tight = evaluate(data, threshold=0.05, margin=0.05, enrolled=ids[:6], unknown=ids[6:])
    assert tight.recall == 0.0 and tight.far == 0.0  # too strict: everyone rejected, nobody wrongly accepted
    loose = evaluate(data, threshold=3.0, margin=0.0, enrolled=ids[:6], unknown=ids[6:])
    assert loose.far == 1.0  # too loose: every unknown person is accepted


def test_run_reports_tuned_threshold_on_heldout_split():
    r = run(synthetic_dataset(20), target_far=0.0, fixed_threshold=0.45)
    assert r["tune_threshold"] is not None and r["identities_tune"] + r["identities_test"] == 20
    assert r["tuned"]["FAR"] == 0.0 and r["fixed"]["recall"] == 1.0


def test_indistinguishable_identities_are_routed_to_review_not_accepted():
    same = {f"p{i}": np.array([vec(1.0) * 0.02 + np.ones(128) * 0.1 for _ in range(4)]) for i in range(8)}
    ids = list(same)
    m = evaluate(same, 0.45, 0.05, ids[:4], ids[4:])
    assert m.far == 0.0 and m.accepted_wrong == 0           # never confidently wrong
    assert m.recall == 0.0 and m.ambiguous_genuine == m.genuine_probes  # everything goes to the teacher
