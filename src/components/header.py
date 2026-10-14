import streamlit as st

from src.ui.base_layout import brand_html, html


def header_dashboard():
    """Top bar for portal screens. Returns the right-hand column for actions.

    The brand is deliberately not a link here: a link would reload the page and
    end the signed-in session.
    """
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        html(brand_html(link=False))
    return right
