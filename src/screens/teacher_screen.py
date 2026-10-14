from __future__ import annotations

import logging

import streamlit as st

from src.components.dialog_add_photo import add_photos_dialog
from src.components.dialog_attendance_results import attendance_result_dialog
from src.components.dialog_create_subject import create_subject_dialog
from src.components.dialog_share_subject import share_subject_dialog
from src.components.dialog_voice_attendance import voice_attendance_dialog
from src.components.footer import footer_dashboard
from src.components.header import header_dashboard
from src.components.subject_card import subject_card
from src.database import db
from src.screens.marks_ui import teacher_marks_tab
from src.database.db import DatabaseError
from src.pipelines.face_pipeline import analyze_photo, confusable_pairs
from src.services.attendance import (
    DEFAULT_MIN_ATTENDANCE,
    attendance_trend,
    build_review_session,
    students_at_risk,
    merge_photo_results,
    new_session_timestamp,
    records_to_frame,
    session_summary,
    subject_rates,
    teacher_overview,
)
from src.ui.base_layout import empty_state, page_header, show_flash, style_base_layout

log = logging.getLogger("smartattend.teacher")
TABS = ["Overview", "Take attendance", "Subjects", "Marks", "Records"]


def teacher_screen():
    style_base_layout()
    if "teacher_data" in st.session_state:
        teacher_dashboard()
    elif st.session_state.get("teacher_login_type") == "register":
        teacher_screen_register()
    else:
        teacher_screen_login()


# ------------------------------------------------------------------- dashboard
def teacher_dashboard():
    teacher = st.session_state.teacher_data
    right = header_dashboard()
    with right:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(f"**{teacher['name']}**")
        if c2.button("Log out", key="teacher_logout"):
            st.session_state.pop("teacher_data", None)
            st.session_state.is_logged_in = False
            st.session_state.user_role = None
            st.rerun()
    show_flash()

    tab = st.segmented_control("Section", TABS, default=TABS[0], key="teacher_tab", label_visibility="collapsed")
    st.divider()
    try:
        {
            "Overview": tab_overview,
            "Take attendance": tab_take_attendance,
            "Subjects": tab_subjects,
            "Marks": lambda: teacher_marks_tab(teacher["teacher_id"]),
            "Records": tab_records,
        }.get(tab or TABS[0], tab_overview)()
    except DatabaseError as exc:
        st.error(str(exc))
    footer_dashboard()


def _load_detail(teacher_id):
    return records_to_frame(db.get_attendance_for_teacher(teacher_id))


def tab_overview():
    teacher_id = st.session_state.teacher_data["teacher_id"]
    page_header("Overview", "A summary of your classes, calculated from saved attendance.")
    subjects = db.get_teacher_subjects(teacher_id)
    detail = _load_detail(teacher_id)
    o = teacher_overview(subjects, detail)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subjects", o["subjects"])
    c2.metric("Enrolled students", o["students"])
    c3.metric("Sessions taken", o["sessions"])
    c4.metric("Overall attendance", "–" if o["rate"] is None else f"{o['rate']}%")
    st.write("")

    if detail.empty:
        empty_state("No attendance has been recorded yet. Go to <b>Take attendance</b> to record your first session.")
        return
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Recent sessions")
        st.dataframe(session_summary(detail).head(8), hide_index=True, width="stretch")
    with right:
        st.subheader("Attendance rate by subject")
        st.bar_chart(subject_rates(detail), x="Subject", y="Rate %", horizontal=True, color="#4F46E5")

    trend = attendance_trend(detail)
    if len(trend) > 1:
        st.subheader("Attendance trend")
        st.line_chart(trend, x="Date", y="Rate %", color="#0D9488")
    st.subheader("Students at risk")
    minimum = st.number_input("Minimum attendance (%)", 0.0, 100.0, DEFAULT_MIN_ATTENDANCE, 5.0, key="min_attendance",
                              help="Students below this rate in a subject are listed.")
    risk = students_at_risk(detail, minimum)
    if risk.empty:
        st.success(f"Nobody is below {minimum:g}% in any subject.")
    else:
        st.dataframe(risk, hide_index=True, width="stretch")


