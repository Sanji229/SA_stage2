-- Migration 002: attendance provenance + correction audit trail. ADDITIVE ONLY (no drops, no data changes).
-- Safe to run on an existing database. The app keeps working without it (legacy columns only),
-- but corrections require attendance_audit.

alter table attendance_logs add column if not exists source      text not null default 'auto'
  check (source in ('auto','manual','corrected'));   -- how the value was decided
alter table attendance_logs add column if not exists match_score real;                -- face distance / voice similarity
alter table attendance_logs add column if not exists method      text;                -- 'face' | 'voice'
alter table attendance_logs add column if not exists marked_by   bigint references teachers(teacher_id) on delete set null;

create table if not exists attendance_audit (
  audit_id           bigint generated always as identity primary key,
  subject_id         bigint not null references subjects(subject_id) on delete cascade,
  student_id         bigint not null references students(student_id) on delete cascade,
  session_timestamp  timestamptz not null,
  old_present        boolean not null,
  new_present        boolean not null,
  reason             text not null check (length(btrim(reason)) >= 3),
  changed_by         bigint not null references teachers(teacher_id),
  changed_at         timestamptz not null default now()
);
create index if not exists attendance_audit_subject_idx on attendance_audit(subject_id, session_timestamp);
alter table attendance_audit enable row level security;   -- no policies: server key only

-- Database-level guarantees (the application also checks these, but the DB is the final guard):
create unique index if not exists attendance_logs_session_student_uq on attendance_logs(subject_id, student_id, "timestamp");
create index if not exists subject_students_subject_idx on subject_students(subject_id);
