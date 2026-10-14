import streamlit as st

from src.database.db import DatabaseError, DuplicateError, create_subject, normalize_code


@st.dialog("Create new subject")
def create_subject_dialog(teacher_id):
    st.write("Enter the details of the new subject.")
    code = st.text_input("Subject code", placeholder="CS101", max_chars=20, help="Students use this to join. Letters/numbers, no spaces.")
    name = st.text_input("Subject name", placeholder="Introduction to Computer Science", max_chars=100)
    section = st.text_input("Section", placeholder="A", max_chars=20)

    if st.button("Create subject", type="primary", width="stretch"):
        if not (code.strip() and name.strip() and section.strip()):
            st.warning("Please fill in all fields.")
            return
        if not normalize_code(code).replace("-", "").replace("_", "").isalnum():
            st.warning("Subject code may only contain letters, numbers, dash and underscore.")
            return
        try:
            create_subject(code, name, section, teacher_id)
        except DuplicateError as exc:
            st.error(str(exc))
            return
        except DatabaseError as exc:
            st.error(str(exc))
            return
        st.session_state.flash = f"Subject “{name.strip()}” created."
        st.rerun()
