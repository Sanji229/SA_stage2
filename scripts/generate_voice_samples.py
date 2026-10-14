
import asyncio
import csv
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "class_data" / "students.csv"
VOICE_DIR = ROOT / "class_data" / "voices"
OUTPUT_CSV = CSV_PATH.with_name("students_with_voice.csv")

# Voice IDs from the available Edge-TTS voice list.
# Some IDs repeat; duplicate IDs are not distinct synthetic speakers.
VOICES = [
    "en-IN-NeerjaNeural", "en-IN-PrabhatNeural",
    "en-US-AriaNeural", "en-US-GuyNeural",
    "en-US-JennyNeural", "en-US-RogerNeural",
    "en-US-MichelleNeural", "en-US-SteffanNeural",
    "en-US-AvaNeural", "en-US-AndrewNeural",
    "en-US-EmmaNeural", "en-US-BrianNeural",
    "en-GB-LibbyNeural", "en-GB-RyanNeural",
    "en-GB-SoniaNeural", "en-GB-ThomasNeural",
    "en-AU-NatashaNeural", "en-AU-WilliamMultilingualNeural",
    "en-CA-ClaraNeural", "en-CA-LiamNeural",
    "en-IE-EmilyNeural", "en-IE-ConnorNeural",
    "en-NZ-MollyNeural", "en-NZ-MitchellNeural",
    "en-ZA-LeahNeural", "en-ZA-LukeNeural",
    "en-SG-LunaNeural", "en-SG-WayneNeural",
    "en-PH-RosaNeural", "en-PH-JamesNeural",
    "en-KE-AsiliaNeural", "en-KE-ChilembaNeural",
    "en-NG-EzinneNeural", "en-NG-AbeoNeural",
    "en-TZ-ImaniNeural", "en-TZ-ElimuNeural",
    "en-HK-YanNeural", "en-HK-SamNeural",
    "en-GB-MaisieNeural", "en-US-AnaNeural",
    "en-US-EricNeural", "en-US-ChristopherNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-AvaMultilingualNeural",
    "en-IN-NeerjaExpressiveNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-ElizabethNeural", "en-US-JacobNeural",
    "en-GB-OliverNeural", "en-GB-MiaNeural",
    "en-AU-AnnetteNeural", "en-AU-CarlyNeural",
    "en-CA-AmandaNeural", "en-CA-JoeyNeural",
    "en-IE-ConnorNeural", "en-NZ-MitchellNeural",
    "en-ZA-LukeNeural", "en-SG-WayneNeural",
]

RETRIES = 3
RETRY_DELAY_SECONDS = 5
TEXT = "Hello, I am present for attendance today."


async def generate_one(output_path: Path, voice: str) -> bool:
    """Generate one audio file, retrying temporary errors."""
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing file: {output_path.name}")
        return True

    # Remove a zero-byte/incomplete file before retrying.
    if output_path.exists():
        output_path.unlink()

    for attempt in range(1, RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(TEXT, voice)
            await communicate.save(str(output_path))

            if output_path.exists() and output_path.stat().st_size > 0:
                print(f"Generated: {output_path.name}")
                return True

            raise RuntimeError("Audio file was not created or is empty.")

        except Exception as exc:
            # Remove a partial file before the next attempt.
            if output_path.exists():
                output_path.unlink()

            print(
                f"Attempt {attempt}/{RETRIES} failed for "
                f"{output_path.name}: {exc}"
            )

            if attempt < RETRIES:
                delay = RETRY_DELAY_SECONDS * attempt
                print(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

    print(f"FAILED: {output_path.name}")
    return False


async def main():
    if not CSV_PATH.exists():
        sys.exit(f"Missing CSV: {CSV_PATH}")

    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    with CSV_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        students = list(csv.DictReader(file))

    if len(students) != 60:
        sys.exit(f"Expected 60 students, found {len(students)}.")

    if not students:
        sys.exit("The CSV contains no student records.")

    fields = list(students[0].keys())
    if "voice_audio" not in fields:
        fields.append("voice_audio")

    successful = 0
    failed = []

    for i, student in enumerate(students):
        voice = VOICES[i % len(VOICES)]
        filename = f"student_{i + 1:02d}.mp3"
        output_path = VOICE_DIR / filename

        print(
            f"\n[{i + 1}/{len(students)}] "
            f"{filename} | voice={voice}"
        )

        ok = await generate_one(output_path, voice)

        if ok:
            student["voice_audio"] = filename
            successful += 1
        else:
            student["voice_audio"] = ""
            failed.append(filename)

        # Brief pause between requests to reduce connection pressure.
        await asyncio.sleep(1)

    # Save the CSV even if some voices failed, so progress is retained.
    with OUTPUT_CSV.open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(students)

    print("\n========== SUMMARY ==========")
    print(f"Successful audio files: {successful}/{len(students)}")
    print(f"Failed audio files: {len(failed)}")
    print(f"Audio folder: {VOICE_DIR}")
    print(f"Updated CSV: {OUTPUT_CSV}")

    if failed:
        print("\nFiles still needing generation:")
        for filename in failed:
            print(f"  - {filename}")
        print("\nRun the script again to retry the missing files.")
    else:
        print("\nAll audio files are ready for the embedding step.")


if __name__ == "__main__":
    asyncio.run(main())
