import streamlit as st

from src.components.dialog_attendance_results import show_attendance_result
from src.database.db import DatabaseError, get_enrolled_students
from src.pipelines.voice_pipeline import VoiceError, process_bulk_audio_detailed
from src.services.attendance import build_review_session, new_session_timestamp


@st.dialog("Voice attendance", width="large")
def voice_attendance_dialog(subject_id):
    st.write("Record the class saying “I am present”, then run the analysis.")
    audio = st.audio_input("Record classroom audio")

    if st.button("Analyze audio", width="stretch", type="primary"):
        if audio is None:
            st.warning("Record some audio first.")
            return
        try:
            with st.spinner("Processing audio…"):
                enrolled = get_enrolled_students(subject_id)
                if not enrolled:
                    st.warning("No students are enrolled in this subject.")
                    return
                candidates = {s["student_id"]: s["voice_embedding"] for s in enrolled if s.get("voice_embedding")}
                if not candidates:
                    st.error("None of the enrolled students has a voice profile.")
                    return
                result = process_bulk_audio_detailed(audio.getvalue(), candidates)
        except (VoiceError, DatabaseError) as exc:
            st.error(str(exc))
            return
        except ImportError:
            st.error("Voice recognition is not installed on this server (see README: resemblyzer).")
            return
        for issue in (result.quality.issues if result.quality else []):
            st.warning(issue)
        present = {sid: f"Voice {score:.2f}" for sid, score in result.matched.items()}
        notes = {s["student_id"]: "No voice profile: mark manually if present" for s in enrolled if not s.get("voice_embedding")}
        for group in result.ambiguous:  # similar-sounding speakers: teacher decides
            for sid in group:
                notes[sid] = "Voice matched several students equally well"
        st.session_state.voice_attendance_results = build_review_session(
            enrolled, present, subject_id, new_session_timestamp(), scores=result.matched, review_notes=notes, method="voice"
        )

    if st.session_state.get("voice_attendance_results"):
        st.divider()
        df, logs = st.session_state.voice_attendance_results
        show_attendance_result(df, logs)
