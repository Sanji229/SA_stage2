-- SmartAttend database schema (Supabase / PostgreSQL)
--
-- NOTE: this file was INFERRED from the application code, because the original
-- repository did not include one. Compare it with your existing database before
-- running it. Every statement is idempotent (IF NOT EXISTS) and non-destructive.
-- Recommended: run against a copy / development project first.

create table if not exists teachers (
  teacher_id  bigint generated always as identity primary key,
  username    text not null unique,
  password    text not null,                 -- bcrypt hash
  name        text not null,
  created_at  timestamptz not null default now()
);

create table if not exists students (
  student_id       bigint generated always as identity primary key,
  name             text not null,
  face_embedding   jsonb,                    -- 128 floats (dlib)
  voice_embedding  jsonb,                    -- 256 floats (Resemblyzer), optional
  created_at       timestamptz not null default now()
);

create table if not exists subjects (
  subject_id    bigint generated always as identity primary key,
  subject_code  text not null unique,        -- stored upper-case, used to join
  name          text not null,
  section       text not null,
  teacher_id    bigint not null references teachers(teacher_id) on delete cascade,
  created_at    timestamptz not null default now()
);

create table if not exists subject_students (
  student_id  bigint not null references students(student_id) on delete cascade,
  subject_id  bigint not null references subjects(subject_id) on delete cascade,
  primary key (student_id, subject_id)       -- prevents duplicate enrolment
);

create table if not exists attendance_logs (
  log_id      bigint generated always as identity primary key,
  student_id  bigint not null references students(student_id) on delete cascade,
  subject_id  bigint not null references subjects(subject_id) on delete cascade,
  "timestamp" timestamptz not null,          -- one value per attendance session
  is_present  boolean not null,
  unique (subject_id, student_id, "timestamp")  -- prevents duplicate saves
);
create index if not exists attendance_logs_subject_idx on attendance_logs(subject_id, "timestamp");

-- ---------------------------------------------------------------------------
-- Row Level Security
-- SmartAttend authenticates users itself (not via Supabase Auth) and talks to
-- Supabase ONLY from the server using SUPABASE_KEY. Enable RLS and add NO
-- policies: the public anon key then cannot read or write anything, while the
-- server-side key (which bypasses RLS) keeps working. Authorisation (a teacher
-- only sees their own subjects, a student only their own data) is enforced in
-- src/database/db.py. Never put the server key in browser code.
-- ---------------------------------------------------------------------------
alter table teachers         enable row level security;
alter table students         enable row level security;
alter table subjects         enable row level security;
alter table subject_students enable row level security;
alter table attendance_logs  enable row level security;

-- If your existing "timestamp" column is `timestamp` (without time zone) the app
-- still works; new rows are written as UTC ISO-8601 strings.
