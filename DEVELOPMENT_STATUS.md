# ICTAKPMS – Development Status

_Last updated: 2026-11-20_  ·  Current: Phase 8 complete

## Completed

### Phase 1 – Foundation
- Docker Compose (db, backend, frontend), `.env.example`, persistent volumes, internal network, health check.
- Flask app factory, config, extensions, centralised JSON error envelope, audit helper.
- All 38 tables as SQLAlchemy models + initial Alembic migration (applied and verified on MySQL 8).
- JWT auth: login, refresh, me, change password, forgot/reset password (hashed one-time tokens), lockout, rate limit.
- RBAC: `roles_required` (role read from DB per request) + data-scope guards (`permissions/scope.py`).
- Admin user list/create/activate endpoints (used for bootstrapping; full user management UI is Phase 2).
- CLI: `flask seed`, `flask create-admin`. Swagger UI at `/api/docs`.
- React shell: login, forgot/reset password, profile, change password, role layouts, role-guarded routes,
  Axios JWT interceptor with refresh.
- Tests: backend 22 passing, frontend 8 passing.

### Phase 2 – Organisation management
- OU CRUD + activate/deactivate; **configurable registration fields** per OU (scope batch/student; text, number,
  date, email, select; required/active flags). Seeded OU fields are ordinary rows the admin can edit.
- Domain CRUD, activate/deactivate, many-to-many domain leads, per-domain batch/student counts.
- Batch CRUD (OU immutable after creation), close/reopen, domain assignment, OU-specific details stored as rows
  (`batch_ou_details`), server-side search/filter/sort/pagination, role-scoped listing.
- Generic import engine (parse → validate → stage → preview → confirm) with Batch and Student importers:
  CSV + XLSX, required-column check, row-wise errors, duplicate detection (in file and in DB, case-insensitive),
  explicit "valid rows only" confirmation, formula-injection-safe error CSV, per-user job privacy, audit entry.
- Downloadable CSV/XLSX templates generated from the OU's current field configuration.
- Staff/user management: create admin/lead/mentor (mentor profile), student create, reset password (temp
  password shown once), activate/deactivate (self-deactivation blocked). Students get one-time temp passwords.
- UI: OUs (+fields modal, template downloads), Domains (+leads), Batches (list/filters/sort/pagination,
  dynamic form, bulk upload wizard), Students (list, add, bulk upload, credentials download), Users.
- Admin navigation: dedicated *Domain Leads* and *Mentors* pages (add/reset/deactivate), single *Bulk Upload* window
  (Batches | Students tabs, Excel/CSV or manual entry). Template and upload buttons are always enabled; the first OU
  is preselected and missing input is explained on click.
- Fixes: per-request user cache moved off `g`; validation errors flattened to `{field: message}`.
- Tests: backend 60 passing, frontend 19 passing; live E2E verified against MySQL in Docker.

### Phase 3 – Problem statement management
- Storage abstraction (`services/storage.py`): `StorageBackend` interface + `LocalStorage` (traversal-proof key
  resolution); S3 can be added behind `STORAGE_BACKEND` without touching routes/services.
- Secure uploads (`services/file_service.py`): per-category extension allow-list, size limits (dataset 50 MB,
  documents 25 MB), content sniffing (magic bytes / NUL check), random storage names, metadata in `file_attachments`.
- Problem statement CRUD with every required field, rich-text HTML sanitised server-side (bleach allow-list),
  immutable ID, activate/deactivate, search/filter/sort/pagination, domain-scoped (leads only see/edit own domains).
- Multiple datasets and reference documents per statement; authorised streamed downloads (`nosniff`, attachment),
  delete removes the stored object. View access also extends to mentors/students whose project uses the statement
  (`can_view_problem_statement`) – ready for Phase 4.
- Bulk upload reuses the import engine (templates CSV/XLSX, preview, row errors, duplicate IDs in file/DB, domain
  scope per row, valid-rows-only confirmation, error report). Datasets are attached separately, never in cells.
- UI (shared by admin `/admin/problem-statements/*` and lead `/lead/problem-statements/*`): list with filters,
  create/edit form with rich-text editors, attachment panels, read-only detail view, bulk upload.
- Tests: backend 83, frontend 33 passing; live E2E on MySQL/nginx incl. 12 MB upload round-trip.

### Phase 4 – Mentors, allocation & lifecycle
- **Lifecycle state machine** (`services/lifecycle.py`): table-driven transitions with roles, system-only SRS steps
  (driven by Phase 5), guards (all 4 reviews submitted + final sign-off before completion), timestamps for every
  transition, activity log, admin-only **reopen** (mandatory reason, audit log, notifications). Weekly reviews are
  independent records (not stages). Students cannot skip SRS approval or self-approve.
