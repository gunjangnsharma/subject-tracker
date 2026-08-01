# Subject Tracker — Build Context

> **Single source of truth** for *what* this app is, *why* every decision was made,
> and *how* to build, run and test it. This document is written so that another
> engineer (or agent) with no prior context can regenerate an equivalent app from
> scratch. If a detail matters, it is here.

Last updated: 2026-08-02

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
| Prod WSGI server | waitress | 3.0.0 (pure-Python, cross-platform) |
| Tests | pytest | 8.3.2 |
| Charts (client) | Chart.js | 4.4.3, **vendored** at `tracker/static/vendor/chart.umd.min.js` |
| Animations/theme JS | vanilla | `tracker/static/app.js` |

`requirements.txt` pins Flask, SQLAlchemy, waitress, pytest. Werkzeug arrives
transitively with Flask. Auth is hand-rolled — no other runtime dependencies.

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
| **Chapter** | `id`, `module_id` (FK→modules), `title`, `kind` (`video`\|`text`), `duration_minutes` (int), `completed_minutes` (int, 0..duration), `position` (int, 0-based within its module) | The atomic trackable item. Completed time entered as hours+minutes. `position` is the user-controlled display order — see §5.8. |
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

### 5.2 Completion — actual completed minutes
- A chapter stores **`completed_minutes`** (int, `0..duration_minutes`) — the real
  time done. **Done** when `completed_minutes >= duration_minutes` (`domain.is_done`).
- Server **clamps** to `0..duration` (`domain.clamp_completed`) as a safety net.
- **Where you edit it:** only on the **plan pages** (`/today`, `/week`), and only
  once a chapter is planned. The subject/modules page shows completion **read-only**
  (`completion_display` macro). Editing lives in the `completion_control` macro
  (plan pages only):
  - A **"Done" checkbox** instantly completes the chapter (sets `completed = duration`);
    unchecking clears it to 0.
  - **Hours + minutes inputs** that **auto-save on blur** (no Save button) via AJAX —
    the route returns JSON (on `X-Requested-With: XMLHttpRequest`) and `app.js`
    updates the row in place (no reload). A `<noscript>` Save button is the fallback.
  - **Inline validation, no popups** (see §9): minutes `0–59`; hours×60 + minutes ≤
    duration. Form is `novalidate`; errors render into `.field-error`.
- **Attribution:** completing a chapter logs the activity for **today** (the route's
  `set_completed_minutes` defaults `when` to `date.today()`), so study time always
  counts toward the day it was actually done — *not* the day it was planned for.
- `Chapter.completed_h` / `completed_m` split the stored value for the two inputs.
- *(History: earlier versions used a 0–10 completion proxy; replaced by direct
  minutes. Backups migrate — see §10.)*

### 5.3 Roll-ups (aggregation) — always computed, never stored
Derived live so they can't drift. Implemented as `domain.Progress` (a frozen
dataclass holding `total_minutes` + `completed_minutes`, with `remaining`,
`percent`, and `*_hours` properties; `Progress + Progress` sums them).
- **Chapter**: `completed = completed_minutes` (clamped 0..duration), `remaining = duration - completed`.
- **Module**: sum of its chapters. **Subject**: sum of its modules. **Overall**: sum of subjects.
- **Percent** = `completed / total * 100`, or `0` when total is 0 (no divide-by-zero).

### 5.4 Planning & backlog rollover — derived from dates, no scheduler

