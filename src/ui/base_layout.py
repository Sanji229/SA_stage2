"""SmartAttend design system: tokens, global CSS and small HTML helpers."""
from __future__ import annotations

import textwrap
from pathlib import Path

import streamlit as st

# ------------------------------------------------------------------ design tokens
COLORS = {
    "primary": "#4F46E5",
    "primary_dark": "#4338CA",
    "primary_soft": "#EEF0FF",
    "ink": "#0F172A",
    "muted": "#475569",
    "bg": "#F5F6FB",
    "card": "#FFFFFF",
    "border": "#E2E8F0",
    "success": "#15803D",
    "danger": "#B91C1C",
    "accent": "#0D9488",
}

ICONS = {  # Feather-style 24x24 stroke icons
    "camera": '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    "mic": '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "check": '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
}


def icon(name: str, size: int = 22) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'
    )


def html(markup: str) -> None:
    """Render raw HTML. Dedents and drops blank lines (a blank line ends a Markdown HTML block)."""
    cleaned = "\n".join(l for l in textwrap.dedent(markup).splitlines() if l.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


_BASE_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {{
  --sa-primary:{COLORS['primary']}; --sa-primary-dark:{COLORS['primary_dark']}; --sa-primary-soft:{COLORS['primary_soft']};
  --sa-ink:{COLORS['ink']}; --sa-muted:{COLORS['muted']}; --sa-bg:{COLORS['bg']}; --sa-card:{COLORS['card']};
  --sa-border:{COLORS['border']}; --sa-success:{COLORS['success']}; --sa-danger:{COLORS['danger']}; --sa-accent:{COLORS['accent']};
}}
html {{ scroll-behavior:smooth; }}
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4
  {{ font-family:'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }}
.stApp {{ background:var(--sa-bg); color:var(--sa-ink); }}
#MainMenu, footer {{ visibility:hidden; }}
header[data-testid="stHeader"] {{ display:none; }}
.block-container {{ max-width:1120px; padding:1.5rem 1.25rem 3rem; }}
h1, h2, h3 {{ letter-spacing:-0.02em; color:var(--sa-ink); }}
a {{ color:var(--sa-primary); }}
[data-testid="stHeaderActionElements"] {{ display:none !important; }}

/* Accessible focus ring on every interactive element */
a:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible,
[role="tab"]:focus-visible, [role="radio"]:focus-visible, summary:focus-visible {{
  outline:3px solid #818CF8 !important; outline-offset:2px !important; }}

/* Buttons */
.stButton > button, .stDownloadButton > button, button[data-testid^="stBaseButton"] {{
  border-radius:12px; font-weight:600; min-height:2.75rem; transition:background .15s, box-shadow .15s, transform .15s; }}
button[data-testid="stBaseButton-primary"] {{ background:var(--sa-primary); color:#fff; border:1px solid var(--sa-primary); }}
button[data-testid="stBaseButton-primary"]:hover {{ background:var(--sa-primary-dark); border-color:var(--sa-primary-dark); box-shadow:0 6px 16px rgba(79,70,229,.28); transform:translateY(-1px); }}
button[data-testid="stBaseButton-secondary"] {{ background:#fff; color:var(--sa-ink); border:1px solid var(--sa-border); }}
button[data-testid="stBaseButton-secondary"]:hover {{ border-color:var(--sa-primary); color:var(--sa-primary); }}
button[data-testid="stBaseButton-tertiary"] {{ color:var(--sa-muted); }}
button:disabled {{ opacity:.55; }}

/* Cards, metrics, inputs */
div[data-testid="stMetric"] {{ background:var(--sa-card); border:1px solid var(--sa-border); border-radius:16px; padding:1rem 1.1rem; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
div[data-testid="stMetricLabel"] p {{ color:var(--sa-muted); font-weight:500; }}
div[data-testid="stTextInput"] input {{ border-radius:10px; }}
div[data-testid="stExpander"] {{ background:var(--sa-card); border:1px solid var(--sa-border); border-radius:14px; }}
div[data-testid="stDataFrame"] {{ border:1px solid var(--sa-border); border-radius:12px; overflow:hidden; }}

/* App chrome */
.stApp a.sa-brand, .stApp a.sa-brand:hover {{ text-decoration:none; color:var(--sa-ink); }}
.sa-brand {{ display:flex; align-items:center; gap:.65rem; font-weight:800; font-size:1.35rem; color:var(--sa-ink); text-decoration:none; }}
.sa-brand img, .sa-brand svg {{ width:36px; height:36px; }}
.stApp h1.sa-page-title {{ margin:.25rem 0 .1rem; padding:0; font-size:1.75rem; line-height:1.2; font-weight:800; }}
.stApp h3 {{ font-size:1.2rem; font-weight:700; }}
.sa-sub {{ color:var(--sa-muted); margin:0 0 1rem; }}
.sa-card {{ background:var(--sa-card); border:1px solid var(--sa-border); border-radius:16px; padding:1.1rem 1.25rem; margin-bottom:.9rem; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
.sa-card h3 {{ margin:0 0 .25rem; font-size:1.15rem; }}
.sa-chip {{ display:inline-block; background:var(--sa-primary-soft); color:var(--sa-primary-dark); padding:.1rem .55rem; border-radius:999px; font-size:.8rem; font-weight:600; }}
.sa-stat {{ display:inline-block; background:#F1F5F9; border-radius:10px; padding:.25rem .65rem; margin:.35rem .4rem 0 0; font-size:.88rem; color:var(--sa-ink); }}
.sa-bar {{ height:8px; background:#E2E8F0; border-radius:99px; overflow:hidden; margin-top:.6rem; }}
.sa-bar > span {{ display:block; height:100%; background:var(--sa-accent); }}
.sa-empty {{ text-align:center; color:var(--sa-muted); border:1.5px dashed var(--sa-border); border-radius:16px; padding:2rem 1rem; background:#fff; }}
.sa-footer {{ text-align:center; color:var(--sa-muted); font-size:.85rem; margin-top:2.5rem; }}
@media (max-width:640px) {{ .block-container {{ padding:1rem .75rem 2rem; }} .stApp h1.sa-page-title {{ font-size:1.45rem; }} }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; scroll-behavior:auto !important; animation:none !important; }} }}
</style>
"""


def style_base_layout() -> None:
    html(_BASE_CSS)


_SYMBOL = None


def _logo_symbol() -> str:
    """Inline the real logo asset (assets/brand/logo-symbol.svg) so it scales crisply."""
    global _SYMBOL
    if _SYMBOL is None:
        path = Path(__file__).resolve().parents[2] / "assets" / "brand" / "logo-symbol.svg"
        svg = path.read_text(encoding="utf-8")
        _SYMBOL = " ".join(svg[svg.index("<svg"):].split())
    return _SYMBOL


def brand_html(link: bool = False) -> str:
    tag = "a" if link else "div"
    href = ' href="/" target="_self"' if link else ""
    return f'<{tag} class="sa-brand"{href}>{_logo_symbol()}<span>Smart<span style="color:var(--sa-primary)">Attend</span></span></{tag}>'


def page_header(title: str, subtitle: str = "") -> None:
    sub = f'<p class="sa-sub">{subtitle}</p>' if subtitle else ""
    html(f'<h1 class="sa-page-title">{title}</h1>{sub}')


def empty_state(message: str) -> None:
    html(f'<div class="sa-empty" role="status">{message}</div>')


def footer() -> None:
    html('<div class="sa-footer">SmartAttend · AI-assisted attendance for classrooms</div>')


def show_flash() -> None:
    """Show one-shot messages set by dialogs before a rerun."""
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    warn = st.session_state.pop("flash_warn", None)
    if warn:
        st.toast(warn, icon=":material/warning:")