- **Mentor management:** assign / remove / reassign batch mentors (domain-checked, atomic reassign also moves
  project overrides), per-project mentor override, mentor workload (batches/projects), lead sees own-domain mentors.
- **Allocation:** one or many students per request, individual or team projects, all-or-nothing, one project per
  student, same-domain + active statement checks, start date → target end (+4 weeks), auto-created Scrum board,
  4 review slots with due dates, assignment history, change problem statement until SRS is submitted.
- Project list/detail/timeline APIs (role-scoped), progress % (configurable weights in `system_settings`),
  delayed detection (overdue reviews, SRS not approved after week 1, overdue tasks).
- **Notifications:** service + API (list, unread count, mark read/all) + bell with live unread badge and page.
  Triggers: batch assigned to domain (leads), mentor assigned (mentor, students), project allocated (students,
  mentor, leads), problem changed, mentor changed, project reopened.
- UI: My Batches, Batch detail (Students / Mentors / Projects tabs), Allocate page, Mentor workload, Projects list
  (admin/lead/mentor), shared Project view (next-step actions, timeline, reopen, mentor, board permission),
  Student "My Project", notification bell + page. Fixed the admin sidebar missing *Problem Statements*.
- Tests: backend 112, frontend 58 passing; live E2E on MySQL/nginx.

### Phase 5 – SRS management & GitHub
- **Submission** (`services/srs_service.py`): students of the project upload PDF/DOCX (≤ 15 MB, content-sniffed) with a
  description; allowed only in *SRS Preparation* / *Changes Requested*; every upload is a new **version** (history kept);
  advances the lifecycle to *SRS Submitted*; project row is locked to serialise concurrent submissions/reviews.
- **Review:** assigned mentors (or admin) can *start review*, *approve*, *request changes* or *reject*; comments are
  mandatory for reject / request changes; only the latest version can be decided, once. Rejected = changes requested
  (must resubmit). Students cannot approve; leads are read-only; unassigned mentors get 404.
- **Revision history:** each submission keeps its decisions (reviewer, remarks, timestamp); lifecycle transitions and
  activity log record every step; audit log entries for submit/decisions.
- **Implementation unlock:** approval moves the project to *SRS Approved*; only then can the student start
  implementation (enforced by the state machine). `srs_status`/`implementation_unlocked` exposed on project APIs.
- **Queue:** `/api/srs/queue` (mentor/lead/admin, scoped, oldest first); notifications to mentors on submission and to
  students on decisions.
- **GitHub:** students add/update one repository URL per project after SRS approval; strict validation (https
  github.com/owner/repo only; `.git`/trailing slash normalised; subpaths, other hosts, lookalike domains rejected);
  readable by mentor, lead, admin; counts toward progress.
- Authorised, streamed SRS downloads (shared `utils/files.py`).
- UI: Student *SRS Submission* + *GitHub Repository* pages, mentor *SRS Review* queue + review page (`/srs/:id`),
  lead/admin SRS status queue, SRS and GitHub cards inside the project view.
- Tests: backend 155, frontend 82 passing; live E2E incl. 10 MB upload through nginx.

### Phase 6 – Scrum management
- **Board:** five columns (Backlog, To Do, In Progress, In Review, Completed); tasks with title, description, priority
  (low/medium/high/critical), assignee (project members only), start/due date, creator, completion date, comments, history.
- **Permissions** (`services/scrum_service.board_permissions`, returned to the UI with a reason): project students create/
  edit/move/delete; mentors view + comment, and may *move* tasks only when the Domain Lead/admin enables
  `mentor_can_edit_board` (never create/edit/delete); leads read-only; admin read + comment; others 404.
  Board unlocks after SRS approval and becomes read-only when the project is completed.
- **Ordering & drag-and-drop:** server-side resequencing (`PATCH /scrum/tasks/:id/move` with column + index); UI uses native
  HTML5 drag & drop with optimistic update + rollback, plus a "move to" select on every card for keyboard/touch.
- **Rules:** delete only before work starts (Backlog/To Do; soft-delete keeps history); optimistic-concurrency `version` on edits;
  completion date set/cleared on move; overdue = past due and not completed (feeds project "delayed" + progress).
- **History & activity:** every create/update/assign/move/delete is recorded per task and in the project activity log;
  comments notify the other side; moving to *In Review* notifies mentors.
- **Monitoring:** `/api/scrum/overview` (mentor/lead/admin, scoped) + *Scrum Monitoring* pages with overdue filter.
- **Concurrency fix (found by live MySQL test):** reads inside lock sections are now locking reads (`FOR UPDATE`/`refresh(...,
  with_for_update=True)`) so parallel moves/creates (and SRS submit/review) cannot use a stale REPEATABLE READ snapshot.
- Tests: backend 201, frontend 109 passing; live E2E with 16 parallel creates + 16 parallel moves.

