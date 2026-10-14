# SmartAttend: status of every requested item

Legend: **V** fixed and verified (automated tests and/or browser run in a sandbox with an in-memory DB) ·
**R** implemented, needs real-world validation · **P** partially addressed · **N** not addressed (reason given)

| Area | Status | Evidence / note |
|---|---|---|
| Face threshold configurable, user's 0.45 and jitter 0 preserved | V | `src/settings.py`; defaults unchanged |
| Unknown faces never forced onto nearest student | V | `test_face_matching.py` (unknown, ambiguous, other-class) |
| Ambiguous / duplicate / other-class matches routed to teacher | V (logic) · R (real faces) | per-face statuses in `face_pipeline.py` |
| Threshold *validated* on labelled data | **N** | No real labelled multi-session data exists. `class_data/` is synthetic with near-identical faces (median nearest-other-identity distance 0.22), so it cannot tune a threshold. Framework ready: `scripts/evaluate_faces.py` |
| Margin (0.05 face / 0.05 voice) | R | Provisional defaults, untuned |
| Evaluation framework (identity-split FAR/FRR/precision/recall/coverage) | V | `evaluation/`, 6 tests; run on synthetic set (see README) |
| Group photo: per-face bbox/status, small-face flag, duplicate claims | V (logic, 2 real photos) · R | `test_face_real.py`, `test_face_matching.py` |
| Large-image performance | P | Images capped to 2000px; ~0.13 s/image measured on 424-px tiles only. No classroom-size profiling |
| Embedding cache invalidation | P | 30 s TTL + `clear_gallery_cache()` after registration. No biometric delete/re-enrol UI yet |
| Voice audio quality validation (empty/short/silent/clipped/noisy) | V | `test_voice_logic.py` (numpy only) |
| Voice ambiguity / unknown handling | V (logic) | embeddings are synthetic vectors in tests |
| Voice model accuracy, thresholds, VAD tuning | **N** | PyTorch/Resemblyzer could not be installed in the sandbox; no labelled recordings. **WebRTC VAD is not in this repo** (silence splitting uses `librosa.effects.split`) |
| Multimodal face+voice fusion | **N** | Needs paired labelled data to validate; modules kept separate so it can be added |
| Liveness / anti-spoofing (photo, replay) | **N** | No validated method added; speaker/face embeddings are NOT liveness. Teacher review is the only mitigation |
| Duplicate attendance prevented (app + DB unique) | V (app) · R (real DB) | `test_attendance_integrity.py`; migration 002 unique index |
| Server-side ownership / enrolment checks | V | same tests |
| Review table, manual vs auto vs corrected provenance | V | tests + browser |
| Audited corrections | V (app) · R (real DB) | requires migration 002 |
| Marks: assessments, CSV validation, atomic import, publish, student view | V (app, fake DB, browser) · R (real DB triggers) | `test_marks.py`; SQL triggers in migration 003 are **not executed** anywhere here |
| Marks match by institutional email | **N** | `students` has no email column; needs your decision (see below) |
| RLS | P | Enabled with no policies (server key only). Per-user policies need Supabase Auth: decision required |
| Logo + favicon + wordmark (light/dark), used in app | V | `assets/brand/` |
| Teacher dashboard: totals, sessions, trend, by-subject, at-risk | V | tests + browser. "Today's %", announcements, upcoming assessments: **N** |
| Student dashboard: attendance, marks, warnings | V | tests. Exam info/announcements: **N** |
| Timetable, announcements/notifications, bulk import UI, QR attendance | **N** | Deferred to keep this change reviewable |
| Biometric consent / deletion / retention workflow | **N** | Next priority after this change |
| Concurrency under real load | **N** | Only the DB unique index guards races; not load-tested |
