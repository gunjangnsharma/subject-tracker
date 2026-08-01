# AGENTS.md — working on Subject Tracker

Entry point for any agent (or engineer) picking up this project. Read this first,
then the two docs it points to. Keep this file short; put detail in the docs.

## What this is

A Flask + SQLAlchemy + SQLite study-progress tracker: `Subject → Module → Chapter`
with per-user accounts, a date-derived daily/weekly plan with backlog rollover, an
activity-tracking charts dashboard, a light/dark theme, and JSON backup/restore.

## Read these (in order)

1. **[docs/BUILD_CONTEXT.md](docs/BUILD_CONTEXT.md)** — the single source of truth:
   full architecture (file-by-file), every business rule, routes, auth, theming,
   backup format, config/env vars, run instructions, decisions log. Detailed enough
   to regenerate the app from scratch.
2. **[docs/TEST_PLAN.md](docs/TEST_PLAN.md)** — every one of the 77 tests and what
   it checks, plus the fixtures.
3. **[README.md](README.md)** — quick start (local + LAN), admin creation, env vars.

## Run & test (from `subject-tracker/`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # local: http://127.0.0.1:5000  (open /register first)
HOST=0.0.0.0 python run.py    # LAN (also set SUBJECT_TRACKER_SECRET); see BUILD_CONTEXT §12
pytest                        # all 77 tests
```

## Architecture rules (do not break)

- **Layering, dependencies point inward:** `Routes → Services → Repositories → Models/DB`.
  Routes are thin (parse → call a service → render/redirect). Business rules live in
  services; SQL lives in repositories; pure math lives in `tracker/domain.py`, which
  imports **nothing** from Flask or SQLAlchemy.
- **User scoping is mandatory.** Services and data-access are constructed with the
  current `user_id`; `get()` enforces ownership (foreign id → None → 404). Never add
  a query that can return another user's data. New per-user tables scope through
  `Chapter → Module → Subject → user`.
- **Roll-ups are computed, never stored** (see `domain.Progress`). Don't persist totals.
- **Backlog is derived from dates** at read time — no cron, nothing "moved".
- **Dates:** `today`/`when` are injected into services for testability; only the
  routes call `date.today()`. Keep it that way so tests stay clock-independent.

## Workflow

- **Commit per feature milestone**, not per file. Each commit should build and have a
  **green test suite** (`pytest` — currently 77 passing). Don't commit red.
- **Add tests with the feature.** Match the existing style: unit tests for
  `domain.py`, integration tests for services against the in-memory DB, route/smoke
  tests via the Flask test client. Document each new test's purpose in TEST_PLAN.md.
- **Update the docs in the same change.** New rule/route/decision → BUILD_CONTEXT.md;
  new test → TEST_PLAN.md; new run/setup step → README.md. Docs must not drift.
- **Schema changes:** there are no migrations — dev data is disposable. Delete
  `subject_tracker.db` and let `create_all` rebuild it (note it in the change).
- Git commit message trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Gotchas (already learned — don't reintroduce)

- Body background must set `background-color` and `background-image` **separately**;
  a `var(--color)` inside the `background` shorthand is parsed as an image and the
  color is dropped (dark theme silently fails). See BUILD_CONTEXT §9.
- Never enable the Flask debugger (`DEBUG=1`) on a non-localhost bind — `run.py`
  already refuses this; keep it that way (the debugger allows remote code execution).
- Import (`/import`) is additive + atomic + verbatim; don't make it fabricate
  activity events or partially commit on error.
