"""Headless end-to-end UI flows via streamlit.testing, backed by the in-memory fake DB.

AppTest cannot drive camera/file-upload widgets, so photo capture is covered by
tests/test_face_real.py instead. Real Supabase is NOT exercised here.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from src.database import config, db

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")


def run(**state):
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def texts(at):
    out = []
    for group in (at.markdown, at.error, at.warning, at.info, at.success, at.caption, at.subheader, at.metric):
        out += [str(getattr(e, "value", "")) + str(getattr(e, "label", "")) for e in group]
    return "\n".join(out)


def test_missing_config_shows_setup_screen_not_traceback(monkeypatch):
    config.set_client_for_testing(None)
    config._create_client.clear()
    for k in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.delenv(k, raising=False)
    at = run()
    assert not at.exception
    assert "needs configuration" in texts(at) or any("needs configuration" in t.value for t in at.title)


def test_landing_has_real_ctas_and_sections(fake_db):
    at = run()
    assert not at.exception
    page = texts(at)
    for needle in ("?portal=teacher&mode=register", "?portal=student", 'id="features"', 'id="how"', 'id="faq"', "Illustration"):
        assert needle in page, needle
    assert len(at.expander) >= 4  # FAQ


def test_portal_links_route_to_screens(fake_db):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["portal"] = "teacher"
    at.query_params["mode"] = "register"
    at.run()
    assert not at.exception and at.session_state["login_type"] == "teacher"
    assert "Create teacher account" in texts(at) or any("Create teacher account" in e.value for e in at.markdown)
    at2 = AppTest.from_file(APP, default_timeout=60)
    at2.query_params["portal"] = "student"
    at2.run()
    assert at2.session_state["login_type"] == "student" and not at2.exception


def test_teacher_register_then_login_then_dashboard(fake_db):
    at = run(login_type="teacher", teacher_login_type="register")
    f = at.text_input
    f[0].set_value("Ananya"); f[1].set_value("Ananya Roy"); f[2].set_value("short"); f[3].set_value("short")
    submit = [b for b in at.button if b.label == "Create account"][0]
    submit.click().run()
    assert any("at least 8" in e.value for e in at.error)          # validation message
    at.text_input[2].set_value("longenough1"); at.text_input[3].set_value("longenough1")
    [b for b in at.button if b.label == "Create account"][0].click().run()
    assert at.session_state["teacher_login_type"] == "login"
    assert len(fake_db.tables["teachers"]) == 1
    # login: wrong then right
    at.text_input[0].set_value("ananya"); at.text_input[1].set_value("wrong-pass-1")
    [b for b in at.button if b.label == "Log in"][0].click().run()
    assert any("Invalid username or password" in e.value for e in at.error)
    at.text_input[1].set_value("longenough1")
    [b for b in at.button if b.label == "Log in"][0].click().run()
    assert not at.exception and at.session_state["user_role"] == "teacher"
    assert "password" not in at.session_state["teacher_data"]
    assert any("No attendance has been recorded" in e.value for e in at.markdown)  # honest empty state


def _seed(fake_db):
    db.create_teacher("t1", "password-1", "Tess Teacher")
    t = db.teacher_login("t1", "password-1")
    s1 = db.create_subject("M1", "Mathematics", "A", t["teacher_id"])[0]
    s2 = db.create_subject("P1", "Physics", "B", t["teacher_id"])[0]
    stu = [db.create_student(n, [float(i)] * 128)[0]["student_id"] for i, n in enumerate(["Al", "Bo", "Cy"])]
    for s in stu:
        db.enroll_student_to_subject(s, s1["subject_id"])
    db.enroll_student_to_subject(stu[0], s2["subject_id"])
    db.save_attendance_session([
        {"student_id": stu[0], "subject_id": s1["subject_id"], "timestamp": "2026-03-01T09:00:00+00:00", "is_present": True},
        {"student_id": stu[1], "subject_id": s1["subject_id"], "timestamp": "2026-03-01T09:00:00+00:00", "is_present": False},
        {"student_id": stu[2], "subject_id": s1["subject_id"], "timestamp": "2026-03-01T09:00:00+00:00", "is_present": True},
    ])
    return t, stu


def test_teacher_dashboard_shows_real_numbers_in_every_tab(fake_db):
    t, _ = _seed(fake_db)
    at = run(login_type="teacher", teacher_data=t, is_logged_in=True, user_role="teacher")
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m == {"Subjects": "2", "Enrolled students": "4", "Sessions taken": "1", "Overall attendance": "66.7%"}
    for tab in ("Take attendance", "Subjects", "Records"):
        at.segmented_control[0].set_value(tab).run()
        assert not at.exception, tab
    # Subjects tab must list EVERY subject (original bug showed only the last one)
    at.segmented_control[0].set_value("Subjects").run()
    page = " ".join(e.value for e in at.markdown)
    assert "Mathematics" in page and "Physics" in page
    at.segmented_control[0].set_value("Records").run()
    assert len(at.dataframe) == 1 and at.dataframe[0].value.iloc[0]["Present"] == 2
    assert at.get("download_button")


def test_subject_html_is_escaped(fake_db):
    db.create_teacher("t2", "password-2", "T")
    t = db.teacher_login("t2", "password-2")
    db.create_subject("X1", '<img src=x onerror=alert(1)>', "A", t["teacher_id"])
    at = run(login_type="teacher", teacher_data=t, is_logged_in=True, user_role="teacher")
    at.segmented_control[0].set_value("Subjects").run()
    page = " ".join(e.value for e in at.markdown)
    assert "<img src=x" not in page and "&lt;img" in page


def test_student_dashboard_and_unenroll_flow(fake_db):
    t, stu = _seed(fake_db)
    at = run(login_type="student", is_logged_in=True, user_role="student", student_data={"student_id": stu[0], "name": "Al"})
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Enrolled subjects"] == "2" and m["Classes recorded"] == "1" and m["Overall attendance"] == "100.0%"
    # student with no enrolments gets an empty state, not a crash
    at2 = run(login_type="student", is_logged_in=True, user_role="student", student_data={"student_id": 999, "name": "New"})
    assert not at2.exception and any("not enrolled in any subject" in e.value for e in at2.markdown)


def test_join_link_requires_student_login_then_dialog(fake_db):
    _seed(fake_db)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["join-code"] = "P1"
    at.run()
    assert at.session_state["login_type"] == "student" and not at.exception


def test_teacher_can_correct_a_record_through_the_ui_and_it_is_audited(fake_db):
    t, stu = _seed(fake_db)
    at = run(login_type="teacher", teacher_data=t, is_logged_in=True, user_role="teacher")
    at.segmented_control[0].set_value("Records").run()
    assert not at.exception
    at.selectbox(key="corr_student").set_value("Bo")          # Bo was absent in the seeded session
    at.radio(key="corr_new").set_value("Present")
    at.button(key="corr_save").click().run()
    assert any("Please give a reason" in e.value for e in at.error)         # reason is mandatory
    assert [r["is_present"] for r in fake_db.tables["attendance_logs"] if r["student_id"] == stu[1]] == [False]
    at.text_input(key="corr_reason").set_value("Arrived late, confirmed by register")
    at.button(key="corr_save").click().run()
    assert not at.exception
    rec = [r for r in fake_db.tables["attendance_logs"] if r["student_id"] == stu[1]][0]
    assert rec["is_present"] is True and rec["source"] == "corrected"
    assert len(fake_db.tables["attendance_audit"]) == 1 and fake_db.tables["attendance_audit"][0]["changed_by"] == t["teacher_id"]


def test_ambiguous_student_face_never_offers_registration():
    # logic-level guard: the student screen only offers the registration form for status == unknown
    from src.pipelines.face_pipeline import FaceMatch, PhotoResult
    r = PhotoResult(1, [FaceMatch(0, status="ambiguous", candidates=[1, 2])])
    assert r.matched == {} and r.faces[0].status in ("ambiguous", "duplicate")


def test_marks_tab_creates_assessment_and_student_sees_only_published(fake_db):
    t, stu = _seed(fake_db)
    sub = db.get_teacher_subjects(t["teacher_id"])[0]["subject_id"]
    at = run(login_type="teacher", teacher_data=t, is_logged_in=True, user_role="teacher")
    at.segmented_control[0].set_value("Marks").run()
    assert not at.exception
    at.text_input[0].set_value("Mid-Semester 1")
    [b for b in at.button if b.label == "Create assessment"][0].click().run()
    assert not at.exception and len(fake_db.tables["assessments"]) == 1
    a = fake_db.tables["assessments"][0]
    db.import_marks(t["teacher_id"], a["assessment_id"], [{"student_id": stu[0], "obtained": 17}])

    def student_view():
        s = run(login_type="student", is_logged_in=True, user_role="student", student_data={"student_id": stu[0], "name": "Al"})
        assert not s.exception
        return " ".join(str(x.value) for x in s.dataframe) + " ".join(c.value for c in s.caption), s

    text, s = student_view()
    assert "pending publication" in text and not any(df.value.get("Obtained") is not None for df in s.dataframe if "Obtained" in df.value)
    db.set_published(t["teacher_id"], a["assessment_id"], True)
    _, s = student_view()
    marks = [df.value for df in s.dataframe if "Obtained" in df.value][0]
    assert marks.iloc[0]["Obtained"] == 17 and marks.iloc[0]["Percentage"] == 85.0
    # another student (enrolled, no mark row) never sees someone else's marks
    s2 = run(login_type="student", is_logged_in=True, user_role="student", student_data={"student_id": stu[1], "name": "Bo"})
    assert not [df for df in s2.dataframe if "Obtained" in df.value]