# ------------------------------------------------------------ take attendance
def tab_take_attendance():
    teacher_id = st.session_state.teacher_data["teacher_id"]
    page_header("Take attendance", "Choose a subject, add classroom photos (or record audio), then review the result.")
    st.session_state.setdefault("attendance_images", [])
    images = st.session_state.attendance_images

    subjects = db.get_teacher_subjects(teacher_id)
    if not subjects:
        empty_state("You have not created a subject yet. Open <b>Subjects</b> to create one.")
        return
    by_id = {s["subject_id"]: s for s in subjects}

    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        subject_id = st.selectbox(
            "Subject", list(by_id), format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['subject_code']} (Sec {by_id[i]['section']})"
        )
    with c2:
        if st.button("Add photos", type="primary", icon=":material/photo_camera:", width="stretch"):
            add_photos_dialog()

    if images:
        st.caption(f"{len(images)} photo(s) ready")
        cols = st.columns(4)
        for i, img in enumerate(images):
            cols[i % 4].image(img, width="stretch", caption=f"Photo {i + 1}")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Clear photos", width="stretch", icon=":material/delete:", disabled=not images):
            st.session_state.attendance_images = []
            st.rerun()
    with b2:
        run = st.button("Run face analysis", width="stretch", type="primary", icon=":material/analytics:", disabled=not images)
    with b3:
        if st.button("Use voice attendance", width="stretch", icon=":material/mic:"):
            voice_attendance_dialog(subject_id)

    if not run:
        return
    enrolled = db.get_enrolled_students(subject_id)
    if not enrolled:
        st.warning("No students are enrolled in this subject yet. Share the subject code from the Subjects tab.")
        return

    allowed = {int(s["student_id"]) for s in enrolled}
    pairs = confusable_pairs(db.get_enrolled_face_rows(subject_id))
    if pairs:
        names = {s["student_id"]: s["name"] for s in enrolled}
        st.warning(
            "Data quality: some enrolled students have nearly identical stored faces, so automatic matching cannot "
            "tell them apart: " + "; ".join(f"{names.get(a, a)} ↔ {names.get(b, b)}" for a, b, _ in pairs[:5])
            + (f" (+{len(pairs) - 5} more)" if len(pairs) > 5 else "") + ". Their attendance will be sent for review."
        )
    try:
        results = []
        with st.spinner("Scanning classroom photos…"):
            for img in images:
                results.append(analyze_photo(img, allowed_ids=allowed))
    except DatabaseError as exc:
        st.error(str(exc))
        return
    except Exception:  # noqa: BLE001
        log.exception("Face analysis failed")
        st.error("Face analysis failed. Check that the photos are valid images and try again.")
        return

    present, scores, notes, t = merge_photo_results(results, allowed)
    if t["faces"] == 0:
        st.warning("No faces were detected in the photos. Try a clearer, closer or better-lit photo.")
        return
    summary = (
        f"{t['faces']} face(s) detected · {t['matched']} identified · {t['ambiguous'] + t['duplicate']} need review · "
        f"{t['unknown']} not recognised" + (f" · {t['small']} very small" if t["small"] else "")
    )
    st.caption(summary)
    if t["unknown"]:
        st.info("Faces that were not recognised are not assigned to anyone. If a student was missed, tick them as present in the review table.")
    df, logs = build_review_session(enrolled, present, subject_id, new_session_timestamp(), scores=scores, review_notes=notes)
    attendance_result_dialog(df, logs, summary)


# --------------------------------------------------------------------- subjects
def tab_subjects():
    teacher_id = st.session_state.teacher_data["teacher_id"]
    left, right = st.columns([3, 1], vertical_alignment="bottom")
    with left:
        page_header("Subjects", "Create subjects and share their join code with students.")
    with right:
        if st.button("Create subject", type="primary", width="stretch", icon=":material/add:"):
            create_subject_dialog(teacher_id)

    subjects = db.get_teacher_subjects(teacher_id)
    if not subjects:
        empty_state("No subjects yet. Press <b>Create subject</b> to add your first one.")
        return
    cols = st.columns(2)
    for i, sub in enumerate(sorted(subjects, key=lambda s: s["name"].lower())):  # every subject, not just the last
        def share_ui(sub=sub):
            if st.button("Share code", key=f"share_{sub['subject_id']}", icon=":material/share:"):
                share_subject_dialog(sub["name"], sub["subject_code"])

        with cols[i % 2]:
            subject_card(
                sub["name"], sub["subject_code"], sub["section"],
                stats=[("🫂", "students", sub["total_students"]), ("🕰️", "classes", sub["total_classes"])],
                footer_callback=share_ui,
            )


# --------------------------------------------------------------------- records
def tab_records():
    teacher_id = st.session_state.teacher_data["teacher_id"]
    page_header("Attendance records", "Every saved session. Filter by subject or export the detailed log.")
    detail = _load_detail(teacher_id)
    if detail.empty:
        empty_state("No attendance records yet.")
        return

    choice = st.selectbox("Subject", ["All subjects"] + sorted(detail["Subject"].unique()))
    view = detail if choice == "All subjects" else detail[detail["Subject"] == choice]
    st.dataframe(session_summary(view), hide_index=True, width="stretch")

    _corrections_panel(teacher_id, view)

    export = view.assign(Status=view["Present"].map({True: "Present", False: "Absent"}))
    export = export.assign(When=export["when"].map(lambda d: d.isoformat() if d is not None else ""))
    csv = export[["When", "Subject", "Subject Code", "Student", "Status"]].sort_values("When", ascending=False).to_csv(index=False)
    st.download_button("Download detailed CSV", csv, file_name="attendance.csv", mime="text/csv", icon=":material/download:")


