# AGENTS.md — working on Subject Tracker

Entry point for any agent (or engineer) picking up this project. Read this first,
then the two docs it points to. Keep this file short; put detail in the docs.

## What this is

A Flask + SQLAlchemy + SQLite study-progress tracker: `Subject → Module → Chapter`
with per-user accounts, a date-derived daily/weekly plan with backlog rollover, an
activity-tracking charts dashboard, a light/dark theme, and JSON backup/restore.
Chapters are reorderable within their module (▲/▼ buttons; `Chapter.position`).

## Read these (in order)

1. **[docs/BUILD_CONTEXT.md](docs/BUILD_CONTEXT.md)** — the single source of truth:
   full architecture (file-by-file), every business rule, routes, auth, theming,
   backup format, config/env vars, run instructions, decisions log. Detailed enough
   to regenerate the app from scratch.
2. **[docs/TEST_PLAN.md](docs/TEST_PLAN.md)** — every test and what it checks, plus
   the fixtures (the file states the current total).
3. **[README.md](README.md)** — quick start (local + LAN), admin creation, env vars.

## Run & test (from `subject-tracker/`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # dev: http://127.0.0.1:5000  (open /register first)
python scripts/seed_dev_data.py   # dummy accounts + sample data (student / boss)
HOST=0.0.0.0 python run.py    # LAN (also set SUBJECT_TRACKER_SECRET); see BUILD_CONTEXT §12
SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... python run.py   # prod (waitress)
pytest                        # the full test suite
```

Environments come from `SUBJECT_TRACKER_ENV` (`dev`/`prod`/`test`) via
`config.get_config`. The two runtime versions are **dev and prod** (`test` is
pytest-only — nothing serves it). Prod runs on waitress, disables the debugger, and
refuses the default secret. `wsgi.py` exposes the app for external WSGI servers.
Env-backed settings (`DATABASE_URL`, `SECRET_KEY`, `SESSION_COOKIE_SECURE`) are
declared `FROM_ENV` and resolved by `config.resolve_settings` inside `create_app` —
never read `os.environ` in a class body (it freezes the value at import; see
BUILD_CONTEXT §11).

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
  **green test suite** (`pytest`). Don't commit red.
- **Add tests with the feature.** Match the existing style: unit tests for
  `domain.py`, integration tests for services against the in-memory DB, route/smoke
  tests via the Flask test client. Document each new test's purpose in TEST_PLAN.md.
- **Update the docs in the same change.** New rule/route/decision → BUILD_CONTEXT.md;
  new test → TEST_PLAN.md; new run/setup step → README.md. Docs must not drift.
- **Schema changes:** there are no migrations, but `tracker/schema.py`
  (`ensure_columns`, run from `create_all`) adds **missing defaulted columns** to
  existing tables, so a new nullable/defaulted column needs no reset — add it to
  the model *and* to `_ADDED_COLUMNS`. Anything else (drops, type changes, new
  constraints) still means deleting `subject_tracker.db` and letting `create_all`
  rebuild it (note it in the change).
- Git commit message trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Gotchas (already learned — don't reintroduce)

- Body background must set `background-color` and `background-image` **separately**;
  a `var(--color)` inside the `background` shorthand is parsed as an image and the
  color is dropped (dark theme silently fails). See BUILD_CONTEXT §9.
- Never enable the Flask debugger (`DEBUG=1`) on a non-localhost bind — `run.py`
  already refuses this; keep it that way (the debugger allows remote code execution).
- Import (`/import`) is additive + atomic + verbatim; don't make it fabricate
  activity events or partially commit on error.
- **The no-back-dating rule is route-only.** `PlanningService.assign` and the backup
  importer still accept any date (historical/backlog data, restores). Only the plan
  route rejects past dates. Don't push that check down into the service.
- **Planning requires an explicit date.** Never re-introduce a "default to today"
  when the date is empty — that caused a real bug.
- **HTML responses are `Cache-Control: no-store`** (app factory `after_request`), so
  dynamic pages never show a stale view. Keep it; static assets stay cacheable.
- **Completion is edited only on the plan pages** (`/today`, `/week`) via the
  `completion_control` macro (Done checkbox + h/m inputs that AJAX-save on blur).
  The subject page is read-only (`completion_display`). Completing always dates the
  activity to `today`, never the planned day.
- **"Studied" time is the NET sum of a day's `minutes_delta`** (`domain.net_studied_minutes`),
  floored at 0 — never sum only the positive deltas. Doing that let Done/undone
  toggling add the chapter's duration on every click. The `ProgressEvent` log keeps
  both directions; the *aggregation* nets them. See BUILD_CONTEXT §5.5.
- **Unplanning removes the assignment only** — never the completed minutes or the
  activity events. "Planned by mistake" ≠ "didn't do the work"; conflating them
  rewrites study history.
- **Chapter order sorts by `(position, id)`, never `position` alone.** Rows written
  before the column existed all share position `0`; the `id` tiebreak keeps them in
  insertion order. A move **renumbers the whole module** rather than swapping two
  values — swapping two zeroes would be a silent no-op. Reordering is confined to
  one module: the swap partner is always a sibling.
- **Don't remove the SQLite `_TUNING_PRAGMAS`** (`database.py`). WAL is what stops a
  write from locking the whole file and freezing every other request; `synchronous=
  NORMAL` is what stops an fsync per commit on SD cards. Both were real Raspberry Pi
  bugs. Note WAL adds `-wal`/`-shm` sidecar files, so file-copy backups must use
  `sqlite3 ... ".backup"` — see BUILD_CONTEXT §11.1.
- **SQLite does not index foreign keys.** Any new FK or filtered column needs an
  explicit `Index(...)` in `models.py`; `schema.ensure_indexes` backfills it into
  already-deployed databases at startup.
