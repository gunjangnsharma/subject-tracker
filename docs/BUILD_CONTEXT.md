# Subject Tracker — Build Context

> **Single source of truth** for *what* this app is, *why* every decision was made,
> and *how* to build, run and test it. This document is written so that another
> engineer (or agent) with no prior context can regenerate an equivalent app from
> scratch. If a detail matters, it is here.

Last updated: 2026-08-01

---

## 0. TL;DR for a regenerator

Build a **Flask + SQLAlchemy + SQLite** web app that tracks study progress across
`Subject → Module → Chapter`, with per-user accounts, a daily/weekly plan whose
**backlog is derived from dates**, an activity log powering a **charts dashboard**,
a **light/dark theme**, and **JSON export/import**. Layer it strictly
**Routes → Services → Repositories → Models**, keep all pure math in a Flask-free
`domain.py`, and cover every rule with pytest against an in-memory DB. Commit at
each milestone (see §14). Exact stack versions in §2.

---

## 1. Purpose & scope

A web app to track study progress. It answers two questions:

1. **How much is done and how much is left** — for every chapter, module, subject,
   and overall.
2. **What should I do today / this week** — a plan with **automatic rollover** of
   unfinished work into today's plan ("yesterday's backlog") and the week's plan
   ("weekly backlog"), each showing the chapter heading and its original date.

Secondary features layered on top: multi-user login with per-user isolation, an
admin overview, an activity-tracking dashboard with charts and animations, a
flashy dark theme, and JSON backup/restore.

**Non-goals:** real-time collaboration, mobile apps, production-grade hosting,
database migrations (dev data is disposable — see §12).

## 2. Tech stack (exact versions)

| Thing | Choice | Version |
|-------|--------|---------|
| Language | Python | 3.12 (works on 3.10+) |
| Web framework | Flask | 3.0.3 |
| ORM | SQLAlchemy | 2.0.32 (2.0 typed `Mapped[]` style) |
| Database | SQLite | stdlib (`sqlite3`), file `subject_tracker.db` |
| Password hashing | Werkzeug | ships with Flask (`generate/check_password_hash`) |
| Tests | pytest | 8.3.2 |
| Charts (client) | Chart.js | 4.4.3, **vendored** at `tracker/static/vendor/chart.umd.min.js` |
| Animations/theme JS | vanilla | `tracker/static/app.js` |

`requirements.txt` pins Flask, SQLAlchemy, pytest. Werkzeug arrives transitively
with Flask. There are **no other runtime dependencies** (auth is hand-rolled).

## 3. Where it lives

Isolated in its own folder `subject-tracker/` with its **own git repo**, so it does
not disturb the pre-existing Rust note-taking workspace it was created inside.

## 4. Domain model

```
User 1───* Subject 1───* Module 1───* Chapter 1───* PlanAssignment
                                              └───* ProgressEvent
```

### Entities

| Entity | Fields | Notes |
|--------|--------|-------|
| **User** | `id`, `username` (unique), `password_hash`, `role` (`user`\|`admin`) | Account. Passwords hashed with Werkzeug PBKDF2. `is_admin` property. |
| **Subject** | `id`, `user_id` (FK→users), `name` | Top-level study area, **owned by a user**. |
| **Module** | `id`, `subject_id` (FK→subjects), `name` | A unit inside a subject. |
| **Chapter** | `id`, `module_id` (FK→modules), `title`, `kind` (`video`\|`text`), `duration_minutes` (int), `completion` (int 0–10) | The atomic trackable item. |
| **PlanAssignment** | `id`, `chapter_id` (FK→chapters), `planned_date` (DATE) | "Do this chapter on this day." Week is **derived** from the date, not stored. |
| **ProgressEvent** | `id`, `chapter_id` (FK→chapters), `occurred_on` (DATE), `minutes_delta` (float) | Study-activity log entry: change in completed minutes on a day. |

**Cascades** (all `all, delete-orphan`): deleting a User deletes its Subjects →
Modules → Chapters → (PlanAssignments + ProgressEvents). Enforced both in ORM
relationships and with `ondelete="CASCADE"` on the FKs.