**No back-dating.** A chapter can only be planned for **today or a future**
date. The plan route rejects a past date (flash error); the date input's
`min` is set to today client-side. (The *service* still accepts any date, so
backup import and historical backlog data are unaffected.)

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
- **The subject page shows each chapter's planned date.** `Chapter.planned_date`
  (the single assignment's date, or None) drives the `plan_control` macro: the
  date input is **pre-filled** with the stored date so reopening the picker lands
  on that day, the date is also rendered as text, and the button reads
  Plan / Reschedule. *(Bug fixed here: the cell used to be an always-empty date
  input, so a chapter planned for another day looked like it was planned for
  today.)* The no-back-dating `min` is only applied when the field is empty or
  already future-dated — otherwise an overdue item's own date would be invalid.
- Because backlog is **computed on read**, finishing a chapter (`completion=10`)
  removes it from all backlogs automatically. Nothing is moved or deleted; **no cron**.

> Note: the dashboard's "This week's activity" **chart** stays a fixed Mon–Sun
> calendar week (retrospective activity via `domain.week_bounds`); only the `/week`
> **plan** page uses the rolling window. `week_bounds()` is still used by the chart.

### 5.5 Activity log
- Whenever `SubjectService.set_completed_minutes` changes completed minutes, it writes
  a `ProgressEvent(chapter_id, occurred_on=when or today, minutes_delta=Δ)`. A no-op
  change writes nothing; reducing completion writes a negative delta.
- `set_completed_minutes(chapter_id, completed_minutes, when=None)` — `when` is
  injectable so tests are clock-independent; the route passes nothing (defaults to today).

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

## 5.8 Chapter order within a module (user-reorderable)

Chapters display in a **user-defined order**, not by id. `Chapter.position` is a
0-based integer scoped to its module; `Module.chapters` orders by
**`(position, id)`**.

- **Why the `id` tiebreak:** rows written before `position` existed all arrive as
  `0`. Sorting by position alone would order those arbitrarily; the `id` tiebreak
  keeps them in the sequence they were added. Never drop it.
- **Reordering is one step at a time, within one module.** The subject page gives
  each chapter ▲/▼ buttons that swap it with its immediate neighbour
  (`POST /chapters/<id>/move` with `direction=up|down`). The swap partner is
  always a sibling, so a move can **never** relocate a chapter to a different
  module or subject.
- **The math is pure:** `domain.swap_index(index, direction, count)` returns the
  index to swap with, or `None` when the move would fall off either end.
  `MOVE_UP`/`MOVE_DOWN` are the direction constants.
- **Off-the-end is a no-op, not an error.** `SubjectService.move_chapter` returns
  `False` (pressing ▲ on the first row does nothing); the UI also disables those
  two buttons. An *unknown direction* is a 400 — that's a malformed request.
- **A move renumbers the whole module** to `0..n-1` rather than swapping two
  stored values. This matters for legacy rows: swapping two positions that are
  both `0` would change nothing, so renumbering both performs the move *and*
  repairs the duplicates. It also means positions stay contiguous.
- **New chapters land at the end** (`ChapterRepository.next_position`). Deleting
  a chapter leaves a gap, which is harmless — order is what matters, and the next
  move renumbers.
- **Backups carry order as array order** — no `position` field in the JSON. See §10.
- Legacy data can be normalised eagerly with
  `maintenance.backfill_chapter_positions` (idempotent); see §12.8.

## 6. Architecture (SOLID / layered) — complete file map

Dependencies point **inward**: `Routes → Services → Repositories → Models/DB`.
`domain.py` sits at the bottom and imports nothing from Flask/SQLAlchemy.

```
subject-tracker/
├── run.py                     Entry point; dev → Flask server, prod → waitress (see §12).
├── wsgi.py                     `app = create_app()` for external WSGI servers (gunicorn/waitress-serve).
├── scripts/
│   ├── squash_duplicate_plans.py   CLI for the one-date cleanup (see §12.6).
│   └── seed_dev_data.py            CLI: dummy accounts + sample data (see §12.9).
├── requirements.txt           Pinned deps.
├── README.md                  Quick start (points here).
├── .gitignore                 Ignores .venv, *.db, __pycache__, .DS_Store, etc.
├── deploy/                    Production deployment artifacts (see docs/DEPLOY_ORACLE.md):
│   ├── subject-tracker.service     systemd unit (runs waitress-serve wsgi:app).
│   ├── nginx-subject-tracker.conf  nginx reverse-proxy site.
│   └── subject-tracker.env.example env template (secret, DB path, HTTPS flag).
├── docs/
│   ├── BUILD_CONTEXT.md        This file.
│   ├── TEST_PLAN.md            Per-test purpose + strategy.
│   ├── DEPLOY_ORACLE.md        Step-by-step Oracle Cloud Always-Free hosting guide.
│   ├── DEPLOY_RASPBERRY_PI.md  Step-by-step Raspberry Pi (home LAN) hosting guide.
│   ├── BACKUP_SCHEMA.md        Import/Export JSON blueprint (rules + generation prompt).
│   └── backup.schema.json      JSON Schema (draft-07) for the backup format.
└── tracker/                   The Flask package.
    ├── __init__.py             App factory create_app(config=None): resolves config from
    │                           SUBJECT_TRACKER_ENV when None, applies resolve_settings()
    │                           for the env-backed values, enforces the prod-secret rule,
    │                           engine+session lifecycle (g.session per request),
    │                           load_logged_in_user → g.user, `hm` Jinja filter,
    │                           current_user template global, Cache-Control: no-store on
    │                           HTML responses (after_request), registers all 6 blueprints.
    ├── config.py               Config (base) + DevConfig / ProdConfig / TestConfig,
    │                           get_config(name) resolving SUBJECT_TRACKER_ENV, EnvSettings
    │                           (reads an injected environ mapping) and resolve_settings()
    │                           which fills the FROM_ENV settings at app-build time. Holds
    │                           DATABASE_URL, SECRET_KEY, MAX_CONTENT_LENGTH, cookie flags.
    ├── database.py             Base(DeclarativeBase); Database(url) → engine + scoped
    │                           session; _TUNING_PRAGMAS applied per connection (WAL,
    │                           synchronous=NORMAL, busy_timeout, foreign_keys, cache,
    │                           temp_store — see §11.1); create_all() (also runs
    │                           schema.ensure_columns + ensure_indexes); remove().
    ├── schema.py               Additive schema reconciliation: ALTER TABLE ... ADD COLUMN
    │                           for columns, CREATE INDEX IF NOT EXISTS for indexes,
    │                           on tables that already exist (create_all only builds
    │                           either for tables it creates). Idempotent. See §12.7.
    ├── models.py               ORM models User/Subject/Module/Chapter/PlanAssignment/
    │                           ProgressEvent + .progress/.is_done helpers; cascades; enums.
    │                           Chapter.position + Module.chapters ordered (position, id).
    ├── domain.py               PURE math: clamp_completed, minutes_to_hours, format_hm,
    │                           completed_minutes, percent, is_done, week_bounds,
    │                           swap_index + MOVE_UP/MOVE_DOWN (reorder arithmetic),
    │                           Progress dataclass, chapter_progress, sum_progress. No Flask/DB.
    ├── auth.py                 Session auth: login_user/logout_user/current_user,
    │                           load_logged_in_user (before_request), login_required,
    │                           admin_required. SESSION_KEY="user_id".
    ├── maintenance.py          One-off cleanups: squash_duplicate_plans (keeps the
    │                           most recent plan assignment per chapter),
    │                           backfill_chapter_positions (0..n-1 per module; idempotent).
    ├── repositories/           DATA ACCESS ONLY (the only layer touching the ORM).
    │   ├── user_repository.py       UserRepository(session): add/get/get_by_username/list_all.
    │   ├── subject_repository.py    SubjectRepository + ModuleRepository (session, user_id);
    │   │                            scoped by user; get() enforces ownership.
    │   ├── chapter_repository.py    ChapterRepository(session, user_id); ownership via Module→Subject;
    │   │                            siblings/next_position/set_positions for ordering.
    │   ├── plan_repository.py       PlanRepository(session, user_id); on_date/in_range/before,
    │   │                            all joined through Chapter→Module→Subject→user.
    │   └── activity_repository.py   ActivityRepository(session, user_id); on_date/between (joined scope).
    ├── services/               BUSINESS LOGIC; own the commit boundary.
    │   ├── auth_service.py          AuthService(session): register/authenticate/get/list_users.
    │   ├── subject_service.py       SubjectService(session, user_id): subject/module/chapter
    │   │                            CRUD, set_completed_minutes (logs activity), roll-ups,
    │   │                            move_chapter (reorder within a module), list_module_chapters.
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
    │   ├── _macros.html             progress_bar(p), kind_pill(kind), completion_display,
    │   │                            completion_control, reorder_control(chapter, first, last),
    │   │                            plan_control(chapter), plan_list(items, show_from).
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
| POST | `/chapters/<id>/completion` | login | Set completed minutes (`completed_hours`+`completed_minutes`); logs activity dated today. Returns JSON for AJAX (`X-Requested-With`), else redirects. |
| POST | `/chapters/<id>/delete` | login | Delete chapter. |
| POST | `/chapters/<id>/move` | login | Reorder: swap with the neighbour above/below inside the same module (`direction=up\|down`). Returns JSON `{moved, module_id, chapter_ids}` for AJAX, else redirects. Off-the-end → `moved: false`; bad direction → 400. |
| POST | `/chapters/<id>/plan` | login | Assign chapter to `planned_date` (**required, today-or-future only**). |
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

Versioned document (`format: "subject-tracker-backup"`, `version: 2`). Chapters
carry `completed_minutes`. **Importing v1** (which stored `completion` 0–10) is
still supported — it converts `completed = round(duration * completion / 10)`.
Export always emits v2. **Chapter order travels as the order of the `chapters`
array** — there is deliberately **no `position` field**: export lists chapters in
display order and import assigns positions while walking the array, so a
re-export reproduces the order exactly and hand-authored files stay simple (no
format bump was needed for the reorder feature). **Full blueprint + JSON Schema:**
[docs/BACKUP_SCHEMA.md](BACKUP_SCHEMA.md) and [docs/backup.schema.json](backup.schema.json)
(hand these to any tool/agent to generate a valid import file).

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
         "completed_minutes": 90, "plan_dates": ["YYYY-MM-DD"],   // plan_dates: 0 or 1
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
| `SUBJECT_TRACKER_ENV` | `dev` | Environment: `dev` \| `prod` \| `test`. Selects the config class (`get_config`). Prod runs on waitress and requires a real secret. |
| `SUBJECT_TRACKER_DB` | `sqlite:///<cwd>/subject_tracker.db` | SQLAlchemy DB URL. Tests use `:memory:` via `TestConfig`. |
| `SUBJECT_TRACKER_SECRET` | `dev-secret-change-me` | Flask `SECRET_KEY` for signed sessions. **Required in prod** (app refuses to start with the default). |
| `SUBJECT_TRACKER_HTTPS` | (off) | `1` sets `SESSION_COOKIE_SECURE` — enable only when actually behind HTTPS. |
| `HOST` | `127.0.0.1` | Bind interface. `0.0.0.0` = reachable on the LAN. |
| `PORT` | `5000` | Listen port. |
| `DEBUG` | (off) | Dev only: `1` enables reloader/debugger — **only honoured on localhost** (the Werkzeug debugger allows RCE and must never be network-reachable). Ignored in prod. |

`MAX_CONTENT_LENGTH = 8 MB` (fixed in config) caps uploads. Session cookies are
`HttpOnly` + `SameSite=Lax` in every environment.

### 11.1 SQLite tuning (`database.py`) — why the Pi was slow

SQLite's defaults are wrong for a small multi-user web app on slow storage.
`Database` applies `_TUNING_PRAGMAS` to **every** connection (a SQLAlchemy
`connect` event, so pooled connections are covered too):

| PRAGMA | Value | Why |
|---|---|---|
| `journal_mode` | `WAL` | **Readers are never blocked by the writer.** With the default rollback journal a writer takes an EXCLUSIVE lock on the whole file, so one `DELETE` stalls every other request — the "whole UI hangs" symptom. Persistent (stored in the file). |
| `synchronous` | `NORMAL` | No fsync per commit. Measured ~13.9 ms/commit at `FULL` vs ~0.05 ms at `NORMAL`+WAL; on an SD card each fsync is far worse. Still crash-safe — you only risk the last few commits on a *power* loss. |
| `busy_timeout` | `5000` | A second writer waits (ms) instead of raising "database is locked". |
| `foreign_keys` | `ON` | SQLite disables FK enforcement by default, so the `ondelete="CASCADE"` FKs never fired — the ORM did all cascading in Python. |
| `cache_size` | `-8000` | ~8 MB page cache (default 2 MB): fewer reads from slow storage. Fine on a 1 GB Pi. |
| `temp_store` | `MEMORY` | Sort/join temporaries in RAM, not on the SD card. |

WAL is skipped for `:memory:` databases (no file to lock, and it's unsupported
there); the rest still applies.

**Indexes.** SQLite does **not** index foreign keys automatically, so before this
work the only index in a live database was the implicit one on `users.username` —
every ownership check and join was a full table scan. The models now declare:
`ix_subjects_user_id`, `ix_modules_subject_id`,
`ix_chapters_module_id_position`, `ix_plan_assignments_planned_date`,
`ix_plan_assignments_chapter_id`, `ix_progress_events_occurred_on`,
`ix_progress_events_chapter_id`.

**Both apply to an already-deployed database on the next restart** — WAL lives in
the file, and `schema.ensure_indexes` creates missing indexes at startup. No
reset, no manual step.

**Backup caveat:** WAL means recent commits can be in `app.db-wal`, so a plain
`cp app.db` may miss data. Use `sqlite3 app.db ".backup 'out.db'"` (or
`VACUUM INTO`), or stop the service and copy `.db`, `.db-wal` and `.db-shm`
together. The deploy guides say the same.

### Environments (`config.py`)
- **dev** (`DevConfig`) — Flask dev server; **templates auto-reload** on change;
  debugger available on localhost via `DEBUG=1`.
- **prod** (`ProdConfig`) — served by **waitress**; no debugger; templates cached;
  **refuses to start with the default `SECRET_KEY`** (`create_app` raises).
- **test** (`TestConfig`) — in-memory DB, `TESTING=True`. Not a deployment target:
  nothing serves it, and the test fixtures pass `create_app(TestConfig)` explicitly.
  The two runtime versions are **dev and prod**.
`create_app(None)` resolves the class from `SUBJECT_TRACKER_ENV`; passing a class
explicitly (e.g. `create_app(TestConfig)`) bypasses env resolution.

Note that `ProdConfig` adds no behaviour of its own — its `DEBUG=False` /
`TEMPLATES_AUTO_RELOAD=False` already match the `Config` base, so `ENV = "prod"`
is the only distinguishing attribute. Every real prod difference is enforced
*outside* the class: the secret check in `create_app`, and the waitress branch in
`run.py`. Don't "simplify" the class away — those two checks key off `ENV`.

### How env-backed settings resolve (`EnvSettings` / `resolve_settings`)
`DATABASE_URL`, `SECRET_KEY` and `SESSION_COOKIE_SECURE` are declared on `Config`
as `FROM_ENV` (i.e. `None`) and filled in **when `create_app` runs**, not at
import time. Precedence: **explicit class value > env var > built-in default**.

- `EnvSettings(environ)` — the only thing that reads environment variables. The
  mapping is injected (defaults to `os.environ`), so tests pass a plain dict
  instead of mutating global state.
- `resolve_settings(config, environ)` — returns the final value for each
  env-backed setting; `create_app` merges it into `app.config`. Standalone
  scripts call it to open the same database the app would
  (`scripts/squash_duplicate_plans.py`).
- Adding an env-backed setting = one reader method on `EnvSettings` + one line in
  `_ENV_BACKED`; the config classes stay declarative.

> **Why (bug fixed here):** the values used to be read in the class body, so the
> first `import tracker.config` froze them and any env var set afterwards was
> silently ignored. `test_default_create_app_is_dev` set `SUBJECT_TRACKER_DB`
> after that import, so the patch was a no-op and the test created a real
> `subject_tracker.db` in the repo root (invisible in `git status` — it's
> gitignored). Resolving at build time makes late env vars work and keeps the
> suite off the on-disk DB.

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

### 12.3 Production server (waitress)
```bash
SUBJECT_TRACKER_ENV=prod \
SUBJECT_TRACKER_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')" \
SUBJECT_TRACKER_DB="sqlite:////var/lib/subject-tracker/app.db" \
HOST=0.0.0.0 PORT=5000 python run.py            # serves via waitress, no debugger
```
Or with an external WSGI server against `wsgi:app`:
```bash
SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... \
    waitress-serve --listen=127.0.0.1:5000 wsgi:app
SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... \
    gunicorn --bind 127.0.0.1:5000 wsgi:app      # Linux
```
Prod refuses the default secret. For public exposure put it behind a reverse
proxy that terminates **HTTPS**, then set `SUBJECT_TRACKER_HTTPS=1`.

**Hosting recipes** (both use systemd + waitress; ready-made files in `deploy/`):
- [docs/DEPLOY_ORACLE.md](DEPLOY_ORACLE.md) — Oracle Cloud Always-Free VM end to end
  (open ports at the cloud **and** host firewall, venv, systemd `waitress-serve
  wsgi:app`, nginx reverse proxy, certbot HTTPS, admin, backups).
- [docs/DEPLOY_RASPBERRY_PI.md](DEPLOY_RASPBERRY_PI.md) — a Raspberry Pi (3B+ or newer)
  on the home LAN (simpler: no cloud firewall; bind waitress to `0.0.0.0:5000`),
  with an optional internet-exposure section (router forward + DDNS + HTTPS).

Either way SQLite persists on local storage (VM boot volume / SD card), so no
database change is needed.

### 12.4 Run the tests
```bash
pytest                # run the full suite
pytest -q             # quiet
pytest tests/test_backup.py -v      # one file, verbose
```
Tests use a fresh in-memory SQLite DB per test (no touching the dev DB).

### 12.5 Create an admin (no UI for this)
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

### 12.6 Squash duplicate plans (one-off cleanup)
Data created before the one-date-per-chapter rule may have a chapter planned on
several dates. Collapse them (keeps the most recent per chapter):
```bash
python scripts/squash_duplicate_plans.py --dry-run   # preview, no changes
python scripts/squash_duplicate_plans.py             # apply
```
Idempotent and respects `SUBJECT_TRACKER_DB`. Logic lives in
`tracker/maintenance.py` (`squash_duplicate_plans`).

### 12.7 Schema changes & resetting the database

There is **no migration tool**, but there is a narrow safety net. `create_all`
only creates *missing tables* — it never alters one that already exists — so a
database written by an older version would break on any query mentioning a new
column. `tracker/schema.py` (`ensure_columns`, called from `Database.create_all`)
closes that gap for the common case:

- it runs `ALTER TABLE ... ADD COLUMN` for columns listed in `_ADDED_COLUMNS`,
- **only** for columns that are nullable or have a server default (so existing
  rows get a value),
- it runs `CREATE INDEX IF NOT EXISTS` (`ensure_indexes`) for every index the
  models declare, since `create_all` only builds indexes for tables it creates —
  an existing table would otherwise keep scanning,
- it is **idempotent** — present columns and indexes are skipped, so it is safe on
  every boot,
- it never drops, renames, retypes or reorders anything.

So **adding a defaulted column or an index needs no reset**: add it to the model
(and, for a column, one line in `_ADDED_COLUMNS`) and existing databases upgrade
themselves on the next start. This is how `Chapter.position` and the performance
indexes (§11.1) shipped.

Anything else — dropping a column, changing a type, adding a NOT NULL column with
no default, new constraints — is still a manual reset. Dev data is disposable:

```bash
rm -f subject_tracker.db        # then start the server to recreate the schema
```

For durable data across arbitrary schema changes, add Alembic (future work).

### 12.8 Backfill chapter positions (legacy data)
Chapters created before `Chapter.position` existed all default to `0`. They still
display in the right order (the `(position, id)` sort), and the first reorder of a
module renumbers it. To normalise everything up front:
```bash
python - <<'PY'
from tracker import create_app
from tracker.maintenance import backfill_chapter_positions
app = create_app(); s = app.database.Session()
result = backfill_chapter_positions(s); s.commit()
print(f"renumbered {result.chapters_renumbered} chapters in {result.modules_affected} modules")
PY
```
Idempotent — a module already numbered `0..n-1` is left untouched.

### 12.9 Seed dummy accounts + sample data (dev only)
```bash
python scripts/seed_dev_data.py            # refuses if the users already exist
python scripts/seed_dev_data.py --reset    # delete those users first, then reseed
```
Creates `student` / `student123` (regular user, filled with 3 subjects, 6 modules,
21 chapters, ~2 weeks of back-dated activity, and 9 planned chapters — 2 of them
overdue so the backlog is populated) and `boss` / `boss12345` (admin, empty, for
viewing `/admin`). Writes through the **service layer**, so seeded data obeys every
rule the app enforces; activity uses the injectable `when` argument. Respects
`SUBJECT_TRACKER_DB`. Never run it against production data.

## 13. Security notes

- Auth prevents cross-user access (§8); foreign ids 404.
- Default `SECRET_KEY` is a known dev value — override via env before exposing.
- No HTTPS (dev server). Fine on localhost/trusted LAN; use a reverse proxy/tunnel
  with TLS for anything internet-facing.
- Werkzeug debugger is never enabled on a network bind (`run.py`).
- Upload size capped (`MAX_CONTENT_LENGTH`); import is validated + atomic.

## 14. Milestones (git history — replay in order)

Each line is one commit (`git log --oneline --reverse`). The first block is the
original build; the rest are incremental features and fixes.

**Original build**
1. **scaffold** — structure, docs, deps.
2. **core-domain** — models, DB, domain math, subject/module/chapter CRUD + roll-ups.
3. **planning** — daily/weekly plans + backlog rollover.
4. **ui** — app factory, routes, templates, styling.
5. **tests** — pytest suite (domain, roll-ups, CRUD, planning, routes).
6. **dashboard** — ProgressEvent activity log + charts dashboard + animations.
7. **auth** — multi-user accounts, per-user isolation, admin overview.
8. **serve** — configurable HOST/PORT/DEBUG for LAN access.
9. **backlog-display tests** — backlog carry-over shows the chapter heading.
10. **theme** — flashy dark theme with persisted toggle.
11. **backup** — JSON export/import.

**Docs & subsequent changes**
12. **docs** — regeneration-grade BUILD_CONTEXT + TEST_PLAN + run guide.
13. **docs** — add AGENTS.md entry point.
14. **fix** — completion save returns to originating page; visible/clickable date picker.
15. **week** — rolling 7-day plan grouped by day (today..today+6).
16. **plan** — one date per chapter (re-planning moves it; no duplicates).
17. **maintenance** — `scripts/squash_duplicate_plans.py` for legacy duplicates.
18. **display** — durations shown as "Xh Ym" (not decimal hours).
19. **completion** — capture completed time as hours+minutes with inline validation
    (replaces the 0–10 proxy; stores `completed_minutes`).
20. **plan-page completion** — read-only on the subject page; Done checkbox + blur
    auto-save (AJAX) on the plan pages; activity dated today.
21. **ui** — move backlog section above the plan on today & week pages.
22. **fix** — `Cache-Control: no-store` on HTML pages (no stale views).
23. **fix** — plan button no longer assigns without an explicit date.
24. **rule** — a chapter cannot be planned for a past date (route-only guard).
25. **test** — confirm JSON import accepts past plan dates.
26. **config** — resolve env-backed settings at app-build time via `EnvSettings` /
    `resolve_settings` (fixes import-time freezing + a test writing a real DB file).
27. **seed** — `scripts/seed_dev_data.py`: dummy user + admin accounts with sample data.
28. **reorder** — chapters are reorderable within a module (`Chapter.position`, ▲/▼
    buttons, `POST /chapters/<id>/move`) + `schema.ensure_columns` so existing
    databases gain the column without a reset.
29. **perf** — SQLite tuned for slow storage (WAL fixes writes blocking the whole
    UI; `synchronous=NORMAL` kills the per-commit fsync) + indexes on every FK and
    date column, backfilled into existing databases by `schema.ensure_indexes`.

## 15. Decisions & assumptions log (why, not just what)

- **Stack = Flask + SQLAlchemy + SQLite**: readable, minimal setup, maps cleanly to
  SOLID service/repository layers; SQLite needs no server. (User-confirmed.)
- **Completion = actual completed minutes** entered as hours+minutes (two inputs),
  with inline client validation (minutes 0–59; total ≤ duration) and no popups.
  Replaced the original 0–10 proxy for precision, per user request. Backup bumped
  to v2; v1 backups auto-convert on import.
- **Roll-ups computed, never stored**: eliminates drift; cheap at this scale.
- **Backlog derived from dates, not moved**: idempotent, needs no scheduler, and
  finishing a chapter clears it everywhere automatically.
- **One date per chapter**: `assign` is an upsert (re-planning moves the chapter),
  so a chapter never appears in more than one day/section. Enforced in the service
  + importer (they are the only writers) rather than a DB constraint, to avoid a
  migration and keep old-backup imports working.
- **Planning requires an explicit date; no back-dating** — both enforced in the
  **plan route only**. An empty date is rejected (never defaults to today); a past
  date is rejected. The service and backup importer still accept any date, so
  historical/backlog data and restores are unaffected. (Real bugs fixed here: the
  empty→today default, and the native picker implicitly submitting on Enter — the
  Plan button is disabled until a date is chosen and Enter no longer submits.)
- **Completion editing lives on the plan pages, not the subject page**: you plan a
  chapter, then set its completed time on `/today` or `/week`. The subject page is
  read-only. A "Done" checkbox completes instantly; h/m inputs auto-save on blur via
  AJAX (in-place, no reload). Completing always dates activity to **today**.
- **HTML is never cached** (`Cache-Control: no-store`, app-factory `after_request`)
  so data changes always show immediately; static assets keep normal caching.
- **Legacy cleanup via a script, not a migration**: `squash_duplicate_plans` collapses
  pre-rule duplicate assignments (keeps the most recent), run on demand.
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
- **Dev / prod split** (`SUBJECT_TRACKER_ENV`): dev = Flask dev server + template
  auto-reload; prod = **waitress** (real WSGI server), no debugger, cached templates,
  and **refuses to boot with the default SECRET_KEY**. Chose waitress over gunicorn
  because it is pure-Python and cross-platform (works on macOS/Windows). `wsgi.py`
  exposes the app for any external WSGI server. Session cookies are HttpOnly +
  SameSite=Lax always; Secure is opt-in via `SUBJECT_TRACKER_HTTPS` (needs real TLS).
- **Environment settings resolve at app-build time, not import time**
  (`EnvSettings` + `resolve_settings`): config classes stay declarative and
  `EnvSettings` is the single place that touches `os.environ`, with the mapping
  injected so tests need no global state. Fixed a real bug — class-body
  `os.environ.get(...)` froze `DATABASE_URL`/`SECRET_KEY` on first import, so a
  later env change was ignored and one test silently created a real
  `subject_tracker.db` in the repo. Precedence is explicit value > env > default.
- **Chapter order is user-controlled via a `position` column**, ordered
  `(position, id)`. Chosen over sorting by title (users want their own sequence)
  and over swapping row ids (ids are referenced by `plan_assignments` and
  `progress_events` — swapping them would silently move plan and activity history
  to the wrong chapter). Reordering is **one step at a time within one module**:
  ▲/▼ buttons that swap with the neighbour, which keeps the interaction usable
  without JS and trivially testable. A move **renumbers the whole module** to
  `0..n-1` instead of exchanging two values, so legacy rows that all share
  position `0` still move correctly (and get repaired in the process). Backups
  carry order as array order rather than a new field, so the format needed no
  version bump.
- **Additive schema reconciliation instead of migrations** (`schema.ensure_columns`):
  `create_all` never alters an existing table, so a new column would break older
  databases. A narrow, idempotent `ALTER TABLE ... ADD COLUMN` pass for defaulted
  columns lets features like `Chapter.position` ship without asking users to
  delete their data — while stopping well short of being a migration framework
  (Alembic remains the answer for anything more).
- **SQLite tuned per connection rather than "SQLite is too slow, switch to
  Postgres"** (§11.1): the real causes on a Raspberry Pi were the default
  rollback journal (a writer exclusively locks the file, so any delete froze
  every other request) and `synchronous=FULL` (an fsync per commit, brutal on an
  SD card), plus **no indexes on foreign keys** — SQLite doesn't create them.
  WAL + `synchronous=NORMAL` + FK indexes address all three and keep the
  zero-server deployment. Rejected "run the UI and writes on separate threads":
  waitress already uses 4 threads; the serialization was a lock on the database
  *file*, one layer below Python, so threading it differently would not have
  helped. WAL is the correct form of that idea.
- **No DB migrations**: dev data disposable; recreate the file on schema change.
  Alembic is the documented upgrade path.
- **App isolated under `subject-tracker/`** with its own git repo so it doesn't
  disturb the surrounding Rust workspace.

## 16. Known limitations / future work

- No timezone handling (server-local dates) — see §5.7.
- No DB migrations (recreate on schema change) — add Alembic.
- Chapters have a `title` (heading) but no free-text description field.
- Backup import is additive only (no replace/restore-in-place mode).
- Admin creation is via shell, not UI.
- **Known remaining performance cost** (after §11.1): relationships load lazily,
  so pages issue more queries than needed (measured: `/` 16, `/week` 18, one
  subject delete 34 — mostly N+1 on `chapters`/`modules`). Fix with eager loading
  (`selectinload`) in the repositories. Also, every page sends the 200 KB vendored
  Chart.js even though only the dashboard draws charts, and `Cache-Control:
  no-store` is broad. Both matter over Wi-Fi on a Pi.
