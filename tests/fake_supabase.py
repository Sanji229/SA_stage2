"""Minimal in-memory stand-in for the supabase-py client, for tests ONLY.

It implements just what src/database/db.py uses: select (with embedded
relations, count and !inner), insert, delete, eq, execute, unique constraints.
It is NOT a substitute for testing against a real Supabase project.
"""
from __future__ import annotations

import copy
import itertools

UNIQUE = {
    "assessments": [("subject_id", "name")],
    "marks": [("assessment_id", "student_id")],
    "teachers": [("username",)],
    "subjects": [("subject_code",)],
    "subject_students": [("student_id", "subject_id")],
    "attendance_logs": [("subject_id", "student_id", "timestamp")],
}
PK = {"assessments": "assessment_id", "marks": "mark_id", "attendance_audit": "audit_id", "teachers": "teacher_id", "students": "student_id", "subjects": "subject_id", "attendance_logs": "log_id"}
# table -> relation name -> (target table, local key, remote key, many?)
REL = {
    "marks": {"assessments": ("assessments", "assessment_id", "assessment_id", False), "students": ("students", "student_id", "student_id", False)},
    "assessments": {"subjects": ("subjects", "subject_id", "subject_id", False), "marks": ("marks", "assessment_id", "assessment_id", True)},
    "subject_students": {"students": ("students", "student_id", "student_id", False), "subjects": ("subjects", "subject_id", "subject_id", False)},
    "attendance_logs": {"students": ("students", "student_id", "student_id", False), "subjects": ("subjects", "subject_id", "subject_id", False)},
    "subjects": {"subject_students": ("subject_students", "subject_id", "subject_id", True), "attendance_logs": ("attendance_logs", "subject_id", "subject_id", True)},
}


class APIError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class Result:
    def __init__(self, data):
        self.data = data


class FakeSupabase:
    def __init__(self):
        self.tables = {n: [] for n in ["teachers", "students", "subjects", "subject_students", "attendance_logs",
                                       "assessments", "marks", "attendance_audit", "marks_audit"]}
        self.missing_columns: dict[str, set] = {}  # table -> columns that "do not exist yet" (simulates an un-migrated DB)
        self._ids = {n: itertools.count(1) for n in self.tables}

    def table(self, name):
        return Query(self, name)


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.cols, self.payload, self.filters = "select", "*", None, []

    def select(self, cols="*"):
        self.op, self.cols = "select", cols
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload, self.on_conflict = "upsert", payload, on_conflict
        return self

    def in_(self, col, vals):
        self.filters.append((col, ("__in__", list(vals))))
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    # ------------------------------------------------------------------
    def execute(self):
        rows = self.db.tables[self.name]
        if self.op in ("insert", "upsert", "update"):
            bad = self.db.missing_columns.get(self.name, set())
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            for it in items:
                for c in it:
                    if c in bad:
                        raise APIError(f"Could not find the '{c}' column of '{self.name}' in the schema cache", code="PGRST204")
        if self.op == "update":
            hit = [r for r in rows if self._ok(r)]
            for r in hit:
                r.update(self.payload)
            return Result(copy.deepcopy(hit))
        if self.op == "upsert":
            keys = [k.strip() for k in (self.on_conflict or "").split(",") if k.strip()]
            batch = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in batch:  # all-or-nothing is not needed here: validated before the call
                existing = next((r for r in rows if keys and all(r.get(k) == item.get(k) for k in keys)), None)
                if existing:
                    existing.update(item); out.append(existing)
                else:
                    row = dict(item)
                    if self.name in PK:
                        row[PK[self.name]] = next(self.db._ids.setdefault(self.name, itertools.count(1)))
                    rows.append(row); out.append(row)
            return Result(copy.deepcopy(out))
        if self.op == "insert":
            return Result(self._insert(rows))
        if self.op == "delete":
            keep, gone = [], []
            for r in rows:
                (gone if self._ok(r) else keep).append(r)
            self.db.tables[self.name][:] = keep
            return Result(copy.deepcopy(gone))
        return Result(self._select(rows))

    def _ok(self, r):
        for c, v in self.filters:
            if isinstance(v, tuple) and v and v[0] == "__in__":
                if r.get(c) not in v[1]:
                    return False
            elif r.get(c) != v:
                return False
        return True

    def _insert(self, rows):
        batch = self.payload if isinstance(self.payload, list) else [self.payload]
        new = []
        for item in batch:
            row = dict(item)
            self.db._ids.setdefault(self.name, itertools.count(1))
            for cols in UNIQUE.get(self.name, []):
                if any(all(r.get(c) == row.get(c) for c in cols) for r in rows + new):
                    raise APIError('duplicate key value violates unique constraint', code="23505")
            if self.name in PK:
                row[PK[self.name]] = next(self.db._ids[self.name])
            new.append(row)
        rows.extend(new)
        return copy.deepcopy(new)

    def _select(self, rows):
        local = [(c, v) for c, v in self.filters if "." not in c]
        remote = [(c, v) for c, v in self.filters if "." in c]
        out = []
        for r in rows:
            probe = Query(self.db, self.name); probe.filters = local
            if not probe._ok(r):
                continue
            row = self._embed(r)
            if remote:
                if not all((row.get(c.split(".")[0]) or {}).get(c.split(".")[1]) == v for c, v in remote):
                    continue
            out.append(self._project(row))
        return copy.deepcopy(out)

    def _embed(self, r):
        row = dict(r)
        for rel, (target, lk, rk, many) in REL.get(self.name, {}).items():
            if rel not in self.cols:
                continue
            matches = [t for t in self.db.tables[target] if t.get(rk) == r.get(lk)]
            if many:
                row[rel] = [{"count": len(matches)}] if f"{rel}(count)" in self.cols else matches
            else:
                row[rel] = matches[0] if matches else None
        return row

    def _project(self, row):
        # Only enforce column lists for plain (non-embedded) selects.
        if "(" in self.cols or self.cols.strip() == "*":
            return row
        wanted = [c.strip() for c in self.cols.split(",")]
        return {c: row.get(c) for c in wanted}
