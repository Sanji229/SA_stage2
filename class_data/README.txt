SmartAttend synthetic class dataset (60 records)

Contents:
- students.csv: 60 fictional names and corresponding photo filenames
- photos/: 60 cropped synthetic portrait tiles

Important limitations:
The photos were cropped from a generated contact sheet. Some faces may be repeated or visually similar, so this is useful for testing the CSV/import workflow and face detection, but NOT a trustworthy face-recognition accuracy benchmark. Use distinct identity images (and separate test captures) for accuracy evaluation. These are synthetic images, not real students.
Do not upload this demo dataset into a production attendance database.