### Phase 7 – Weekly evaluation & final evaluation
- **Dynamic criteria** (`services/evaluation_service.py`): nothing is preconfigured. Mentors add/edit/remove criteria
  (name, max marks) per review until submission, or start from their own **templates** (CRUD + one-click *sample* templates
  matching the example in the brief – ordinary editable data, no code depends on them).
- **Scoring:** marks per criterion (+ remarks), validated (0 ≤ marks ≤ max, ≤ 20 criteria, unique names, decimals rounded
  to 2 places); automatic totals, percentage (unscored criteria count as 0), review-wise performance and overall project
  performance (submitted reviews only: total, percentage, average).
- **Feedback:** overall feedback (required to submit), strengths, improvements, recommendations, review date.
- **Workflow:** save draft → submit (all criteria scored + feedback). Students only ever see *submitted* evaluations;
  drafts/under-revision are hidden. Only the project's assigned mentor can evaluate (override mentor respected);
  Week 1 needs SRS preparation started, weeks 2–4 need implementation; completed projects are read-only.
- **Controlled modification:** submitted reviews are locked; mentor/admin can **reopen with a reason**, the previous state is
  snapshotted in `evaluation_revisions`, audit-logged, student notified; history viewable by mentor/lead/admin.
  Reopening a review blocks completion until resubmitted. Optimistic `version` check on saves.
- **Final evaluation:** mentor/admin sign-off (remarks, only in *Final Evaluation* stage with all 4 reviews submitted) is
  mandatory before the project can be completed; completion and sign-off notify students and leads.
- **Queue/monitoring:** `/api/reviews/queue` (week/status/overdue filters) for mentors and read-only for leads/admins.
- UI: evaluation editor with live totals, template apply, submit confirmation; read-only evaluation + audit history; student
  *Weekly Reviews* (scores, criteria, feedback, overall performance, final evaluation); *Evaluation Templates* page;
  queue pages; project page links.
- **Integration test:** `tests/lifecycle_flow.py` drives the complete 20-step lifecycle from the brief through the public API;
  it runs in pytest *and* live against Docker/MySQL (both passing).
- Fixed: timeline ordering was unstable on MySQL (1-second timestamp resolution) – now tie-broken by id.
- Tests: backend 251+, frontend 138 passing.

### Phase 8 – Dashboards, analytics & reports
- **One metrics engine** (`services/metrics_service.py`): progress, delay reasons, review/score/task metrics for many projects in
  5 grouped queries (asserted by a test); the single-project helpers delegate to it, so project page, dashboards and reports
  cannot disagree.
- **Role dashboards** (`GET /api/dashboard`, live data only): *Admin* (OUs, domains, batches, students, mentors, problem
  statements, in-progress / awaiting-SRS / pending-review / completed / delayed; OU, domain, stage, batch-progress, participation,
  mentor-workload, review-completion and average-score charts); *Domain Lead* (domain-scoped counts, mentor-wise review
  completion, SRS status, weekly evaluation status, Scrum completion, student progress); *Mentor* (queues, students requiring
  attention, nearing completion, Scrum, progress); *Student* (project, mentor, stage, progress, SRS, review scores, latest
  feedback, Scrum summary, GitHub, timeline – only published feedback).
- **Reports** (`/api/reports/<type>`): OU, domain, batch, student, mentor, weekly-evaluation, project-completion; role-scoped
  (admin all, lead own domain without OU report, mentor own projects), filterable, paginated JSON preview, **CSV and Excel export**
  of the full scoped result (formula-injection-safe, BOM for Excel, audit-logged).
- **Charts follow the data-viz rules:** validated reference palette (≤ 3 categorical series), legends for ≥ 2 series, direct value
  labels on single-series bars, hover tooltips, reserved status colours always paired with icon + label, an always-available
  *View as table* alternative and `role="img"` summaries. Dashboards/reports are lazy-loaded (Recharts out of the first paint).
- Reports/dashboards UI: *Reports* for admin/lead, *Project Reports* for mentors; the placeholder landing page was removed.
- Tests: backend 273, frontend 158 passing; verified live on MySQL after running the full lifecycle.

