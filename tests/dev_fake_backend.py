"""DEV/TEST ONLY: run the real app against an in-memory database seeded with demo data.

    streamlit run tests/dev_fake_backend.py

Demo teacher login: username `demo`, password `demo-password`.
Never use in production; data is lost when the process stops.
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database import config, db  # noqa: E402
from tests.fake_supabase import FakeSupabase  # noqa: E402

if getattr(config, "_client_override", None) is None:
    config.set_client_for_testing(FakeSupabase())
    db.create_teacher("demo", "demo-password", "Demo Teacher")
    t = db.teacher_login("demo", "demo-password")["teacher_id"]
    math = db.create_subject("MATH101", "Mathematics", "A", t)[0]["subject_id"]
    phys = db.create_subject("PHY201", "Physics", "B", t)[0]["subject_id"]
    ids = [db.create_student(n, [float(i)] * 128)[0]["student_id"] for i, n in enumerate(["Aisha Khan", "Ben Ortiz", "Chen Wei", "Dana Lee"])]
    for s in ids:
        db.enroll_student_to_subject(s, math)
    for s in ids[:2]:
        db.enroll_student_to_subject(s, phys)
    for day, absent in (("2026-09-01", {1}), ("2026-09-08", {2, 3}), ("2026-09-15", set())):
        db.save_attendance_session([
            {"student_id": s, "subject_id": math, "timestamp": f"{day}T09:00:00+00:00", "is_present": i not in absent}
            for i, s in enumerate(ids)
        ])
    db.save_attendance_session([
        {"student_id": s, "subject_id": phys, "timestamp": "2026-09-10T11:00:00+00:00", "is_present": i == 0}
        for i, s in enumerate(ids[:2])
    ])

runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
