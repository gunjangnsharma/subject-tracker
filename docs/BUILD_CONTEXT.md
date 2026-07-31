# Subject Tracker — Build Context

> Single source of truth for **what** this app is and **why** it is built the way it is.
> If the codebase is ever lost, this document is enough to rebuild an equivalent app.

Last updated: 2026-08-01

---

## 1. Purpose

A simple web app to track study progress across **subjects**. It answers two questions:

1. **How much is done and how much is left** — for every chapter, module and subject.
2. **What should I do today / this week** — with automatic rollover of unfinished work
   into today's plan ("yesterday's backlog") and the week's plan ("weekly backlog").

## 2. Domain model

```
Subject 1───* Module 1───* Chapter
                              │
                              *
                       PlanAssignment  (a chapter planned for a specific date)
```

### Entities

| Entity | Fields | Notes |
|--------|--------|-------|
| **Subject** | `id`, `name` | Top-level study area. |
| **Module** | `id`, `subject_id`, `name` | A unit inside a subject. |
| **Chapter** | `id`, `module_id`, `title`, `kind` (`video`\|`text`), `duration_minutes`, `completion` (0–10) | The atomic trackable item. |
| **PlanAssignment** | `id`, `chapter_id`, `planned_date` (DATE) | "I plan to do this chapter on this day." Week is derived from the date. |
| **ProgressEvent** | `id`, `chapter_id`, `occurred_on` (DATE), `minutes_delta` | Study-activity log: the change in completed minutes on a day. Powers today/week *activity* (the current completion value can't say *when* work happened). |

## 3. Core business rules

### 3.1 Duration
- Duration is **stored in minutes** (integer).
- Duration is **displayed in hours** for the UI: `hours = minutes / 60` (e.g. 90 min → `1.5h`).

### 3.2 Completion (the "1–10" metric)
- `completion` is an integer **0–10** representing tenths of the chapter done.
- `10` = fully finished, `5` = half done, `0` = not started.
- **Completed minutes** = `duration_minutes * completion / 10`.
- Example (from spec): a 2-hour (120 min) video, 1 hour done → user enters `5` →
  `120 * 5/10 = 60` minutes completed (50%).
- A chapter is **done** when `completion == 10`.

### 3.3 Roll-ups (progress aggregation)
Computed, never stored — always derived from chapters so they can't go stale.
- **Chapter**: `completed = duration * completion/10`, `remaining = duration - completed`.
- **Module**: `total = Σ chapter.duration`, `completed = Σ chapter.completed`, `remaining = total - completed`.
- **Subject**: `total = Σ module.total`, `completed = Σ module.completed`, `remaining = total - completed`.
- **Percent complete** at any level = `completed / total * 100` (0 when total is 0).

### 3.4 Planning & backlog rollover
The key insight: **backlog is computed from dates, not physically moved.** No cron job needed.

- **Today view** (for date `T = today`):
  - *Today's plan* = assignments where `planned_date == T`.
  - *Backlog* = assignments where `planned_date < T` **and** chapter not done (`completion < 10`).
    These are shown as "carried over from <date>".
- **Week view** (for the week containing today, Monday–Sunday):
  - *This week's plan* = assignments where `planned_date` in `[week_start, week_end]`.
  - *Weekly backlog* = assignments where `planned_date < week_start` **and** chapter not done.
- Because backlog is derived, finishing a chapter (setting `completion = 10`) makes it
  disappear from all backlogs automatically. Nothing is deleted or moved.

## 4. Architecture (SOLID / layered)

Dependencies point **inward**: Routes → Services → Repositories → Models/DB.
Each layer depends only on the layer below via a narrow interface.

```
tracker/
  __init__.py            App factory (create_app), wires blueprints + DB.
  config.py              Config objects (DB URL, etc.).
  database.py            SQLAlchemy engine/session management (scoped session).
  models.py              ORM models: Subject, Module, Chapter, PlanAssignment.
  domain.py              Pure calculation helpers (minutes↔hours, roll-ups). No DB, no Flask.
  repositories/          Data access only (CRUD). One repo per aggregate.
    subject_repository.py
    module_repository.py
    chapter_repository.py
    plan_repository.py
  services/              Business logic. Orchestrate repos + domain rules.
    subject_service.py   Subject/module/chapter use-cases + progress roll-ups.
    planning_service.py  Daily/weekly plans + backlog computation.
  routes/                Flask blueprints (HTTP controllers only, no logic).
    subjects.py
    planning.py
  templates/             Jinja2 HTML.
  static/                CSS.
run.py                   Dev entry point.
```

### Why this shape (SOLID)
- **S**ingle responsibility: routes handle HTTP, services hold rules, repos hold SQL, domain holds math.
- **O**pen/closed: new features (e.g. tags) add a repo+service without touching existing ones.
- **L**iskov / **I**nterface segregation: services depend on small repo interfaces, not the ORM globally.
- **D**ependency inversion: `domain.py` (the rules) knows nothing about Flask or SQLAlchemy,
  so the calculation logic is unit-testable in isolation and reusable.

### 3.5 Dashboard aggregation (activity tracking)
The dashboard (`/`) combines three things, computed by `DashboardService.build(today)`:
- **Overall progress** — sum of all subjects' roll-ups (doughnut chart).
- **Today** — chapters planned today, how many done, backlog count, and minutes
  *studied today* (sum of positive `ProgressEvent.minutes_delta` on today's date).
- **This week** — a 7-day (Mon–Sun) breakdown of *studied* minutes (from events)
  vs *planned* minutes (durations of chapters assigned to each day). Bar chart.

Charts are rendered client-side with a **locally vendored Chart.js**
(`static/vendor/chart.umd.min.js`); the route passes a small JSON payload.
Entrance animations (count-up numbers, reveal-on-scroll) live in `static/app.js`
and respect `prefers-reduced-motion`.

## 5. Routes (UI + actions)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | **Dashboard**: overall progress + today + week activity, with charts. |
| GET  | `/subjects` | Manage subjects (list with progress bars). |
| POST | `/subjects` | Add subject. |
| POST | `/subjects/<id>/delete` | Delete subject (cascades modules/chapters). |
| GET  | `/subjects/<id>` | Subject detail: modules + chapters + roll-ups. |
| POST | `/subjects/<id>/modules` | Add module. |
| POST | `/modules/<id>/delete` | Delete module. |
| POST | `/modules/<id>/chapters` | Add chapter (title, kind, duration). |
| POST | `/chapters/<id>/completion` | Update completion (0–10). |
| POST | `/chapters/<id>/delete` | Delete chapter. |
| POST | `/chapters/<id>/plan` | Assign chapter to a date. |
| GET  | `/today` | Today's plan + carried-over backlog. |
| GET  | `/week` | This week's plan + weekly backlog. |

## 6. How to run

```bash
cd subject-tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py            # serves on http://127.0.0.1:5000
pytest                   # run the test suite
```

The SQLite file (`subject_tracker.db`) is created automatically on first run.

## 7. Milestones (git history)

Each milestone is one commit so the build can be replayed step by step.

1. **scaffold** — project structure, docs (this file), test plan, deps.
2. **core-domain** — models, DB, domain math, subject/module/chapter CRUD + roll-ups.
3. **planning** — daily/weekly plans and backlog rollover.
4. **ui** — templates and styling for a usable web UI.
5. **tests** — pytest suite covering domain math, roll-ups, and backlog logic.

## 8. Decisions & assumptions log

- Stack: **Python + Flask + SQLAlchemy + SQLite** (chosen for readable, testable, minimal setup).
- Completion modeled as **10-point ratio of duration** (confirmed with spec's 2-hour example).
- Backlog is **derived from dates**, not stored/moved — idempotent, no scheduler.
- Week runs **Monday → Sunday** (ISO). Change `week_bounds()` in `domain.py` to alter this.
- Roll-ups are **always computed**, never persisted, to avoid drift.
- App isolated under `subject-tracker/` so it does not disturb the existing Rust note-taking workspace.
