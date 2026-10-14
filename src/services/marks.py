"""Marks business rules: CSV validation, percentages, safe export. Pure functions (no DB, no UI)."""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Mapping

MAX_BYTES = 1_000_000
MAX_ROWS = 5000
ID_HEADERS = ("student_id", "id", "studentid")
MARK_HEADERS = ("marks", "obtained", "score", "mark")


@dataclass
class RowError:
    row: int                 # 1-based spreadsheet row number (header is row 1)
    student_id: str
    problem: str


@dataclass
class ImportPreview:
    rows: list[dict] = field(default_factory=list)              # valid: student_id, name, obtained
    errors: list[RowError] = field(default_factory=list)        # block the import
    warnings: list[str] = field(default_factory=list)           # do not block
    missing: list[tuple[int, str]] = field(default_factory=list)  # enrolled but absent from the file
    fatal: str | None = None

    @property
    def can_commit(self) -> bool:
        return not self.fatal and not self.errors and bool(self.rows)


def _find(headers: list[str], options) -> str | None:
    norm = {h.strip().lower().replace(" ", "_"): h for h in headers}
    return next((norm[o] for o in options if o in norm), None)


def validate_mark(value, max_marks: float) -> tuple[Decimal | None, str | None]:
    """Return (value, None) or (None, reason). Used for CSV rows AND manual table edits."""
    text = str(value).strip() if value is not None else ""
    if text == "" or text.lower() == "nan":
        return None, "marks is blank"
    try:
        d = Decimal(text)
    except InvalidOperation:
        return None, f"“{text[:20]}” is not a number"
    if not d.is_finite() or (isinstance(value, float) and not math.isfinite(value)):
        return None, "marks must be a finite number"
    if d < 0:
        return None, "marks cannot be negative"
    if d > Decimal(str(max_marks)):
        return None, f"{d} exceeds the maximum of {max_marks}"
    return d.quantize(Decimal("0.01")), None


def parse_marks_csv(raw: bytes, max_marks: float, enrolled: Mapping[int, str]) -> ImportPreview:
    """Validate an uploaded CSV against the class list. Nothing is written here."""
    p = ImportPreview()
    if len(raw) > MAX_BYTES:
        p.fatal = "The file is larger than 1 MB."
        return p
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        p.fatal = "The file is not UTF-8 text. Export it as “CSV UTF-8”."
        return p
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        p.fatal = "The file is empty."
        return p
    id_col, mark_col = _find(reader.fieldnames, ID_HEADERS), _find(reader.fieldnames, MARK_HEADERS)
    name_col = _find(reader.fieldnames, ("name", "student_name"))
    if not id_col or not mark_col:
        p.fatal = "Header must contain a student_id column and a marks column (found: " + ", ".join(reader.fieldnames[:6]) + ")."
        return p

    seen: dict[int, int] = {}
    for n, rec in enumerate(reader, start=2):
        if n - 1 > MAX_ROWS:
            p.fatal = f"Too many rows (limit {MAX_ROWS})."
            return p
        raw_id = (rec.get(id_col) or "").strip()
        if not raw_id and not (rec.get(mark_col) or "").strip():
            continue  # fully blank line
        if not raw_id:
            p.errors.append(RowError(n, "", "missing student_id")); continue
        try:
            sid = int(raw_id)
        except ValueError:
            p.errors.append(RowError(n, raw_id, "student_id must be a whole number")); continue
        if sid not in enrolled:
            p.errors.append(RowError(n, raw_id, "this student is not enrolled in the subject")); continue
        if sid in seen:
            p.errors.append(RowError(n, raw_id, f"duplicate of row {seen[sid]}")); continue
        seen[sid] = n
        value, why = validate_mark(rec.get(mark_col), max_marks)
        if why == "marks is blank":
            p.warnings.append(f"Row {n}: {enrolled[sid]} has no marks and will be skipped.")
            continue
        if why:
            p.errors.append(RowError(n, raw_id, why)); continue
        if name_col and (rec.get(name_col) or "").strip() and rec[name_col].strip().lower() != enrolled[sid].lower():
            p.warnings.append(f"Row {n}: name “{rec[name_col].strip()}” differs from the enrolled name “{enrolled[sid]}” (matched by student_id).")
        p.rows.append({"student_id": sid, "name": enrolled[sid], "obtained": value})
    got = {r["student_id"] for r in p.rows}
    flagged = {int(e.student_id) for e in p.errors if e.student_id.isdigit()}  # already reported as errors
    p.missing = [(sid, nm) for sid, nm in sorted(enrolled.items()) if sid not in got and sid not in flagged]
    if not p.rows and not p.errors:
        p.fatal = "No marks were found in the file."
    return p


def percentage(obtained, max_marks) -> float | None:
    return None if not max_marks else round(100.0 * float(obtained) / float(max_marks), 1)


def csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection in exported text."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def marks_to_csv(rows: list[dict], max_marks) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["student_id", "name", "marks", "max_marks", "percentage"])
    for r in rows:
        w.writerow([r["student_id"], csv_safe(r["name"]), r["obtained"], max_marks, percentage(r["obtained"], max_marks)])
    return out.getvalue()


def template_csv(enrolled: Mapping[int, str]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["student_id", "name", "marks"])
    for sid, nm in sorted(enrolled.items()):
        w.writerow([sid, csv_safe(nm), ""])
    return out.getvalue()