**Enums:** `CHAPTER_KINDS = ("video", "text")`, `USER_ROLES = ("user", "admin")`
(defined in `models.py`).

## 5. Core business rules

### 5.1 Duration
- Stored in **minutes** (integer). Displayed as **hours + minutes** everywhere:
  `domain.format_hm(minutes)` → `130 → "2h 10m"`, `120 → "2h"`, `30 → "30m"`,
  `0 → "0m"` (rounds to the nearest whole minute; completed minutes can be
  fractional). Exposed as the Jinja filter `hm` (`{{ minutes|hm }}`) and as
  `Progress.total_hm / completed_hm / remaining_hm`.
- `domain.minutes_to_hours` (decimal hours) survives **only** for numeric chart
  axes; chart tooltips convert back to h/m via `formatHM` in `app.js`.

### 5.2 Completion — the "1–10" metric
- `completion` is an integer **0–10** = tenths of the chapter done (`10`=finished, `5`=half, `0`=not started).
- **Completed minutes** = `duration_minutes * completion / 10`.
- Spec example: a 2-hour (120 min) video with 1 hour done → enter `5` → `120*5/10 = 60` min (50%).
- Input is **clamped** to 0–10 (`domain.clamp_completion`); a chapter is **done** when `completion == 10`.

### 5.3 Roll-ups (aggregation) — always computed, never stored
Derived live so they can't drift. Implemented as `domain.Progress` (a frozen
dataclass holding `total_minutes` + `completed_minutes`, with `remaining`,
`percent`, and `*_hours` properties; `Progress + Progress` sums them).
- **Chapter**: `completed = duration*completion/10`, `remaining = duration - completed`.
- **Module**: sum of its chapters. **Subject**: sum of its modules. **Overall**: sum of subjects.
- **Percent** = `completed / total * 100`, or `0` when total is 0 (no divide-by-zero).

### 5.4 Planning & backlog rollover — derived from dates, no scheduler

**One date per chapter.** A chapter can be planned on **at most one** date, so it
never appears twice (across the day view, the week view, or any backlog).
`PlanningService.assign` is an **upsert**: it deletes any existing assignment for
the chapter, then adds the new one — re-planning *moves* the chapter. Backup
import keeps only the first `plan_dates` entry per chapter. (Invariant maintained
in code; the service and importer are the only writers, so no DB unique
constraint is required.)

- **Today view** for date `T`:
  - *Today's plan* = assignments with `planned_date == T`.
  - *Backlog* = assignments with `planned_date < T` **and** chapter not done. Shown as "carried from <date>".
