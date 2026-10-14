import io
from urllib.parse import quote

import segno
import streamlit as st

from src.settings import get_setting


def build_join_url(subject_code: str) -> str | None:
    base = (get_setting("APP_BASE_URL") or "").rstrip("/")
    return f"{base}/?join-code={quote(subject_code)}" if base else None


@st.dialog("Share class")
def share_subject_dialog(subject_name, subject_code):
    st.subheader(subject_name)
    st.write("Students can join by typing this code after signing in:")
    st.code(subject_code, language="text")

    join_url = build_join_url(subject_code)
    if not join_url:
        st.info("Set `APP_BASE_URL` (your deployed app address) to also get a join link and QR code.")
        return
    out = io.BytesIO()
    segno.make(join_url).save(out, kind="png", scale=8, border=2)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Join link**")
        st.code(join_url, language="text")
    with c2:
        st.image(out.getvalue(), caption="Scan to join", width=200)
