"""Landing page. Every call to action is a real link handled by app.py (?portal=...)."""
from __future__ import annotations

import streamlit as st

from src.ui.base_layout import brand_html, html, icon

T = "?portal=teacher"
TR = "?portal=teacher&mode=register"
S = "?portal=student"

_CSS = """
<style>
.block-container { max-width:100% !important; padding:0 !important; }
div[data-testid="stVerticalBlock"] { gap:0 !important; }
.lp-wrap { max-width:1120px; margin:0 auto; padding:0 1.25rem; }
.lp-nav { position:sticky; top:0; z-index:50; background:rgba(255,255,255,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--sa-border); }
.lp-nav .lp-wrap { display:flex; align-items:center; justify-content:space-between; height:68px; }
.lp-links { display:flex; gap:1.6rem; align-items:center; }
.lp-links a { color:var(--sa-muted); text-decoration:none; font-weight:500; }
.lp-links a:hover { color:var(--sa-primary); }
.lp-actions { display:flex; gap:.6rem; align-items:center; }
.lp-btn { display:inline-block; padding:.7rem 1.25rem; border-radius:12px; font-weight:600; text-decoration:none !important; border:1px solid var(--sa-border); color:var(--sa-ink) !important; background:#fff; transition:all .15s; }
.lp-btn:hover { border-color:var(--sa-primary); color:var(--sa-primary) !important; }
.lp-btn.primary { background:var(--sa-primary); color:#fff !important; border-color:var(--sa-primary); }
.lp-btn.primary:hover { background:var(--sa-primary-dark); box-shadow:0 8px 20px rgba(79,70,229,.3); transform:translateY(-1px); }
.lp-btn.lg { padding:.9rem 1.6rem; font-size:1.05rem; }
.lp-menu { display:none; }
.lp-menu summary { list-style:none; cursor:pointer; padding:.55rem .9rem; border:1px solid var(--sa-border); border-radius:10px; font-weight:600; }
.lp-menu nav { position:absolute; right:1rem; top:64px; background:#fff; border:1px solid var(--sa-border); border-radius:14px; padding:.75rem; display:flex; flex-direction:column; gap:.2rem; min-width:210px; box-shadow:0 12px 30px rgba(15,23,42,.12); }
.lp-menu nav a { padding:.6rem .8rem; color:var(--sa-ink); text-decoration:none; border-radius:8px; font-weight:500; }
.lp-menu nav a:hover { background:var(--sa-primary-soft); }
.lp-hero { background:radial-gradient(1200px 500px at 80% -10%, #E0E7FF 0%, transparent 60%), linear-gradient(180deg,#fff 0%, var(--sa-bg) 100%); padding:4.5rem 0 4rem; }
.lp-hero .lp-wrap { display:grid; grid-template-columns:1.1fr .9fr; gap:3rem; align-items:center; }
.lp-eyebrow { display:inline-block; background:var(--sa-primary-soft); color:var(--sa-primary-dark); font-weight:600; font-size:.85rem; padding:.3rem .8rem; border-radius:999px; }
.lp-hero h1 { font-size:3.2rem; line-height:1.08; font-weight:800; margin:1rem 0; }
.lp-hero h1 .hl { color:var(--sa-primary); }
.stApp .lp-lead { margin:0; font-size:1.15rem; color:var(--sa-muted); max-width:34rem; line-height:1.6; }
.lp-cta { display:flex; gap:.8rem; flex-wrap:wrap; margin-top:1.6rem; }
.stApp .lp-note { margin:1.2rem 0 0; color:var(--sa-muted); font-size:.9rem; }
.lp-preview { background:#fff; border:1px solid var(--sa-border); border-radius:20px; box-shadow:0 24px 60px rgba(79,70,229,.16); padding:1.1rem; animation:lp-float 6s ease-in-out infinite; }
@keyframes lp-float { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-6px); } }
.lp-pv-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:.7rem; font-weight:700; }
.lp-badge { font-size:.72rem; font-weight:600; background:#F1F5F9; color:var(--sa-muted); padding:.2rem .55rem; border-radius:999px; }
.lp-row { display:flex; justify-content:space-between; align-items:center; padding:.6rem .75rem; border-radius:10px; background:#F8FAFC; margin-bottom:.45rem; font-size:.95rem; }
.lp-ok { color:var(--sa-success); font-weight:600; } .lp-no { color:var(--sa-danger); font-weight:600; }
.lp-btn-fake { display:block; text-align:center; background:var(--sa-primary); color:#fff; padding:.65rem; border-radius:10px; font-weight:600; margin-top:.6rem; }
.lp-sec { padding:4.5rem 0; scroll-margin-top:70px; }
.lp-sec.alt { background:#fff; }
.lp-sec h2 { font-size:2.1rem; font-weight:800; text-align:center; margin:0 0 .6rem; }
.lp-sec .lp-sub { text-align:center; color:var(--sa-muted); max-width:40rem; margin:0 auto 2.5rem; font-size:1.05rem; line-height:1.6; }
.lp-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:1.1rem; }
.lp-card { background:#fff; border:1px solid var(--sa-border); border-radius:18px; padding:1.5rem; transition:transform .2s, box-shadow .2s; }
.lp-card:hover { transform:translateY(-3px); box-shadow:0 14px 34px rgba(15,23,42,.08); }
.lp-card h3 { font-size:1.1rem; margin:.9rem 0 .4rem; }
.lp-card p { color:var(--sa-muted); margin:0; line-height:1.55; }
.lp-ico { width:46px; height:46px; border-radius:12px; display:grid; place-items:center; background:var(--sa-primary-soft); color:var(--sa-primary); }
.lp-steps { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:1.1rem; counter-reset:step; }
.lp-step { position:relative; background:var(--sa-bg); border:1px solid var(--sa-border); border-radius:18px; padding:1.5rem 1.25rem; counter-increment:step; }
.lp-step::before { content:counter(step); display:grid; place-items:center; width:34px; height:34px; border-radius:50%; background:var(--sa-primary); color:#fff; font-weight:700; margin-bottom:.8rem; }
.lp-step h3 { margin:0 0 .35rem; font-size:1.05rem; } .lp-step p { margin:0; color:var(--sa-muted); line-height:1.5; }
.lp-final { background:linear-gradient(135deg,#4338CA,#4F46E5 60%,#6366F1); color:#fff; text-align:center; padding:4rem 1rem; }
.lp-final h2 { color:#fff; font-size:2.1rem; margin:0 0 .6rem; } .lp-final p { color:#E0E7FF; margin:0 0 1.5rem; }
.lp-final .lp-btn { background:#fff; color:var(--sa-primary-dark) !important; border-color:#fff; }
.lp-foot { background:#0F172A; color:#CBD5E1; padding:2.2rem 0; font-size:.92rem; }
.lp-foot .lp-wrap { display:flex; justify-content:space-between; flex-wrap:wrap; gap:1rem; align-items:center; }
.lp-foot a { color:#CBD5E1; text-decoration:none; margin-left:1.2rem; } .lp-foot a:hover { color:#fff; }
.lp-faq { max-width:800px; margin:0 auto; padding:0 1.25rem; }
div[data-testid="stExpander"] { max-width:800px; width:calc(100% - 2.5rem); margin:0 auto .6rem; }
@media (max-width:860px) {
  .lp-hero .lp-wrap { grid-template-columns:1fr; gap:2rem; } .lp-hero h1 { font-size:2.35rem; }
  .lp-links, .lp-actions .lp-btn.hide-sm { display:none; } .lp-menu { display:block; } .lp-sec { padding:3rem 0; }
}
</style>
"""

