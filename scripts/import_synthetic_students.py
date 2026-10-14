
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Run this script from the project root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.config import get_supabase
from src.pipelines.face_pipeline import get_face_embeddings


CSV_PATH = ROOT / "class_data" / "students_with_voice_embeddings.csv"
PHOTO_DIR = ROOT / "class_data" / "photos"
VOICE_DIR = ROOT / "class_data" / "voices"


def read_embedding(value: str) -> list[float]:
    """Parse a JSON-encoded embedding and validate its values."""
    embedding = json.loads(value)

    if not isinstance(embedding, list) or not embedding:
        raise ValueError("Embedding must be a non-empty JSON array.")

    values = np.asarray(embedding, dtype=np.float64)

    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Embedding must contain finite numeric values.")

    return values.tolist()


def resolve_file(folder: Path, filename: str) -> Path:
    """Resolve a dataset filename while preventing paths outside its folder."""
    path = (folder / filename).resolve()

    if not path.is_relative_to(folder.resolve()):
        raise ValueError(f"Invalid file path: {filename}")

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    return path


def prepare_row(row: dict) -> dict:
    name = (row.get("name") or "").strip()
    photo_name = (row.get("photo") or "").strip()
    voice_name = (row.get("voice_audio") or "").strip()
    voice_value = (row.get("voice_embedding") or "").strip()

    if not name or not photo_name or not voice_name or not voice_value:
        raise ValueError("Missing name, photo, voice_audio, or voice_embedding.")

    photo_path = resolve_file(PHOTO_DIR, photo_name)
    # Confirm that the referenced audio file is present too.
    resolve_file(VOICE_DIR, voice_name)

    voice_embedding = read_embedding(voice_value)

    with Image.open(photo_path) as image:
        face_embeddings = get_face_embeddings(image.convert("RGB"))

    if len(face_embeddings) != 1:
        raise ValueError(
            f"Expected exactly one face in {photo_name}; "
            f"detected {len(face_embeddings)}. Review this photo manually."
        )

    face_embedding = np.asarray(
        face_embeddings[0], dtype=np.float64
    )

    if (
        face_embedding.shape != (128,)
        or not np.isfinite(face_embedding).all()
    ):
        raise ValueError("Face embedding must contain 128 finite numbers.")

    return {
        "name": name,
        "face_embedding": face_embedding.tolist(),
        "voice_embedding": voice_embedding,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safely import synthetic SmartAttend student profiles."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually insert validated rows. Without this flag, only preview.",
    )
    args = parser.parse_args()

    if not CSV_PATH.is_file():
        raise SystemExit(
            f"CSV not found: {CSV_PATH}\n"
            "Check that students_with_voice_embeddings.csv exists."
        )

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"name", "photo", "voice_audio", "voice_embedding"}

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SystemExit(
                f"CSV must contain these columns: {sorted(required)}\n"
                f"Found: {reader.fieldnames}"
            )

        source_rows = list(reader)

    print(f"Rows in CSV: {len(source_rows)}")
    print("Loading existing student names...")

    client = get_supabase()
    existing_rows = (
        client.table("students")
        .select("student_id, name")
        .execute()
        .data or []
    )

    existing_names = {
        (row.get("name") or "").strip().casefold()
        for row in existing_rows
    }

    seen_names = set()
    prepared = []
    rejected = []

    for line_number, row in enumerate(source_rows, start=2):
        name = (row.get("name") or "").strip()
        normalized_name = name.casefold()

        if not name:
            rejected.append((line_number, "Empty name"))
            continue

        if normalized_name in existing_names:
            rejected.append((line_number, f"Name already exists: {name}"))
            continue

        if normalized_name in seen_names:
            rejected.append((line_number, f"Duplicate name in CSV: {name}"))
            continue

        seen_names.add(normalized_name)

        try:
            student = prepare_row(row)
            prepared.append(student)
            print(f"[VALID] {name}")
        except Exception as exc:
            rejected.append((line_number, f"{name}: {exc}"))
            print(f"[REJECTED] CSV row {line_number}, {name}: {exc}")

    print("\n========== IMPORT SUMMARY ==========")
    print(f"Existing database records: {len(existing_rows)}")
    print(f"Validated for import:       {len(prepared)}")
    print(f"Rejected/skipped:           {len(rejected)}")
    print(f"Mode:                       {'COMMIT' if args.commit else 'DRY RUN'}")

    if rejected:
        print("\nRows needing attention:")
        for line_number, reason in rejected:
            print(f"  CSV row {line_number}: {reason}")

    if not args.commit:
        print(
            "\nDRY RUN ONLY: No student records were inserted.\n"
            "Review the summary before running with --commit."
        )
        return

    if not prepared:
        print("Nothing to insert.")
        return

    # Recheck names immediately before inserting to reduce race risks.
    latest_rows = (
        client.table("students")
        .select("name")
        .execute()
        .data or []
    )
    latest_names = {
        (row.get("name") or "").strip().casefold()
        for row in latest_rows
    }

    to_insert = [
        student for student in prepared
        if student["name"].casefold() not in latest_names
    ]

    if len(to_insert) != len(prepared):
        print(
            "STOPPED: At least one name appeared in the database "
            "after validation. Run a fresh dry run."
        )
        return

    inserted = 0

    for student in to_insert:
        try:
            result = (
                client.table("students")
                .insert(student)
                .execute()
            )
            if result.data:
                inserted += 1
                print(f"[INSERTED] {student['name']}")
            else:
                print(f"[UNCERTAIN] No returned row for {student['name']}")
        except Exception as exc:
            print(
                f"[FAILED] {student['name']}: {type(exc).__name__}: {exc}"
            )
            print(
                "Stopping further inserts. Check Supabase before retrying "
                "to avoid duplicate records."
            )
            break

    print(f"\nInsertions confirmed by returned rows: {inserted}")
    print("Check Supabase to verify the final record count.")


if __name__ == "__main__":
    main()
