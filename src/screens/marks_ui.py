"""Marks screens. All rules live in src/services/marks.py and src/database/db.py."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.database import db
from src.database.db import DatabaseError
from src.services import marks as svc
from src.ui.base_layout import empty_state, page_header


def teacher_marks_tab(teacher_id: int) -> None:
    page_header("Marks", "Create assessments, import or edit marks, then publish when ready. Students only see published marks.")
    subjects = db.get_teacher_subjects(teacher_id)
    if not subjects:
        empty_state("Create a subject first (Subjects tab).")
        return
    by_id = {s["subject_id"]: s for s in subjects}
    subject_id = st.selectbox("Subject", list(by_id), format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['subject_code']}", key="marks_subject")
    assessments = db.list_assessments(teacher_id, subject_id)

    with st.expander("Create a new assessment", expanded=not assessments):
        with st.form(f"new_assessment_{subject_id}", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            name = c1.text_input("Name", placeholder="Mid-Semester 1", max_chars=60)
            max_marks = c2.number_input("Maximum marks", min_value=1.0, max_value=1000.0, value=20.0, step=1.0)
            when = c3.date_input("Assessment date", value=date.today())
            if st.form_submit_button("Create assessment", type="primary"):
                try:
                    db.create_assessment(teacher_id, subject_id, name, max_marks, when)
                    st.session_state.flash = f"Assessment “{name.strip()}” created."
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))
    if not assessments:
        return

    a_by = {a["assessment_id"]: a for a in sorted(assessments, key=lambda a: a["name"])}
    aid = st.selectbox("Assessment", list(a_by), format_func=lambda i: f"{a_by[i]['name']} (max {a_by[i]['max_marks']:g})", key="marks_assessment")
    a = a_by[aid]
    published = bool(a["published"])
    st.markdown(f"**Status:** {'Published, visible to students' if published else 'Draft, hidden from students'}")
    with st.popover("Unpublish" if published else "Publish results", icon=":material/visibility:"):
        st.write("Students will no longer see these marks." if published else "Enrolled students will be able to see their own marks.")
        if st.button("Confirm", key=f"pub_{aid}", type="primary"):
            try:
                db.set_published(teacher_id, aid, not published)
            except DatabaseError as exc:
                st.error(str(exc))
            else:
                st.session_state.flash = "Results unpublished." if published else "Results published."
                st.rerun()

    enrolled = {s["student_id"]: s["name"] for s in db.get_enrolled_students(subject_id)}
    if not enrolled:
        st.info("No students are enrolled in this subject yet.")
        return
    t_upload, t_edit, t_export = st.tabs(["Import CSV", "Edit table", "Export & history"])
    with t_upload:
        _import_csv(teacher_id, aid, a, enrolled)
    with t_edit:
        _edit_table(teacher_id, aid, a, enrolled)
    with t_export:
        _export_and_audit(teacher_id, aid, a)


def _import_csv(teacher_id, aid, a, enrolled):
    st.download_button("Download CSV template", svc.template_csv(enrolled), file_name="marks_template.csv", mime="text/csv", icon=":material/download:")
    st.caption("Columns: student_id, name (optional, informational), marks. Students are matched by student_id.")
    up = st.file_uploader("Marks CSV", type=["csv"], key=f"marks_csv_{aid}")
    if not up:
        return
    preview = svc.parse_marks_csv(up.getvalue(), a["max_marks"], enrolled)
    if preview.fatal:
        st.error(preview.fatal)
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Valid rows", len(preview.rows))
    c2.metric("Rows with errors", len(preview.errors))
    c3.metric("Students without marks", len(preview.missing))
    if preview.errors:
        st.error("Fix these rows in your file and upload it again. Nothing has been saved.")
        st.dataframe([{"Row": e.row, "Student ID": e.student_id, "Problem": e.problem} for e in preview.errors], hide_index=True, width="stretch")
    for w in preview.warnings[:10]:
        st.warning(w)
    if preview.missing:
        st.caption("No marks for: " + ", ".join(n for _, n in preview.missing[:15]) + (" …" if len(preview.missing) > 15 else ""))
    if preview.rows:
        st.dataframe([{"Student": r["name"], "Marks": float(r["obtained"]), "%": svc.percentage(r["obtained"], a["max_marks"])} for r in preview.rows], hide_index=True, width="stretch")
    if st.button(f"Import {len(preview.rows)} marks", type="primary", disabled=not preview.can_commit, key=f"do_import_{aid}"):
        try:
            n = db.import_marks(teacher_id, aid, preview.rows)
        except DatabaseError as exc:
            st.error(f"{exc} Nothing was saved.")
            return
        st.session_state.flash = f"Imported {n} marks."
        st.rerun()


def _edit_table(teacher_id, aid, a, enrolled):
    current = {r["student_id"]: float(r["obtained"]) for r in db.get_marks(teacher_id, aid)}
    df = pd.DataFrame([{"ID": sid, "Student": nm, "Marks": current.get(sid)} for sid, nm in sorted(enrolled.items(), key=lambda kv: kv[1].lower())])
    edited = st.data_editor(
        df, hide_index=True, width="stretch", disabled=["ID", "Student"], key=f"marks_editor_{aid}",
        column_config={"ID": None, "Marks": st.column_config.NumberColumn(f"Marks (0 – {a['max_marks']:g})", min_value=0.0, max_value=float(a["max_marks"]), step=0.25)},
    )
    st.caption("Clearing a cell does not delete an existing mark. Every change is recorded in the history.")
    if st.button("Save changes", type="primary", key=f"save_marks_{aid}"):
        changes = [{"student_id": int(r["ID"]), "obtained": r["Marks"]} for _, r in edited.iterrows()
                   if pd.notna(r["Marks"]) and current.get(int(r["ID"])) != float(r["Marks"])]
        if not changes:
            st.info("No changes to save.")
            return
        try:
            n = db.import_marks(teacher_id, aid, changes)
        except DatabaseError as exc:
            st.error(f"{exc} Nothing was saved.")
            return
        st.session_state.flash = f"Saved {n} change(s)."
        st.rerun()


def _export_and_audit(teacher_id, aid, a):
    rows = db.get_marks(teacher_id, aid)
    if rows:
        st.download_button("Export marks (CSV)", svc.marks_to_csv(rows, a["max_marks"]), file_name=f"marks_{a['name'].replace(' ', '_')}.csv", mime="text/csv", icon=":material/download:")
    else:
        st.caption("No marks entered yet.")
    trail = db.get_marks_audit(teacher_id, aid)
    if trail:
        names = {r["student_id"]: r["name"] for r in rows}
        st.caption("Change history")
        st.dataframe([{"When": t.get("changed_at", ""), "Student": names.get(t["student_id"], t["student_id"]), "Action": t["action"],
                       "From": t.get("old_obtained"), "To": t.get("new_obtained")} for t in trail], hide_index=True, width="stretch")
    else:
        st.caption("Change history appears here (requires migration 003 triggers).")


# ----------------------------------------------------------------------------- student
def student_marks_section(student_id: int) -> None:
    st.subheader("Your marks")
    try:
        published = db.get_student_marks(student_id)
        pending = db.get_student_pending_assessments(student_id)
    except DatabaseError as exc:
        st.error(str(exc))
        return
    if not published and not pending:
        empty_state("No assessments have been set up for your subjects yet.")
        return
    if published:
        df = pd.DataFrame(published)
        df["Percentage"] = [svc.percentage(o, m) for o, m in zip(df["obtained"], df["max_marks"])]
        show = df.rename(columns={"subject": "Subject", "assessment": "Assessment", "obtained": "Obtained", "max_marks": "Out of"})
        st.dataframe(show[["Subject", "Assessment", "Obtained", "Out of", "Percentage"]], hide_index=True, width="stretch")
        chart = df.assign(Label=df["code"] + " · " + df["assessment"])[["Label", "Percentage"]]
        st.bar_chart(chart, x="Label", y="Percentage", color="#4F46E5")
    if pending:
        st.caption(f"{len(pending)} assessment(s) pending publication: " + ", ".join(sorted({p['assessment'] for p in pending})))