_FEATURES = [
    ("camera", "Photo attendance", "Upload or capture classroom photos. Faces are matched against students enrolled in the selected subject, and you review every result before it is saved."),
    ("mic", "Voice attendance", "Students can optionally enrol a short voice sample. Record the class saying “present” and SmartAttend matches each speaker."),
    ("link", "Join by code, link or QR", "Every subject gets a unique code. Students enrol by typing it, opening a join link, or scanning the QR code."),
    ("check", "Review before saving", "Nothing is recorded automatically. You confirm a clear present/absent table first, and saving the same session twice never creates duplicates."),
    ("chart", "Records and reports", "See attendance rate per subject and every session, filter by subject, and export a CSV of the detailed log."),
    ("users", "Student view", "Students sign in with their face and see the subjects they are enrolled in with their own attendance totals."),
]
_STEPS = [
    ("Create a subject", "Teachers register, then create a subject and share its code, link or QR."),
    ("Students enrol", "Students register once with a face photo (voice is optional) and join using the code."),
    ("Capture the class", "Add one or more classroom photos, or record audio, for the chosen subject."),
    ("Review and confirm", "Check the present/absent list, then confirm to save the session."),
    ("Track results", "Open the dashboard for session history, attendance rates and CSV export."),
]
_FAQ = [
    ("Does SmartAttend store photos or recordings?", "The application code does not save classroom photos, registration photos or audio recordings. They are processed in memory. What is stored is a numeric face embedding (and an optional voice embedding) per student, plus attendance records."),
    ("Is face data sensitive?", "Yes. Face and voice embeddings are biometric data. Get consent from students (and guardians where required) and check the rules that apply to your institution and region before using SmartAttend."),
    ("How accurate is recognition?", "It depends on lighting, image resolution and face angle. That is why results are always shown for review before they are saved, and a teacher can run several photos per session. The match threshold is configurable."),
    ("Can someone sign in with a photo of a student?", "Student sign-in uses face matching only and has no liveness check, so a printed photo could fool it. The student view is read-only, but treat this as a known limitation."),
    ("Do students need an account?", "Students register once with a face photo and a name. Teachers sign up with a username and password."),
]


