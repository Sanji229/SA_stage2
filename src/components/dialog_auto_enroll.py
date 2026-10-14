import streamlit as st

from src.database.db import DatabaseError, enroll_student_to_subject, get_subject_by_code, is_enrolled


def _close():
    st.query_params.clear()
    st.rerun()


@st.dialog("Quick enrollment")
def auto_enroll_dialog(subject_code):
    student_id = st.session_state.student_data["student_id"]
    try:
        subject = get_subject_by_code(subject_code)
        if not subject:
            st.error("This join link is not valid: the subject code was not found.")
            if st.button("Close"):
                _close()
            return
        if is_enrolled(student_id, subject["subject_id"]):
            st.info(f"You are already enrolled in **{subject['name']}**.")
            if st.button("Got it"):
                _close()
            return
        st.markdown(f"Would you like to enroll in **{subject['name']}**?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("No thanks", width="stretch"):
                _close()
        with c2:
            if st.button("Yes, enroll me", type="primary", width="stretch"):
                enroll_student_to_subject(student_id, subject["subject_id"])
                st.session_state.flash = f"Enrolled in {subject['name']}."
                _close()
    except DatabaseError as exc:
        st.error(str(exc))
