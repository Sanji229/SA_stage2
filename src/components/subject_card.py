from __future__ import annotations

from html import escape

import streamlit as st

from src.ui.base_layout import html


def subject_card(name, code, section, stats=None, footer_callback=None, progress: float | None = None):
    """Render a subject card. All user-supplied text is HTML-escaped."""
    stat_html = "".join(
        f'<span class="sa-stat">{escape(str(icon))} <b>{escape(str(value))}</b> {escape(str(label))}</span>'
        for icon, label, value in (stats or [])
    )
    bar = ""
    if progress is not None:
        pct = max(0.0, min(100.0, progress))
        bar = (
            f'<div class="sa-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{pct:.0f}" aria-label="Attendance rate"><span style="width:{pct:.0f}%"></span></div>'
        )
    html(
        f'<div class="sa-card"><h3>{escape(str(name))}</h3>'
        f'<div><span class="sa-chip">{escape(str(code))}</span> &nbsp;Section {escape(str(section))}</div>'
        f"<div>{stat_html}</div>{bar}</div>"
    )
    if footer_callback:
        footer_callback()
