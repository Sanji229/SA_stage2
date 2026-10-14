import streamlit as st

from src.database.db import DatabaseError, save_attendance_session
from src.services.attendance import apply_review_edits


def show_attendance_result(df, logs):
    """Editable review table. Nothing is saved until the teacher confirms; edits are recorded as manual."""
    flagged = int((df["Review"] != "").sum())
    st.write("Review attendance before confirming. Tick or untick **Present** to correct any row.")
    if flagged:
        st.warning(f"{flagged} student(s) need your attention (listed first). Automatic matching was not certain for them.")
    edited = st.data_editor(
        df,
        hide_index=True,
        width="stretch",
        disabled=["ID", "Name", "Evidence", "Review"],
        column_config={"ID": None, "Present": st.column_config.CheckboxColumn("Present", help="Editable")},
        key=f"review_editor_{logs[0]['timestamp'] if logs else 'x'}",
    )
    final = apply_review_edits(logs, edited)
    n_present = sum(1 for l in final if l["is_present"])
    n_manual = sum(1 for l in final if l.get("source") == "manual")
    st.caption(f"{n_present} present · {len(final) - n_present} absent · {n_manual} manually changed")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Discard", width="stretch", key="att_discard"):
            st.session_state.voice_attendance_results = None
            st.session_state.attendance_images = []
            st.rerun()
    with col2:
        if st.button("Confirm & save", width="stretch", type="primary", key="att_confirm"):
            try:
                written = save_attendance_session(final, teacher_id=st.session_state.teacher_data["teacher_id"])
            except DatabaseError as exc:
                st.error(str(exc))
                return
            st.session_state.attendance_images = []
            st.session_state.voice_attendance_results = None
            st.session_state.flash = (
                "Attendance saved." if written else "This session was already saved, so nothing new was added."
            )
            st.rerun()


@st.dialog("Attendance report", width="large")
def attendance_result_dialog(df, logs, summary: str = ""):
    if summary:
        st.caption(summary)
    show_attendance_result(df, logs)
