from __future__ import annotations

import logging

import streamlit as st

from src.components.dialog_enroll import enroll_dialog
from src.components.footer import footer_dashboard
from src.components.header import header_dashboard
from src.components.subject_card import subject_card
from src.database.db import (
    DatabaseError,
    create_student,
    get_student,
    get_student_attendance,
    get_student_subjects,
    unenroll_student_to_subject,
)
from src.pipelines.face_pipeline import analyze_photo, clear_gallery_cache, get_face_embeddings
from src.pipelines.voice_pipeline import VoiceError, get_voice_embedding
from src.screens.marks_ui import student_marks_section
from src.services.attendance import DEFAULT_MIN_ATTENDANCE, attendance_rate, low_attendance_subjects, student_stats
from src.ui.base_layout import empty_state, page_header, show_flash, style_base_layout

log = logging.getLogger("smartattend.student")


def _start_session(student: dict) -> None:
    st.session_state.is_logged_in = True
    st.session_state.user_role = "student"
    st.session_state.student_data = {"student_id": student["student_id"], "name": student["name"]}


def _logout() -> None:
    st.session_state.pop("student_data", None)
    st.session_state.is_logged_in = False
    st.session_state.user_role = None


def student_dashboard():
    student = st.session_state.student_data
    right = header_dashboard()
    with right:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(f"**{student['name']}**")
        if c2.button("Log out", key="student_logout"):
            _logout()
            st.rerun()
    show_flash()

    top, action = st.columns([3, 1], vertical_alignment="bottom")
    with top:
        page_header("Your subjects", "Subjects you are enrolled in and your attendance so far.")
    with action:
        if st.button("Enroll in subject", type="primary", width="stretch"):
            enroll_dialog()

    try:
        with st.spinner("Loading your subjects…"):
            subjects = get_student_subjects(student["student_id"])
            logs = get_student_attendance(student["student_id"])
    except DatabaseError as exc:
        st.error(str(exc))
        return

    stats_map = student_stats(logs)
    total = sum(s["total"] for s in stats_map.values())
    attended = sum(s["attended"] for s in stats_map.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Enrolled subjects", len(subjects))
    m2.metric("Classes recorded", total)
    rate = attendance_rate(attended, total)
    m3.metric("Overall attendance", "–" if rate is None else f"{rate}%")
    st.write("")

    if not subjects:
        empty_state("You are not enrolled in any subject yet. Use <b>Enroll in subject</b> and enter the code from your teacher.")
        footer_dashboard()
        return

    low = set(low_attendance_subjects(stats_map, DEFAULT_MIN_ATTENDANCE))
    if low:
        names = [(n.get("subjects") or {}).get("name", "a subject") for n in subjects if n["subject_id"] in low]
        st.warning(f"Low attendance: you are below {DEFAULT_MIN_ATTENDANCE:g}% in " + ", ".join(names) + ".")

    cols = st.columns(2)
    for i, node in enumerate(subjects):
        sub = node.get("subjects") or {}
        sid = node["subject_id"]
        s = stats_map.get(sid, {"total": 0, "attended": 0})
        pct = attendance_rate(s["attended"], s["total"])

        def unenroll_ui(sub=sub, sid=sid):
            with st.popover("Unenroll", icon=":material/logout:"):
                st.write(f"Leave **{sub.get('name', 'this subject')}**? Your past attendance records are kept.")
                if st.button("Yes, unenroll", key=f"unenroll_{sid}", type="primary"):
                    try:
                        unenroll_student_to_subject(student["student_id"], sid)
                    except DatabaseError as exc:
                        st.error(str(exc))
                        return
                    st.session_state.flash = f"Unenrolled from {sub.get('name', 'subject')}."
                    st.rerun()

        with cols[i % 2]:
            subject_card(
                sub.get("name", "Unknown"),
                sub.get("subject_code", "?"),
                sub.get("section", "-"),
                stats=[("📅", "classes", s["total"]), ("✅", "attended", s["attended"])]
                + ([("📈", "%", pct)] if pct is not None else []),
                footer_callback=unenroll_ui,
                progress=pct,
            )
    st.divider()
    student_marks_section(student["student_id"])
    footer_dashboard()


def _registration_form(photo) -> None:
    with st.container(border=True):
        st.subheader("Create your profile")
        st.caption("Your face (and optional voice) is converted to numbers for matching. The photo itself is not stored.")
        name = st.text_input("Your name", placeholder="e.g. Hamza Rizvi", max_chars=60)
        st.markdown("**Optional: voice enrollment** for voice-only attendance")
        audio = None
        try:
            audio = st.audio_input("Record a short phrase, e.g. “My name is Akash, I am present.”")
        except Exception:  # noqa: BLE001
            st.info("Audio recording is not available in this browser.")

        if st.button("Create account", type="primary"):
            if not name.strip():
                st.warning("Please enter your name.")
                return
            with st.spinner("Creating your profile…"):
                encodings = get_face_embeddings(photo)
                if len(encodings) != 1:
                    st.error("Exactly one clear face is needed to register. Please retake the photo.")
                    return
                voice_emb = None
                if audio is not None:
                    try:
                        voice_emb = get_voice_embedding(audio.getvalue())
                    except (VoiceError, ImportError) as exc:
                        st.warning(f"Voice enrollment skipped: {exc}")
                try:
                    # st.write("Voice embedding exists:", voice_emb is not None)
                    # st.write("Voice embedding length:", len(voice_emb) if voice_emb else 0)
                    rows = create_student(name, face_embedding=encodings[0].tolist(), voice_embedding=voice_emb)
                except DatabaseError as exc:
                    st.error(str(exc))
                    return
            clear_gallery_cache()
            _start_session(rows[0])
            st.session_state.flash = f"Profile created. Welcome, {name.strip()}!"
            st.rerun()


def student_screen():
    style_base_layout()
    if "student_data" in st.session_state:
        student_dashboard()
        return

    right = header_dashboard()
    with right:
        if st.button("Back to home", key="student_back"):
            st.session_state.login_type = None
            st.query_params.clear()
            st.rerun()

    page_header("Student sign in", "Look at the camera to sign in with FaceID. New here? You will be asked to register.")
    photo = st.camera_input("Position your face in the centre of the frame")
    if photo:
        try:
            with st.spinner("Scanning…"):
                result = analyze_photo(photo)
                student = get_student(next(iter(result.matched))) if len(result.matched) == 1 and result.num_faces == 1 else None
        except DatabaseError as exc:
            st.error(str(exc))
            return
        except Exception:  # noqa: BLE001
            log.exception("Face scan failed")
            st.error("Could not process the photo. Please try again.")
            return

        if result.num_faces == 0:
            st.warning("No face found. Face the camera in good light and try again.")
        elif result.num_faces > 1:
            st.warning("More than one face found. Only one person should be in the frame.")
        elif result.faces and result.faces[0].status in ("ambiguous", "duplicate"):
            st.warning("Your face could not be matched confidently (it is very similar to another profile). "
                       "Please ask your teacher to verify you; registering again would create a duplicate profile.")
        elif student:
            _start_session(student)
            st.session_state.flash = f"Welcome back, {student['name']}!"
            st.rerun()
        else:
            st.info("Face not recognised. If you are new, register below.")
            _registration_form(photo)
    footer_dashboard()