- **Week view — rolling 7-day window** (`PlanningService.rolling_plan(today)`):
  - Seven **day-groups** in chronological order from `today` to `today+6`, each
    holding the chapters planned for that exact day (empty days show "Nothing
    planned"). The window **rolls**: as each real day passes, a new day appears at
    the end, so you always see a full week ahead. `today` is highlighted.
  - *Overdue backlog* = assignments with `planned_date < today` **and** chapter not
    done (identical rule to the Today page's backlog).
  - Items planned **beyond** `today+6` are not shown until they enter the window.
- Because backlog is **computed on read**, finishing a chapter (`completion=10`)
  removes it from all backlogs automatically. Nothing is moved or deleted; **no cron**.

> Note: the dashboard's "This week's activity" **chart** stays a fixed Mon–Sun
> calendar week (retrospective activity via `domain.week_bounds`); only the `/week`
> **plan** page uses the rolling window. `week_bounds()` is still used by the chart.

### 5.5 Activity log
- Whenever `SubjectService.set_completion` changes completed minutes, it writes a
  `ProgressEvent(chapter_id, occurred_on=when or today, minutes_delta=Δ)`. A no-op
  change writes nothing; reducing completion writes a negative delta.
- `set_completion(chapter_id, completion, when=None)` — `when` is injectable so
  tests are clock-independent; the route passes nothing (defaults to today).

### 5.6 Dashboard aggregation
`DashboardService.build(today)` returns a `DashboardView` with:
- **overall** — `Progress` summed across the user's subjects (doughnut chart).
- **today** — `TodayStats(planned_count, done_count, backlog_count, studied_minutes)`.
  `studied_minutes` = sum of **positive** `minutes_delta` on `today`.
- **week** — `WeekStats(start, end, days[7])`; each `DayActivity(day, label, studied_minutes, planned_minutes)`
  where *studied* = positive deltas that day, *planned* = Σ durations of chapters assigned that day.

### 5.7 What decides "today" and "the week"
- **Server-side & automatic.** Every request calls Python `date.today()` (the
  **server machine's local date/timezone**) — never the client's clock, never a
  manual field. Week = Monday–Sunday via `domain.week_bounds()`.
- Backlog re-derives each request, so it self-corrects as real days pass.
- **Limitation:** `date.today()` is naive local time. Across timezones or on a
  cloud host (often UTC) "today" follows the server. To fix, replace `date.today()`
  in the routes with a timezone-aware date. Change `week_bounds()` for a non-Monday start.

## 6. Architecture (SOLID / layered) — complete file map

Dependencies point **inward**: `Routes → Services → Repositories → Models/DB`.
`domain.py` sits at the bottom and imports nothing from Flask/SQLAlchemy.

```
subject-tracker/
├── run.py                     Entry point; HOST/PORT/DEBUG env handling (see §11).
├── scripts/
│   └── squash_duplicate_plans.py   CLI for the one-date cleanup (see §12.5).
├── requirements.txt           Pinned deps.
├── README.md                  Quick start (points here).
├── .gitignore                 Ignores .venv, *.db, __pycache__, .DS_Store, etc.
├── docs/
│   ├── BUILD_CONTEXT.md        This file.
│   └── TEST_PLAN.md            Per-test purpose + strategy.
└── tracker/                   The Flask package.
    ├── __init__.py             App factory create_app(config): engine+session lifecycle
    │                           (g.session per request), load_logged_in_user → g.user,
    │                           `hours` Jinja filter, current_user template global,
    │                           registers all 6 blueprints.
    ├── config.py               Config (DATABASE_URL, SECRET_KEY, MAX_CONTENT_LENGTH) +
    │                           TestConfig (in-memory :memory: DB). Env-var driven.
    ├── database.py             Base(DeclarativeBase); Database(url) → engine + scoped
    │                           session; create_all(); remove(). sqlite check_same_thread=False.
    ├── models.py               ORM models User/Subject/Module/Chapter/PlanAssignment/
    │                           ProgressEvent + .progress/.is_done helpers; cascades; enums.
    ├── domain.py               PURE math: clamp_completion, minutes_to_hours,
    │                           completed_minutes, percent, is_done, week_bounds,
    │                           Progress dataclass, chapter_progress, sum_progress. No Flask/DB.
    ├── auth.py                 Session auth: login_user/logout_user/current_user,
    │                           load_logged_in_user (before_request), login_required,
    │                           admin_required. SESSION_KEY="user_id".
    ├── maintenance.py          One-off cleanups: squash_duplicate_plans (keeps the
    │                           most recent plan assignment per chapter).
    ├── repositories/           DATA ACCESS ONLY (the only layer touching the ORM).
    │   ├── user_repository.py       UserRepository(session): add/get/get_by_username/list_all.
    │   ├── subject_repository.py    SubjectRepository + ModuleRepository (session, user_id);
    │   │                            scoped by user; get() enforces ownership.
    │   ├── chapter_repository.py    ChapterRepository(session, user_id); ownership via Module→Subject.
    │   ├── plan_repository.py       PlanRepository(session, user_id); on_date/in_range/before,
    │   │                            all joined through Chapter→Module→Subject→user.
    │   └── activity_repository.py   ActivityRepository(session, user_id); on_date/between (joined scope).
    ├── services/               BUSINESS LOGIC; own the commit boundary.
    │   ├── auth_service.py          AuthService(session): register/authenticate/get/list_users.
    │   ├── subject_service.py       SubjectService(session, user_id): subject/module/chapter
    │   │                            CRUD, set_completion (logs activity), roll-ups via models.
    │   ├── planning_service.py      PlanningService(session, user_id): assign (ownership-guarded),
    │   │                            today_plan/week_plan → DayPlan/WeekPlan with PlannedItem.
    │   ├── dashboard_service.py     DashboardService(session, user_id): build(today)→DashboardView
    │   │                            (SubjectSummary, TodayStats, WeekStats, DayActivity).
    │   └── backup_service.py        BackupService(session, user_id): export_data()/import_data();
    │                                BackupError; ImportSummary. Format constants.
    ├── routes/                 HTTP CONTROLLERS (thin; parse → call service → render/redirect).
    │   ├── auth.py                  /register /login /logout.
    │   ├── dashboard.py             / (dashboard; builds charts JSON payload).
    │   ├── subjects.py              /subjects CRUD for subjects/modules/chapters/completion.
    │   │                            Blueprint before_request requires login.
    │   ├── planning.py              /today /week /chapters/<id>/plan. Login-gated.
    │   ├── admin.py                 /admin (admin_required); per-user progress overview.
    │   └── backup.py                /export (download) /import (upload). Login-gated.
    ├── templates/              Jinja2.
    │   ├── base.html                Layout: theme <head> script, nav (auth-aware + theme toggle),
    │   │                            flash messages, Chart.js + app.js includes, {% block scripts %}.
    │   ├── _macros.html             progress_bar(p), kind_pill(kind), plan_list(items, show_from).
    │   ├── dashboard.html           Hero doughnut, stat cards, subject+week charts (data via JSON).
    │   ├── subjects.html            Subject list + add form + backup (import/export) bar.
    │   ├── subject_detail.html      Modules/chapters tables, completion & plan forms.
    │   ├── today.html / week.html   Plan + backlog lists via plan_list macro.
    │   ├── admin.html               All-users progress table.
    │   └── auth/login.html, auth/register.html   Auth cards.
    └── static/
        ├── style.css            All styling; CSS variables for light + :root[data-theme="dark"].
        ├── app.js               Theme toggle+persist, count-up, reveal, Chart.js rendering.
        └── vendor/chart.umd.min.js   Chart.js 4.4.3 (vendored; no runtime CDN).
```

**Why this shape (SOLID):** routes handle HTTP; services hold rules + transactions;
repos hold SQL; `domain.py` holds math with zero framework deps (so it's unit-tested
in isolation). New features add a repo+service without touching existing ones.

## 7. Routes reference

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET/POST | `/register` | public | Create account (auto-login on success). |
| GET/POST | `/login` | public | Sign in. |
| POST | `/logout` | any | Sign out (clears session). |
| GET | `/` | login | **Dashboard**: overall + today + week charts. |
| GET | `/subjects` | login | Manage subjects (list, add, import/export). |
| POST | `/subjects` | login | Add subject. |
| POST | `/subjects/<id>/delete` | login | Delete subject (cascades). |
| GET | `/subjects/<id>` | login | Subject detail: modules + chapters + roll-ups. |
| POST | `/subjects/<id>/modules` | login | Add module. |
| POST | `/modules/<id>/delete` | login | Delete module. |
| POST | `/modules/<id>/chapters` | login | Add chapter (title, kind, duration_minutes). |
| POST | `/chapters/<id>/completion` | login | Update completion 0–10 (logs activity). |
| POST | `/chapters/<id>/delete` | login | Delete chapter. |
| POST | `/chapters/<id>/plan` | login | Assign chapter to a date (`planned_date`). |
| GET | `/today` | login | Today's plan + carried-over backlog. |
| GET | `/week` | login | Rolling 7-day plan (today..today+6) grouped by day + overdue backlog. |
| GET | `/admin` | admin | Overview of every user's progress (403 for non-admins). |
| GET | `/export` | login | Download the user's data as a JSON backup file. |
| POST | `/import` | login | Upload a JSON backup; **adds** its subjects to the account. |

Ownership: every `<id>` lookup is scoped to the logged-in user; a foreign id
returns **404** (via repository `get()` returning None), never another user's data.

## 8. Authentication & multi-user isolation

- **Session-based**, hand-rolled (no Flask-Login). Flask's signed cookie stores
  `user_id`; `load_logged_in_user` (app `before_request`) sets `g.user`. Guards:
  `login_required`, `admin_required` (403 via Werkzeug `Forbidden`). Login-only
  blueprints (`subjects`, `planning`, `backup`) also gate via a blueprint
  `before_request`.
- **Passwords** hashed with Werkzeug PBKDF2 (`generate_password_hash` /
  `check_password_hash`); min length 6 (`AuthService.MIN_PASSWORD_LEN`).
- **Isolation (critical security property):** every Subject has `user_id`. All
  repositories take the current `user_id` and scope queries to it; `get()` returns
  None for another user's row. Plans/activity scope by joining Chapter→Module→
  Subject→user. `PlanningService.assign` re-checks chapter ownership.
- **Roles / different views:** a `user` sees only their own dashboard; an `admin`
  additionally sees `/admin`. The Admin nav link is hidden for non-admins.

## 9. Theming (light / flashy dark)

- All colors are CSS custom properties in `:root`; `:root[data-theme="dark"]`
  overrides them with a neon/glow palette (gradient brand, glowing progress bars,
  stat-card glow, ambient radial-gradient background).
- A nav toggle (🌙/☀️) flips `data-theme` on `<html>` and saves it to `localStorage`
  (`app.js`). An inline script in `base.html <head>` applies the saved-or-system
  theme **before paint** to avoid a flash.
- Charts read colors from CSS variables (`getComputedStyle`) and are **destroyed +
  rebuilt on toggle** so they always match the theme.
- **Native controls follow the theme** via `color-scheme` (`light` on `:root`,
  `dark` on `:root[data-theme="dark"]`). Without this the `<input type="date">`
  calendar icon is a dark glyph on a dark field → invisible in dark mode.
- **Date fields open on click anywhere**: `app.js` calls `input.showPicker()` on
  click (natively only the small icon opens the calendar).
- **Gotcha (do not reintroduce):** set the body background with **separate**
  `background-color: var(--bg)` and `background-image: var(--bg-accent)`. A
  `var(--color)` inside the `background` shorthand is parsed as an *image* layer,
  leaving `background-color` transparent (so the dark bg silently fails). The light
  overlay uses `none`, not `transparent`, because `background-image` needs an image value.

## 10. JSON backup (export / import) — the standard format

Versioned document (`format: "subject-tracker-backup"`, `version: 1`):

```json
{
  "format": "subject-tracker-backup",
  "version": 1,
  "exported_at": "<ISO-8601 UTC>",
  "user": {"username": "<name>"},
  "subjects": [
    {"name": "...", "modules": [
      {"name": "...", "chapters": [
        {"title": "...", "kind": "video|text", "duration_minutes": 120,
         "completion": 10, "plan_dates": ["YYYY-MM-DD"],   // 0 or 1 (one date per chapter)
         "activity": [{"occurred_on": "YYYY-MM-DD", "minutes_delta": 120.0}]}
      ]}
    ]}
  ]
}
```

- **Export** (`GET /export`) scopes to the current user; streams JSON as a download
  `subject-tracker-<user>-<date>.json`.
- **Import** (`POST /import`) is **additive** (adds the file's subjects; existing
  data untouched) and **atomic** (any validation error rolls the whole thing back).
  It writes completion / plan dates / activity **verbatim** via repositories, so it
  never fabricates new activity events (re-export == original).
- **Validation** (`BackupError`) rejects wrong `format`/`version`, bad `kind`,
  non-integer numbers, and malformed dates, each with a clear message.
  `MAX_CONTENT_LENGTH` (8 MB) caps upload size.
- For a clean **restore** (replace, not merge): delete existing subjects first,
  then import. (A dedicated replace-mode is a possible future addition.)

## 11. Configuration & environment variables

Read in `config.py` and `run.py`:

| Variable | Default | Meaning |
|----------|---------|---------|
| `SUBJECT_TRACKER_DB` | `sqlite:///<cwd>/subject_tracker.db` | SQLAlchemy DB URL. Tests use `:memory:` via `TestConfig`. |
| `SUBJECT_TRACKER_SECRET` | `dev-secret-change-me` | Flask `SECRET_KEY` for signed sessions. **Set a real one when exposed.** |
| `HOST` | `127.0.0.1` | Bind interface. `0.0.0.0` = reachable on the LAN. |
| `PORT` | `5000` | Listen port. |
| `DEBUG` | (off) | `1` enables reloader/debugger — **only honoured on localhost** (the Werkzeug debugger allows RCE and must never be network-reachable). |

`MAX_CONTENT_LENGTH = 8 MB` (fixed in config) caps uploads.

## 12. How to run — every path

All commands run from the `subject-tracker/` directory. First-time setup:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The SQLite file `subject_tracker.db` is created automatically on first run
(`create_all` at app startup). On first use, open `/register` to make an account.

### 12.1 Dev server (local machine only)
```bash
python run.py                         # http://127.0.0.1:5000  (localhost only)
```
Enable auto-reload/debugger while developing (localhost only, safe):
```bash
DEBUG=1 python run.py
```

### 12.2 LAN server (reach it from other devices on the same Wi-Fi)
```bash
HOST=0.0.0.0 SUBJECT_TRACKER_SECRET="$(python -c 'import secrets;print(secrets.token_hex(16))')" python run.py
```
Then from another device open `http://<this-machine-LAN-IP>:5000`
(find the IP with `ipconfig getifaddr en0` on macOS Wi-Fi).
Notes: macOS may prompt to allow incoming connections (Allow); the host machine
must stay awake and running; `DEBUG` is ignored on a non-localhost bind by design;
this is **plain HTTP** — fine on trusted Wi-Fi, not for the public internet
(use a tunnel/host with HTTPS for that).

### 12.3 Run the tests
```bash
pytest                # all 77 tests
pytest -q             # quiet
pytest tests/test_backup.py -v      # one file, verbose
```
Tests use a fresh in-memory SQLite DB per test (no touching the dev DB).

### 12.4 Create an admin (no UI for this)
`register` always makes a regular `user`. Promote/create an admin via a shell:
```bash
python - <<'PY'
from tracker import create_app
from tracker.services.auth_service import AuthService
app = create_app(); s = app.database.Session()
AuthService(s).register("boss", "secret123", role="admin")
print("admin 'boss' created")
PY
```

### 12.5 Squash duplicate plans (one-off cleanup)
Data created before the one-date-per-chapter rule may have a chapter planned on
several dates. Collapse them (keeps the most recent per chapter):
```bash
python scripts/squash_duplicate_plans.py --dry-run   # preview, no changes
python scripts/squash_duplicate_plans.py             # apply
```
Idempotent and respects `SUBJECT_TRACKER_DB`. Logic lives in
`tracker/maintenance.py` (`squash_duplicate_plans`).

### 12.6 Reset the database (schema change or clean slate)
There is **no migration tool**. Dev data is disposable — after a model change:
```bash
rm -f subject_tracker.db        # then start the server to recreate the schema
```
For durable data across schema changes, add Alembic (future work).

## 13. Security notes

- Auth prevents cross-user access (§8); foreign ids 404.
- Default `SECRET_KEY` is a known dev value — override via env before exposing.
- No HTTPS (dev server). Fine on localhost/trusted LAN; use a reverse proxy/tunnel
  with TLS for anything internet-facing.
- Werkzeug debugger is never enabled on a network bind (`run.py`).
- Upload size capped (`MAX_CONTENT_LENGTH`); import is validated + atomic.

## 14. Milestones (git history — replay in order)

Each milestone is a single commit:

1. **scaffold** — structure, docs, deps.
2. **core-domain** — models, DB, domain math, subject/module/chapter CRUD + roll-ups.
3. **planning** — daily/weekly plans + backlog rollover.
4. **ui** — app factory, routes, templates, styling.
5. **tests** — pytest suite (domain, roll-ups, CRUD, planning, routes).
6. **dashboard** — ProgressEvent activity log + charts dashboard + animations.
7. **auth** — multi-user accounts, per-user isolation, admin overview.
8. **serve** — configurable HOST/PORT/DEBUG for LAN access.
9. **backlog-display tests** — verify backlog carry-over shows the chapter heading.
10. **theme** — flashy dark theme with persisted toggle.
11. **backup** — JSON export/import.

## 15. Decisions & assumptions log (why, not just what)

- **Stack = Flask + SQLAlchemy + SQLite**: readable, minimal setup, maps cleanly to
  SOLID service/repository layers; SQLite needs no server. (User-confirmed.)
- **Completion = 10-point ratio of duration** (not raw minutes): matches the spec's
  2-hour→enter-5 example. (User-confirmed.)
- **Roll-ups computed, never stored**: eliminates drift; cheap at this scale.
- **Backlog derived from dates, not moved**: idempotent, needs no scheduler, and
  finishing a chapter clears it everywhere automatically.
- **One date per chapter**: `assign` is an upsert (re-planning moves the chapter),
  so a chapter never appears in more than one day/section. Enforced in the service
  + importer (they are the only writers) rather than a DB constraint, to avoid a
  migration and keep old-backup imports working.
- **Durations shown as "Xh Ym"** (not decimal hours): one formatter `format_hm`
  drives every text surface (filter, `Progress.*_hm`, JS count-up, chart tooltips).
  Decimal hours kept only for chart axes.
- **Week plan = rolling 7-day window** (today..today+6) grouped by day, chosen over
  a fixed Mon–Sun week so the user always sees the week *ahead* (per their T+7
  request). The dashboard activity chart stays Mon–Sun.
- **Week = Monday–Sunday (ISO)**; "today"/"week" use the **server's** `date.today()`
  (local tz), recomputed per request. Timezone-awareness deferred (§5.7).
- **Activity log (ProgressEvent)** added because current completion can't say *when*
  work happened — required for real "today/this week activity". `when` is injectable
  for deterministic tests.
- **Charts: Chart.js, vendored locally** (not CDN) so the app is self-contained and
  works offline; chart data passed as a small JSON payload; colors read from CSS vars.
- **Auth hand-rolled** (session cookie + Werkzeug hashing) instead of Flask-Login:
  no extra dependency, full control, trivially testable with the test client.
- **Per-user isolation via repository scoping + ownership checks**: prevents IDOR;
  chosen over trusting the caller.
- **Roles**: `user` vs `admin` gives "different views for different users" — regular
  users see only their own data; admin gets a read-only cross-user overview.
- **Dark theme via CSS variables + `data-theme`**, persisted in `localStorage`, with
  a no-flash `<head>` script. Body background split into color+image (see §9 gotcha).
- **Backup import is additive + atomic + verbatim**: safe (no accidental wipe),
  all-or-nothing, and a re-export equals the original. Replace-mode deferred.
- **LAN serving**: `run.py` reads HOST/PORT/DEBUG; debugger disabled on non-localhost
  binds for safety; warns if the default SECRET_KEY is used while exposed.
- **No DB migrations**: dev data disposable; recreate the file on schema change.
  Alembic is the documented upgrade path.
- **App isolated under `subject-tracker/`** with its own git repo so it doesn't
  disturb the surrounding Rust workspace.

## 16. Known limitations / future work

- No timezone handling (server-local dates) — see §5.7.
- No DB migrations (recreate on schema change) — add Alembic.
- Chapters have a `title` (heading) but no free-text description field.
- Backup import is additive only (no replace/restore-in-place mode).
- Dev server only (no gunicorn/waitress); no HTTPS.
- Admin creation is via shell, not UI.
