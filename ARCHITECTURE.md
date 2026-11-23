# ICTAKPMS – Architecture (approved design)

```
Browser (React/Vite/Tailwind) ──► nginx (SPA + /api proxy) ──► Flask/gunicorn ──► MySQL 8
```

Backend layering: **routes** (thin: parse, authorise, serialise) → **services** (business rules, transactions)
→ **models**. Cross-cutting: `permissions/` (role + scope guards), `utils/` (envelope, errors, audit).
Storage will sit behind a `StorageBackend` interface (local now, S3-compatible later).

## Decisions
- Individual projects by default; teams optional via `project_students` (1..N).
- Mentor scope is batch-level (`batch_mentors`) with optional per-project override (`projects.mentor_id`).
- Domain leads are many-to-many (`domain_leads`) for co-leads and cross-domain grants.
- Project **stage** (state machine) is separate from the four weekly **reviews** (independent records).
- Progress weights (configurable): SRS 20 · GitHub 5 · Scrum 25 · Reviews 40 · Final sign-off 10.
- API docs: flask-smorest (OpenAPI at `/api/openapi.json`, UI at `/api/docs`).
- Out-of-scope resource access returns 404, not 403.

## ER diagram

```mermaid
erDiagram
    ROLES ||--o{ USERS : has
    USERS ||--o| STUDENTS : profile
    USERS ||--o| MENTORS : profile
    USERS ||--o{ DOMAIN_LEADS : leads
    DOMAINS ||--o{ DOMAIN_LEADS : "led by"
    ORGANISATIONAL_UNITS ||--o{ OU_CUSTOM_FIELDS : defines
    ORGANISATIONAL_UNITS ||--o{ BATCHES : owns
    DOMAINS ||--o{ BATCHES : "assigned to"
    BATCHES ||--o{ BATCH_OU_DETAILS : "field values"
    OU_CUSTOM_FIELDS ||--o{ BATCH_OU_DETAILS : for
    BATCHES ||--o{ STUDENTS : contains
    BATCHES ||--o{ BATCH_MENTORS : has
    MENTORS ||--o{ BATCH_MENTORS : assigned
    DOMAINS ||--o{ PROBLEM_STATEMENTS : categorises
    PROBLEM_STATEMENTS ||--o{ PROBLEM_STATEMENT_DATASETS : has
    PROBLEM_STATEMENTS ||--o{ PROBLEM_STATEMENT_DOCUMENTS : has
    BATCHES ||--o{ PROJECTS : hosts
    PROBLEM_STATEMENTS ||--o{ PROJECTS : "allocated as"
    MENTORS ||--o{ PROJECTS : "optional override"
    PROJECTS ||--o{ PROJECT_STUDENTS : team
    STUDENTS ||--o{ PROJECT_STUDENTS : member
    PROJECTS ||--o{ PROJECT_ASSIGNMENTS : history
    PROJECTS ||--o{ SRS_SUBMISSIONS : has
    SRS_SUBMISSIONS ||--o{ SRS_REVIEW_HISTORY : reviewed
    PROJECTS ||--o| PROJECT_GITHUB_REPOSITORIES : repo
    PROJECTS ||--o{ PROJECT_REVIEWS : "weeks 1-4"
    PROJECT_REVIEWS ||--o{ EVALUATION_CRITERIA : defines
    EVALUATION_CRITERIA ||--o| EVALUATION_SCORES : scored
    PROJECT_REVIEWS ||--o{ EVALUATION_REVISIONS : audited
    PROJECTS ||--|| SCRUM_BOARDS : has
    SCRUM_BOARDS ||--o{ SCRUM_TASKS : contains
    SCRUM_TASKS ||--o{ SCRUM_TASK_COMMENTS : has
    SCRUM_TASKS ||--o{ SCRUM_TASK_HISTORY : tracked
    PROJECTS ||--o{ PROJECT_LIFECYCLE_TRANSITIONS : stages
    PROJECTS ||--o{ PROJECT_ACTIVITY_LOGS : activity
    USERS ||--o{ NOTIFICATIONS : receives
    USERS ||--o{ IMPORT_JOBS : runs
    IMPORT_JOBS ||--o{ IMPORT_ERRORS : has
    USERS ||--o{ AUDIT_LOGS : performs
    USERS ||--o{ FILE_ATTACHMENTS : uploads
```

Additional tables beyond the original list: `system_settings`, `password_reset_tokens`,
`evaluation_revisions`, `evaluation_templates`, `project_lifecycle_transitions`.