def landing_page() -> None:
    html(_CSS)
    html(f"""
    <header class="lp-nav"><div class="lp-wrap">
      {brand_html(link=True)}
      <nav class="lp-links" aria-label="Primary">
        <a href="#top">Home</a><a href="#features">Features</a><a href="#how">How it works</a>
        <a href="#privacy">Privacy</a><a href="#faq">FAQ</a>
      </nav>
      <div class="lp-actions">
        <a class="lp-btn hide-sm" href="{T}" target="_self">Teacher login</a>
        <a class="lp-btn primary" href="{TR}" target="_self">Sign up</a>
        <details class="lp-menu"><summary aria-label="Open menu">Menu</summary><nav aria-label="Mobile">
          <a href="#features">Features</a><a href="#how">How it works</a><a href="#privacy">Privacy</a><a href="#faq">FAQ</a>
          <a href="{T}" target="_self">Teacher login</a><a href="{S}" target="_self">Student portal</a></nav></details>
      </div>
    </div></header>
    <section class="lp-hero" id="top"><div class="lp-wrap">
      <div>
        <span class="lp-eyebrow">AI-assisted classroom attendance</span>
        <h1>Take attendance from a <span class="hl">photo</span>, not a roll call.</h1>
        <p class="lp-lead">SmartAttend recognises enrolled students in classroom photos or voice recordings, lets you review the result, and keeps a clean attendance record for every subject.</p>
        <div class="lp-cta">
          <a class="lp-btn primary lg" href="{TR}" target="_self">Get started as a teacher</a>
          <a class="lp-btn lg" href="{S}" target="_self">Student portal</a>
        </div>
        <p class="lp-note">Free to run yourself · You review every result before it is saved</p>
      </div>
      <div class="lp-preview" role="img" aria-label="Illustration of the attendance review screen">
        <div class="lp-pv-head"><span>Review attendance</span><span class="lp-badge">Illustration · not real data</span></div>
        <div class="lp-row"><span>Student A</span><span class="lp-ok">Present · Photo 1</span></div>
        <div class="lp-row"><span>Student B</span><span class="lp-ok">Present · Photo 2</span></div>
        <div class="lp-row"><span>Student C</span><span class="lp-no">Absent</span></div>
        <div class="lp-btn-fake">Confirm &amp; Save</div>
      </div>
    </div></section>
    <section class="lp-sec alt" id="features"><div class="lp-wrap">
      <h2>Everything you need to run attendance</h2>
      <p class="lp-sub">Built around how a class actually works: subjects, enrolment, capture, review and records.</p>
      <div class="lp-grid">{''.join(f'<div class="lp-card"><div class="lp-ico">{icon(i)}</div><h3>{t}</h3><p>{d}</p></div>' for i, t, d in _FEATURES)}</div>
    </div></section>
    <section class="lp-sec" id="how"><div class="lp-wrap">
      <h2>How it works</h2><p class="lp-sub">From an empty class to a saved attendance record in five steps.</p>
      <div class="lp-steps">{''.join(f'<div class="lp-step"><h3>{t}</h3><p>{d}</p></div>' for t, d in _STEPS)}</div>
    </div></section>
    <section class="lp-sec alt" id="privacy"><div class="lp-wrap">
      <h2>Privacy and security, stated plainly</h2><p class="lp-sub">What SmartAttend does today, without overpromising.</p>
      <div class="lp-grid">
        <div class="lp-card"><div class="lp-ico">{icon('shield')}</div><h3>Embeddings, not images</h3><p>Photos and audio are processed in memory and not saved by the app. Only numeric embeddings and attendance rows are stored.</p></div>
        <div class="lp-card"><div class="lp-ico">{icon('shield')}</div><h3>Protected credentials</h3><p>Teacher passwords are hashed with bcrypt. Database keys stay on the server and are never sent to the browser.</p></div>
        <div class="lp-card"><div class="lp-ico">{icon('shield')}</div><h3>Teachers see their own classes</h3><p>Subjects and records are scoped to the signed-in teacher. Students only see their own enrolments and attendance.</p></div>
      </div>
    </div></section>
    <section class="lp-sec" id="faq" style="padding-bottom:1.5rem"><div class="lp-faq"><h2>Frequently asked questions</h2><p class="lp-sub">Straight answers, including the limitations.</p></div></section>
    """)
    for q, a in _FAQ:
        with st.expander(q):
            st.write(a)
    html('<div style="height:3.5rem"></div>')
    html(f"""
    <section class="lp-final"><h2>Ready to simplify attendance?</h2><p>Create a teacher account and set up your first subject in minutes.</p>
      <a class="lp-btn lg" href="{TR}" target="_self">Create teacher account</a></section>
    <footer class="lp-foot"><div class="lp-wrap"><div>© SmartAttend</div>
      <div><a href="#features">Features</a><a href="#how">How it works</a><a href="#faq">FAQ</a><a href="{T}" target="_self">Teacher login</a><a href="{S}" target="_self">Student portal</a></div></div></footer>
    """)
