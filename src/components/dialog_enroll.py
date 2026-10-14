import streamlit as st

from src.database.db import DatabaseError, enroll_student_to_subject, get_subject_by_code


@st.dialog("Enroll in a subject")
def enroll_dialog():
    st.write("Enter the subject code provided by your teacher.")
    code = st.text_input("Subject code", placeholder="CS101", max_chars=20)

    if st.button("Enroll now", type="primary", width="stretch"):
        if not code.strip():
            st.warning("Please enter a subject code.")
            return
        try:
            subject = get_subject_by_code(code)
            if not subject:
                st.error("No subject found with that code. Check it and try again.")
                return
            newly = enroll_student_to_subject(st.session_state.student_data["student_id"], subject["subject_id"])
        except DatabaseError as exc:
            st.error(str(exc))
            return
        st.session_state.flash = (
            f"Enrolled in {subject['name']}." if newly else f"You are already enrolled in {subject['name']}."
        )
        st.rerun()
