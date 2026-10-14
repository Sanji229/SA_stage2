-- Migration 003: mid-semester marks. ADDITIVE ONLY. Safe on an existing database.
-- Requires migration 002 is NOT needed; requires the base tables from schema.sql.

create table if not exists assessments (
  assessment_id  bigint generated always as identity primary key,
  subject_id     bigint not null references subjects(subject_id) on delete cascade,
  name           text not null check (length(btrim(name)) > 0),          -- e.g. 'Mid-Semester 1'
  max_marks      numeric(7,2) not null check (max_marks > 0),
  assessed_on    date,
  published      boolean not null default false,
  published_at   timestamptz,
  created_by     bigint references teachers(teacher_id) on delete set null,
  created_at     timestamptz not null default now(),
  unique (subject_id, name)
);

create table if not exists marks (
  mark_id        bigint generated always as identity primary key,
  assessment_id  bigint not null references assessments(assessment_id) on delete cascade,
  student_id     bigint not null references students(student_id) on delete cascade,
  obtained       numeric(7,2) not null check (obtained >= 0),
  updated_by     bigint references teachers(teacher_id) on delete set null,
  updated_at     timestamptz not null default now(),
  unique (assessment_id, student_id)                                      -- one mark per student per assessment
);
create index if not exists marks_student_idx on marks(student_id);

create table if not exists marks_audit (
  audit_id       bigint generated always as identity primary key,
  assessment_id  bigint not null,
  student_id     bigint not null,
  action         text not null,                                            -- insert | update | delete
  old_obtained   numeric(7,2),
  new_obtained   numeric(7,2),
  changed_by     bigint,
  changed_at     timestamptz not null default now()
);
create index if not exists marks_audit_assessment_idx on marks_audit(assessment_id, changed_at);

-- Rules the database enforces even if application code is bypassed ---------------------------
create or replace function marks_enforce_rules() returns trigger language plpgsql as $$
declare mx numeric; subj bigint;
begin
  select max_marks, subject_id into mx, subj from assessments where assessment_id = new.assessment_id;
  if new.obtained > mx then
    raise exception 'marks (%) exceed the maximum (%) for this assessment', new.obtained, mx;
  end if;
  if not exists (select 1 from subject_students where subject_id = subj and student_id = new.student_id) then
    raise exception 'student % is not enrolled in the subject of this assessment', new.student_id;
  end if;
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists marks_rules on marks;
create trigger marks_rules before insert or update on marks for each row execute function marks_enforce_rules();

create or replace function marks_write_audit() returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    insert into marks_audit(assessment_id, student_id, action, old_obtained, changed_by) values (old.assessment_id, old.student_id, 'delete', old.obtained, old.updated_by);
  elsif tg_op = 'INSERT' then
    insert into marks_audit(assessment_id, student_id, action, new_obtained, changed_by) values (new.assessment_id, new.student_id, 'insert', new.obtained, new.updated_by);
  elsif new.obtained is distinct from old.obtained then
    insert into marks_audit(assessment_id, student_id, action, old_obtained, new_obtained, changed_by) values (new.assessment_id, new.student_id, 'update', old.obtained, new.obtained, new.updated_by);
  end if;
  return null;
end $$;
drop trigger if exists marks_audit_trg on marks;
create trigger marks_audit_trg after insert or update or delete on marks for each row execute function marks_write_audit();

-- A maximum cannot be lowered below marks that already exist.
create or replace function assessments_guard_max() returns trigger language plpgsql as $$
begin
  if new.max_marks < old.max_marks and exists (select 1 from marks where assessment_id = new.assessment_id and obtained > new.max_marks) then
    raise exception 'cannot lower the maximum below existing marks';
  end if;
  return new;
end $$;
drop trigger if exists assessments_max_guard on assessments;
create trigger assessments_max_guard before update on assessments for each row execute function assessments_guard_max();

-- Row Level Security: enabled with NO policies => the public anon key can read/write nothing.
-- SmartAttend authenticates teachers/students itself and accesses the DB only with a server-side
-- key, so "teacher sees own subjects" and "student sees only own PUBLISHED marks" are enforced in
-- src/database/db.py. Per-user RLS policies would require moving to Supabase Auth (JWT) - see README.
alter table assessments  enable row level security;
alter table marks        enable row level security;
alter table marks_audit  enable row level security;