def _corrections_panel(teacher_id, view):
    """Correct a saved record. Every change is audited (who, when, old/new, reason)."""
    with st.expander("Correct a saved attendance record"):
        sessions = view[["session", "Subject", "Subject Code"]].drop_duplicates().sort_values("session", ascending=False)
        if sessions.empty:
            st.caption("No sessions to correct.")
            return
        labels = {r.session: f"{r.Subject} · {r.session}" for r in sessions.itertuples()}
        ts = st.selectbox("Session", list(labels), format_func=labels.get, key="corr_session")
        rows = view[view["session"] == ts].sort_values("Student")
        sid_by_name = {r["Student"]: r for _, r in rows.iterrows()}
        who = st.selectbox("Student", list(sid_by_name), key="corr_student")
        current = bool(sid_by_name[who]["Present"])
        new = st.radio("Mark as", ["Present", "Absent"], index=0 if current else 1, horizontal=True, key="corr_new")
        reason = st.text_input("Reason (required)", max_chars=200, key="corr_reason")
        if st.button("Save correction", key="corr_save"):
            subject_id = sid_by_name[who]["subject_id"]
            student_id = sid_by_name[who]["student_id"]
            try:
                changed = db.correct_attendance(teacher_id, int(subject_id), ts, int(student_id), new == "Present", reason)
            except DatabaseError as exc:
                st.error(str(exc))
                return
            if changed:
                st.session_state.flash = f"Updated {who}: now {new.lower()}. The change was recorded in the audit trail."
                st.rerun()
            st.info("That is already the saved value; nothing changed.")
        trail = db.get_audit_trail(teacher_id, int(rows.iloc[0]["subject_id"])) if len(rows) else []
        if trail:
            st.caption("Audit trail for this subject")
            st.dataframe(
                [{"When": t["changed_at"] if "changed_at" in t else "", "Student": (t.get("students") or {}).get("name", t["student_id"]),
                  "From": "Present" if t["old_present"] else "Absent", "To": "Present" if t["new_present"] else "Absent", "Reason": t["reason"]} for t in trail],
                hide_index=True, width="stretch")


# ------------------------------------------------------------------ auth screens
def _auth_header(back_key: str):
    right = header_dashboard()
    with right:
        if st.button("Back to home", key=back_key):
            st.session_state.login_type = None
            st.session_state.teacher_login_type = "login"
            st.query_params.clear()
            st.rerun()


def teacher_screen_login():
    _auth_header("teacher_back_login")
    show_flash()
    page_header("Teacher login", "Sign in to manage subjects and take attendance.")
    with st.form("teacher_login"):
        username = st.text_input("Username", placeholder="ananyaroy", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in", type="primary", width="stretch")
    if submitted:
        if not username or not password:
            st.error("Enter both username and password.")
        else:
            try:
                teacher = db.teacher_login(username, password)
            except DatabaseError as exc:
                st.error(str(exc))
                teacher = None
            else:
                if teacher:
                    st.session_state.update(teacher_data=teacher, is_logged_in=True, user_role="teacher")
                    st.rerun()
                st.error("Invalid username or password.")
    if st.button("Create an account instead"):
        st.session_state.teacher_login_type = "register"
        st.rerun()
    footer_dashboard()


def teacher_screen_register():
    _auth_header("teacher_back_register")
    page_header("Create teacher account", "Choose a username and password (at least 8 characters).")
    with st.form("teacher_register"):
        username = st.text_input("Username", placeholder="ananyaroy", autocomplete="username")
        name = st.text_input("Full name", placeholder="Ananya Roy")
        password = st.text_input("Password", type="password", autocomplete="new-password")
        confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Create account", type="primary", width="stretch")
    if submitted:
        error = db.validate_registration(username, name, password, confirm)
        if error:
            st.error(error)
        else:
            try:
                if db.check_teacher_exists(username):
                    st.error("That username is already taken.")
                else:
                    db.create_teacher(username, password, name)
                    st.session_state.teacher_login_type = "login"
                    st.session_state.flash = "Account created. Please log in."
                    st.rerun()
            except db.DuplicateError:
                st.error("That username is already taken.")
            except DatabaseError as exc:
                st.error(str(exc))
    if st.button("I already have an account"):
        st.session_state.teacher_login_type = "login"
        st.rerun()
    footer_dashboard()