### Post-Phase-8 requests
- **Rename:** the app is now **ICTAKPMS** (sign-in screen, sidebar, browser title, API docs, README/docs).
- **Batch filter** for admins, Domain Leads and mentors: dashboards (`/api/dashboard?batch_id=`, counts and charts narrow to the batch,
  404 outside the user's scope) and the project, SRS, Scrum and weekly-evaluation lists (`BatchFilter` component).
- **Shareable student credentials:** CSV with name, login email, temporary password, registration no., phone, batch and login URL after
  bulk import and single-student creation; `POST /api/students/credentials` (admin) issues fresh temporary passwords for a batch's
  students who have not logged in yet (never touches students who set their own password; audited; passwords never stored in clear).
- Tests: backend 284, frontend 175 passing.

### Post-Phase-8 requests (round 2)
- **Renamed to ICTAKPMS** everywhere (UI, browser title, API docs, README/docs).
- **New colour scheme** (indigo-night sidebar, indigo primary, teal accent, lavender canvas, soft shadows) and **custom SVG artwork**:
  logo, two-panel sign-in with a dashboard illustration, dashboard welcome banners, empty-state illustrations. (No raster AI images were
  generated – this environment has no image-generation tool; `VITE_HERO_IMAGE` lets you plug in your own picture.) Chart palette is unchanged
  (validated, accessible).
- **Batch detailed report** (`GET /api/reports/batch-detailed/<batch_id>`, admin + Domain Lead of the batch's domain): Summary, Students,
  Weekly scores (marks, feedback, strengths, improvements, recommendations, per-student remark), Criteria scores; xlsx / csv sheet / json;
  only submitted scores are exported; audit-logged; formula-injection safe. UI: Reports page card, batch page and batch list buttons.
- **Scoring only by mentors** (verified for admin, lead, student, other mentors) and **Domain Lead can revert a submitted score to the
  mentor** (`reopen` now allowed for leads in scope; mentor notified with reason; revert note shown to the mentor; history kept).
- **Remarks for every student** while scoring: new table `review_student_remarks` (migration `d5e0e43910ee`), saved with draft/submit,
  validated against project members, frozen after submission, each student only sees their own, included in history snapshots and reports.

### Post-Phase-8 requests (round 3) – review-date approval
- A mentor assigns a review date freely the first time; once saved it is **locked** (edits in place – including via submit – are refused).
  Changing it needs a **date-change request** (new date ≥ today, reason ≥ 5 chars, one pending request per review, only while the review is
  not submitted) that the project's **Domain Lead** approves or rejects (reject needs a reason); an administrator can decide as a fallback.
- New table `review_date_requests` (migration `c12a80f8359a`), endpoints under `/api/reviews/<id>/date-requests` and
  `/api/review-date-requests` (+ `/decision`, `/cancel`), audit-logged, mentors can withdraw, concurrent decisions are serialised.
- Notifications: lead on request; mentor on decision; students when a new date is approved. Students see the scheduled date on their review cards.
- UI: locked date field + *Request date change* dialog + pending banner/withdraw in the evaluation editor; **Date Approvals** page for leads/admin
  (approve / reject with note), **Date Requests** for mentors; lead dashboard tile *Date changes to approve*.
- Tests: backend 321, frontend 217 passing; verified live on MySQL.

## Pending
Phase 9 as per roadmap (problem statements → allocation/lifecycle evaluations →
notifications/hardening).

## Known issues / notes
- Sidebar intentionally lists only implemented pages; entries are added per phase.
- Password-reset email is logged, not sent (SMTP mailer to be added).
- Temporary passwords are returned once in API responses (import confirm, user/student create, reset); never stored in clear.
- Domain leads/mentors cannot yet browse batches in the UI (their pages arrive in Phase 4); the API is already scoped.
- Tests run on SQLite; MySQL-specific behaviour is verified via migration + smoke tests in Docker.
- Host port 8080 may be occupied on some machines; change `APP_PORT`.

## Next
Phase 9: scheduler for due/overdue notifications, audit-log viewer, security review, performance pass, Docker/production hardening, final docs.
- Rich-text editor uses `document.execCommand` (deprecated but universally supported); swap for TipTap if richer editing is needed.
- Uploaded files are not virus-scanned (hook point: `file_service.save_upload`).
- Deleting/cancelling an allocated project is not supported yet (use *Change problem* or admin reopen).
- Notification delivery is poll-based (60 s); no push/websocket.
- Final evaluation sign-off (needed to complete a project) arrives with Phase 7.
- Pending-review/"deadline approaching" notifications need a scheduler (Phase 9).
- The SRS "first week" deadline is advisory: late submissions are allowed but the project is flagged delayed.
- GitHub can only be added after SRS approval (matches the workflow); relax in `srs_service.set_github` if needed.
- Drag & drop uses native HTML5 events (no extra dependency); the per-card select is the accessible/touch alternative. Swap in @dnd-kit if richer touch drag is required.
- Concurrency-sensitive code paths are only exercised for real on MySQL; SQLite tests cannot reproduce lock/snapshot behaviour (verified live).
- Reviews have no relationship attribute on `Project`; they are queried by `project_id` (kept simple, indexed).
- "Weekly review due" / "deadline approaching" notifications still need the Phase 9 scheduler.
- Charts were verified through component tests and table views; I have not reviewed the rendered charts in a browser. Dark mode is not implemented (light theme only).
- Dashboard/report queries are computed on demand (no caching); fine for institute scale, add caching/materialised views if data grows into the tens of thousands of projects.
