from decimal import Decimal

import pytest

from src.database import db
from src.services import marks as m

ENR = {1: "Asha Rao", 2: "Ben Ortiz", 3: "Chen Wei"}


def parse(text, mx=20, enrolled=ENR):
    return m.parse_marks_csv(text.encode(), mx, enrolled)


def test_valid_csv_and_decimal_rounding():
    p = parse("student_id,name,marks\n1,Asha Rao,18.5\n2,Ben Ortiz,7\n3,Chen Wei,20\n")
    assert p.can_commit and [r["obtained"] for r in p.rows] == [Decimal("18.50"), Decimal("7.00"), Decimal("20.00")]
    assert p.errors == [] and p.missing == []


def test_row_specific_errors_for_every_failure_type():
    p = parse("student_id,marks\n1,21\n2,abc\n2,5\nx,4\n9,3\n,6\n3,-1\n")
    by_row = {e.row: e.problem for e in p.errors}
    assert "exceeds the maximum of 20" in by_row[2]
    assert "not a number" in by_row[3]
    assert "duplicate of row 3" in by_row[4]
    assert "whole number" in by_row[5]
    assert "not enrolled" in by_row[6]
    assert "missing student_id" in by_row[7]
    assert "negative" in by_row[8]
    assert not p.can_commit                      # one bad row blocks the whole import


def test_blank_marks_warn_and_missing_students_are_listed():
    p = parse("student_id,marks\n1,10\n2,\n")
    assert p.can_commit and any("no marks" in w for w in p.warnings)
    assert p.missing == [(2, "Ben Ortiz"), (3, "Chen Wei")]


def test_header_aliases_bom_and_name_mismatch_warning():
    p = m.parse_marks_csv("\ufeffID,Name,Score\n1,Someone Else,5\n".encode("utf-8"), 10, ENR)
    assert p.can_commit and any("differs" in w for w in p.warnings) and p.rows[0]["name"] == "Asha Rao"  # matched by ID


@pytest.mark.parametrize("raw,needle", [
    (b"", "empty"), (b"a,b\n1,2\n", "student_id"), (b"\xff\xfe\x00bad", "UTF-8"),
    (b"student_id,marks\n", "No marks"), (b"x" * 1_000_001, "larger than 1 MB"),
])
def test_fatal_file_problems(raw, needle):
    p = m.parse_marks_csv(raw, 10, ENR)
    assert p.fatal and needle in p.fatal and not p.can_commit


def test_row_limit():
    big = "student_id,marks\n" + "1,1\n" * (m.MAX_ROWS + 5)
    assert "Too many rows" in parse(big).fatal


def test_percentage_and_csv_injection_are_safe():
    assert m.percentage(15, 20) == 75.0 and m.percentage(1, 0) is None
    out = m.marks_to_csv([{"student_id": 1, "name": "=HYPERLINK(\"http://evil\")", "obtained": 5}], 10)
    assert "'=HYPERLINK" in out and ",=HYP" not in out
    assert m.template_csv({1: "@x"}).splitlines()[1].startswith("1,'@x")


def test_validate_mark_edge_cases():
    assert m.validate_mark("NaN", 10)[1] and m.validate_mark("inf", 10)[1] and m.validate_mark(None, 10)[1]
    assert m.validate_mark("10", 10)[0] == Decimal("10.00") and m.validate_mark("10.01", 10)[1]


# ----------------------------------------------------------------------------- DB layer
@pytest.fixture()
def world(fake_db):
    db.create_teacher("t1", "password-1", "T1"); db.create_teacher("t2", "password-2", "T2")
    t1 = db.teacher_login("t1", "password-1")["teacher_id"]; t2 = db.teacher_login("t2", "password-2")["teacher_id"]
    sub = db.create_subject("S1", "Sub", "A", t1)[0]["subject_id"]
    stu = [db.create_student(n, [float(i)] * 128)[0]["student_id"] for i, n in enumerate(["A", "B", "C"])]
    for s in stu[:2]:
        db.enroll_student_to_subject(s, sub)
    a = db.create_assessment(t1, sub, "Mid-Semester 1", 20, "2026-09-20")
    return fake_db, t1, t2, sub, stu, a["assessment_id"]


def test_assessment_rules_and_ownership(world):
    fake, t1, t2, sub, stu, aid = world
    with pytest.raises(db.DuplicateError, match="already has"):
        db.create_assessment(t1, sub, "Mid-Semester 1", 20)
    with pytest.raises(db.PermissionDenied):
        db.create_assessment(t2, sub, "Hack", 10)
    with pytest.raises(db.DatabaseError):
        db.create_assessment(t1, sub, "Zero", 0)
    with pytest.raises(db.PermissionDenied):
        db.list_assessments(t2, sub)
    for fn, args in ((db.get_marks, (t2, aid)), (db.set_published, (t2, aid, True)), (db.import_marks, (t2, aid, [])), (db.get_marks_audit, (t2, aid))):
        with pytest.raises(db.PermissionDenied):
            fn(*args)


def test_import_is_atomic_and_revalidated_server_side(world):
    fake, t1, _, sub, stu, aid = world
    good = [{"student_id": stu[0], "obtained": 15}, {"student_id": stu[1], "obtained": 9.5}]
    assert db.import_marks(t1, aid, good) == 2
    before = [dict(r) for r in fake.tables["marks"]]
    for bad in ([{"student_id": stu[0], "obtained": 3}, {"student_id": stu[1], "obtained": 99}],     # over max
                [{"student_id": stu[0], "obtained": 3}, {"student_id": stu[2], "obtained": 5}],      # not enrolled
                [{"student_id": stu[0], "obtained": 3}, {"student_id": stu[0], "obtained": 4}],      # duplicate
                [{"student_id": stu[0], "obtained": 3}, {"student_id": stu[1], "obtained": "abc"}]):  # not numeric
        with pytest.raises(db.DatabaseError):
            db.import_marks(t1, aid, bad)
        assert fake.tables["marks"] == before            # nothing partially updated, not even the valid first row
    assert db.import_marks(t1, aid, [{"student_id": stu[0], "obtained": 16}]) == 1   # re-import edits in place
    assert len(fake.tables["marks"]) == 2 and {r["obtained"] for r in fake.tables["marks"]} == {16.0, 9.5}
    assert all(r["updated_by"] == t1 for r in fake.tables["marks"])
    assert sorted(r["name"] for r in db.get_marks(t1, aid)) == ["A", "B"]


def test_students_only_see_their_own_published_marks(world):
    fake, t1, t2, sub, stu, aid = world
    db.import_marks(t1, aid, [{"student_id": stu[0], "obtained": 15}, {"student_id": stu[1], "obtained": 9}])
    assert db.get_student_marks(stu[0]) == []                                     # draft: invisible
    assert [x["assessment"] for x in db.get_student_pending_assessments(stu[0])] == ["Mid-Semester 1"]
    assert db.get_student_pending_assessments(stu[2]) == []                       # not enrolled: not even names
    db.set_published(t1, aid, True)
    mine = db.get_student_marks(stu[0])
    assert [(x["subject"], x["obtained"], x["max_marks"]) for x in mine] == [("Sub", 15, 20)]
    assert [x["obtained"] for x in db.get_student_marks(stu[1])] == [9]           # each sees only own row
    assert db.get_student_marks(stu[2]) == [] and db.get_student_pending_assessments(stu[0]) == []
    db.set_published(t1, aid, False)                                              # unpublish hides again
    assert db.get_student_marks(stu[0]) == []
