
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.config import get_supabase
from src.database import db

SUBJECT_CODE = "ML437T"
CSV_PATH = ROOT / "class_data" / "students_with_voice_embeddings.csv"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform enrollment. Without this flag, only preview.",
    )
    args = parser.parse_args()

    if not CSV_PATH.is_file():
        raise SystemExit(f"CSV not found: {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise SystemExit("CSV must contain a 'name' column.")
        names = list(dict.fromkeys(
            (row.get("name") or "").strip()
            for row in reader
            if (row.get("name") or "").strip()
        ))

    subject = db.get_subject_by_code(SUBJECT_CODE)
    if not subject:
        raise SystemExit(
            f"Subject {SUBJECT_CODE} was not found. "
            "Check the subject code in SmartAttend."
        )

    subject_id = int(subject["subject_id"])
    print(f"Subject: {subject['subject_code']} — {subject['name']}")
    print(f"Subject ID: {subject_id}")
    print(f"Unique names in CSV: {len(names)}")

    client = get_supabase()
    rows = (
        client.table("students")
        .select("student_id, name")
        .execute()
        .data or []
    )

    by_name = {}
    for row in rows:
        key = (row.get("name") or "").strip().casefold()
        if key:
            by_name.setdefault(key, []).append(int(row["student_id"]))

    ready = []
    skipped = []

    for name in names:
        matches = by_name.get(name.casefold(), [])

        if len(matches) == 0:
            skipped.append((name, "Student not found in database"))
            continue
        if len(matches) > 1:
            skipped.append((name, "Multiple students have this name; ambiguous"))
            continue

        student_id = matches[0]
        if db.is_enrolled(student_id, subject_id):
            skipped.append((name, "Already enrolled"))
            continue

        ready.append((name, student_id))

    print("\n========== ENROLLMENT PREVIEW ==========")
    print(f"Ready to enroll: {len(ready)}")
    print(f"Skipped:         {len(skipped)}")
    print(f"Mode:            {'COMMIT' if args.commit else 'DRY RUN'}")

    for name, student_id in ready:
        print(f"[READY] {name} (student_id={student_id})")

    for name, reason in skipped:
        print(f"[SKIP] {name}: {reason}")

    if not args.commit:
        print("\nDRY RUN ONLY: No enrollments were changed.")
        print("Review the preview, then rerun with --commit.")
        return

    enrolled = 0
    failed = 0

    for name, student_id in ready:
        try:
            if db.enroll_student_to_subject(student_id, subject_id):
                enrolled += 1
                print(f"[ENROLLED] {name}")
            else:
                print(f"[SKIP] {name}: Already enrolled")
        except Exception as exc:
            failed += 1
            print(f"[FAILED] {name}: {type(exc).__name__}: {exc}")

    print("\n========== FINAL SUMMARY ==========")
    print(f"New enrollments: {enrolled}")
    print(f"Skipped:         {len(skipped)}")
    print(f"Failed:          {failed}")
    print("Verify the enrollment count in SmartAttend or Supabase.")


if __name__ == "__main__":
    main()
