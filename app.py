"""SmartAttend entry point.  Run with:  streamlit run app.py"""
import logging
from pathlib import Path

import streamlit as st

from src.database.config import ConfigError, get_supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

LOGO = Path(__file__).parent / "assets" / "brand" / "favicon-64.png"


def _config_error_screen(message: str) -> None:
    from src.ui.base_layout import style_base_layout

    style_base_layout()
    st.title("SmartAttend needs configuration")
    st.error(message)
    st.markdown(
        "1. Copy `.env.example` to `.env` **or** `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.\n"
        "2. Fill in `SUPABASE_URL` and `SUPABASE_KEY` (server-side key; never commit it).\n"
        "3. Run `supabase/schema.sql` in your Supabase SQL editor, then restart the app."
    )


def _apply_portal_param() -> None:
    """Landing-page links use ?portal=student|teacher[&mode=register]."""
    portal = st.query_params.get("portal")
    if portal in ("student", "teacher") and st.session_state.get("login_type") is None:
        st.session_state.login_type = portal
        if portal == "teacher" and st.query_params.get("mode") == "register":
            st.session_state.teacher_login_type = "register"
    if portal:
        st.query_params.pop("portal", None)
        st.query_params.pop("mode", None)


def main() -> None:
    st.set_page_config(
        page_title="SmartAttend – AI-assisted attendance",
        page_icon=str(LOGO) if LOGO.exists() else "✅",
        layout="wide",
    )
    st.session_state.setdefault("login_type", None)

    try:
        get_supabase()
    except ConfigError as exc:
        _config_error_screen(str(exc))
        return

    _apply_portal_param()

    # Imported here so a missing-config page never needs the ML stack.
    from src.components.dialog_auto_enroll import auto_enroll_dialog
    from src.screens.home_screen import home_screen
    from src.screens.student_screen import student_screen
    from src.screens.teacher_screen import teacher_screen

    join_code = st.query_params.get("join-code")
    if join_code and st.session_state.login_type is None:
        st.session_state.login_type = "student"

    match st.session_state.login_type:
        case "teacher":
            teacher_screen()
        case "student":
            student_screen()
            if join_code and "student_data" in st.session_state:
                auto_enroll_dialog(join_code)
        case _:
            home_screen()


main()
