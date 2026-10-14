
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipelines.voice_pipeline import get_voice_embedding

DATA_DIR = ROOT / "class_data"
VOICE_DIR = DATA_DIR / "voices"
INPUT_CSV = DATA_DIR / "students_with_voice.csv"
OUTPUT_CSV = DATA_DIR / "students_with_voice_embeddings.csv"


def main():
    if not INPUT_CSV.exists():
        sys.exit(f"Missing input CSV: {INPUT_CSV}")

    with INPUT_CSV.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        students = list(csv.DictReader(f))

    if not students:
        sys.exit("The input CSV has no student records.")

    fields = list(students[0].keys())
    if "voice_embedding" not in fields:
        fields.append("voice_embedding")

    successful = 0
    failed = []

    for index, student in enumerate(students, start=1):
        filename = (student.get("voice_audio") or "").strip()

        if not filename:
            student["voice_embedding"] = ""
            failed.append((index, "No voice_audio filename"))
            print(f"[{index}/{len(students)}] Missing audio filename")
            continue

        # Prevent paths from escaping the voices folder.
        audio_path = (VOICE_DIR / filename).resolve()

        if audio_path.parent != VOICE_DIR.resolve():
            student["voice_embedding"] = ""
            failed.append((index, "Invalid audio path"))
            print(f"[{index}/{len(students)}] Invalid audio path")
            continue

        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            student["voice_embedding"] = ""
            failed.append((index, f"Missing/empty file: {filename}"))
            print(f"[{index}/{len(students)}] Missing audio: {filename}")
            continue

        try:
            print(
                f"[{index}/{len(students)}] "
                f"Processing {filename}..."
            )

            audio_bytes = audio_path.read_bytes()
            embedding = get_voice_embedding(audio_bytes)

            if embedding is None or len(embedding) == 0:
                raise ValueError("Embedding is empty")

            # Store the vector as JSON inside the CSV cell.
            student["voice_embedding"] = json.dumps(
                embedding, separators=(",", ":")
            )

            successful += 1
            print(f"  Success: {len(embedding)} embedding values")

        except Exception as exc:
            student["voice_embedding"] = ""
            failed.append((index, f"{filename}: {exc}"))
            print(f"  Failed: {exc}")

        # Save progress after each student, so interruptions lose
        # at most the current student's work.
        with OUTPUT_CSV.open(
            "w", encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(students)

    print("\n========== SUMMARY ==========")
    print(f"Students in CSV: {len(students)}")
    print(f"Embeddings generated: {successful}")
    print(f"Failed: {len(failed)}")
    print(f"Output: {OUTPUT_CSV}")

    if failed:
        print("\nFailures:")
        for student_number, reason in failed:
            print(f"Student row {student_number}: {reason}")
        print("\nFix the reported issue and rerun the script.")
    else:
        print("\nAll voice embeddings generated successfully.")


if __name__ == "__main__":
    main()
