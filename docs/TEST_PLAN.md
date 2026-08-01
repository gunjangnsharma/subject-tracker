# Subject Tracker — Test Plan

Every test and what it verifies. Built alongside the app. Run from
`subject-tracker/` with `pytest` (165 tests). Suite runs against a fresh in-memory
SQLite database per test, so tests are isolated, deterministic and never touch the
dev DB.

Last updated: 2026-08-02

---

## 1. Strategy

- **Unit tests** for pure logic in `tracker/domain.py` — no DB, no Flask.
- **Integration tests** for services against an in-memory SQLite DB — repos + rules together.
- **Route / smoke tests** via Flask's test client — pages render, actions persist, auth gates.
- Dates that drive backlog/activity are **injected** (functions take `today` / `when`),
  so tests never depend on the wall clock.

## 2. Fixtures (`tests/conftest.py`)

| Fixture | Provides |
|---------|----------|
| `app` | A `create_app(TestConfig)` instance (new in-memory DB → full isolation). |
| `session` | A DB session bound to that app's database. |
| `user_id` | A registered non-admin user `tester`; returns its id for scoping services. |
| `client` | Flask test client (not logged in). |
| `auth_client` | Flask test client with `tester` registered **and logged in**. |

`tests/test_chapter_order.py` adds a local `module_with_chapters` fixture: a
subject + module holding four chapters (`First`..`Fourth`) in a known order.

## 3. Test inventory — each test and what it checks

### 3.1 `test_domain.py` — pure math (9)
| Test | Checks |
|------|--------|
| `test_minutes_to_hours` | `90 → 1.5`, `0 → 0.0` (decimal hours for chart axes). |
| `test_format_hm` | `130 → "2h 10m"`, `120 → "2h"`, `30 → "30m"`, `0 → "0m"`, `22.5 → "22m"`. |
| `test_progress_hm_strings` | `Progress` exposes `total_hm/completed_hm/remaining_hm` as "Xh Ym". |
| `test_chapter_progress_from_minutes` | `120,60→60`, `60,60→60`, `60,0→0` (completed time stored directly). |
| `test_percent_safe_and_correct` | `percent(0,0) → 0` (no divide-by-zero); `percent(30,120) → 25.0`. |
| `test_completed_clamped` | Clamp completed to `0..duration` (200→120, -5→0, 45→45). |
| `test_is_done` | `is_done(dur, done)`: 120,120→True; 120,119→False; over-complete→True. |
| `test_week_bounds_monday_to_sunday` | A Wednesday → (that week's Monday, Sunday). |
| `test_progress_rollup_addition` | `sum_progress` adds totals/completed/remaining and computes percent. |

### 3.2 `test_subjects.py` — subject/module/chapter service + roll-ups (9)
| Test | Checks |
|------|--------|
| `test_add_and_list_subject` | Added subject appears in the user's list. |
| `test_add_module_and_chapter` | Module links to subject; new chapter defaults completed 0, stores duration. |
| `test_update_completion_reflects_minutes` | Set 60 min on a 120-min chapter → 60 completed minutes. |
| `test_completion_is_clamped` | Set 999 → clamped to the chapter duration. |
| `test_module_and_subject_rollup` | Module and subject totals/completed/remaining sum correctly. |
| `test_empty_module_rollup` | Empty module → total 0, percent 0 (no error). |
| `test_delete_subject_cascades` | Deleting a subject removes its modules and chapters. |
| `test_delete_chapter_recalculates` | Deleting a chapter recomputes the module total. |
| `test_invalid_inputs_raise` | Blank subject name and unknown chapter kind raise `ValueError`. |

### 3.3 `test_activity.py` — study-activity logging (4)
| Test | Checks |
|------|--------|
| `test_progress_logs_positive_delta` | 0→60 min on a 120-min chapter logs `+60` on the given date. |
| `test_reducing_completion_logs_negative_delta` | Then 60→36 min logs `-24`; both events present. |
| `test_no_change_logs_nothing` | Setting the same completed minutes logs no event. |
| `test_when_defaults_to_today` | With no `when`, the event is dated today. |

### 3.4 `test_planning.py` — plans + backlog rollover (7)
| Test | Checks |
|------|--------|
| `test_assigned_today_shows_in_plan` | A chapter planned today is in today's plan, not backlog. |
| `test_yesterday_incomplete_is_backlog` | Incomplete + planned yesterday → today's backlog, keeps original date. |
| `test_yesterday_complete_not_backlog` | Completed (full) + planned yesterday → not in backlog. |
| `test_past_incomplete_is_rolling_backlog` | Incomplete + planned in the past → rolling plan's overdue backlog. |
| `test_future_shows_in_its_day_not_backlog` | Planned today+3 → appears in that day-group, not backlog. |
| `test_finishing_backlog_removes_it` | Marking it fully complete removes it from both today & week backlog. |
| `test_rolling_window_is_today_to_today_plus_6` | Window is 7 days starting today; day 0 is today. |

### 3.5 `test_backlog_display.py` — backlog carry-over shows the heading (6)
| Test | Checks |
|------|--------|
| `test_past_week_incomplete_goes_to_weekly_backlog` | Service: title present in weekly backlog; original date kept. |
| `test_past_day_incomplete_goes_to_today_backlog` | Service: title present in today's backlog. |
| `test_completed_item_not_in_either_backlog` | Finished item excluded from both backlogs. |
| `test_today_page_shows_backlog_heading` | Rendered `/today` contains the chapter heading + "carried from <date>". |
| `test_week_page_shows_backlog_heading` | Rendered `/week` shows the heading under Overdue backlog + carried-from date. |
| `test_finished_item_absent_from_today_page` | Rendered `/today` shows no "carried from" when the item is finished. |

### 3.6 `test_dashboard.py` — dashboard aggregation (8)
| Test | Checks |
|------|--------|
| `test_overall_progress_sums_subjects` | Overall total/completed sum across subjects; subject count correct. |
| `test_today_stats` | planned_count / done_count / backlog_count and studied_minutes all correct. |
| `test_today_done_count` | A finished chapter planned today counts as done. |
| `test_completion_counts_toward_today_not_planned_day` | Completing a chapter planned for another day counts toward today's studied time. |
| `test_week_activity_per_day` | Positive deltas bucket into the right weekday; week total correct. |
| `test_week_planned_per_day` | Assignment durations bucket into the right day; week planned total correct. |
| `test_week_has_seven_days` | Week = 7 days Mon..Sun with the correct start date. |
| `test_empty_dashboard` | Empty account → all zeros, no errors. |

### 3.7 `test_auth.py` — registration / login (7)
| Test | Checks |
|------|--------|
| `test_register_hashes_password` | Password stored hashed (≠ plaintext); role defaults to `user`. |
| `test_register_rejects_short_password` | Password < 6 chars raises `ValueError`. |
| `test_register_rejects_duplicate_username` | Duplicate username raises. |
| `test_authenticate_success_and_failure` | Correct → user; wrong password / unknown user → None. |
| `test_register_logs_in_and_redirects` | Registering via route logs in and lands on the dashboard. |
| `test_login_logout_cycle` | After logout a protected page redirects to `/login`; re-login works. |
| `test_bad_login_shows_error` | Wrong credentials show "Invalid username or password". |

### 3.8 `test_isolation.py` — multi-user isolation + admin (8)
| Test | Checks |
|------|--------|
| `test_list_is_scoped_per_user` | Each user lists only their own subjects. |
| `test_cannot_get_other_users_subject` | Fetching another user's subject by id returns None. |
| `test_cannot_edit_other_users_chapter` | Foreign chapter: `get` → None, `set_completed_minutes` raises. |
| `test_cannot_plan_other_users_chapter` | Planning another user's chapter raises. |
| `test_dashboard_is_scoped` | One user's dashboard shows zero of another user's data. |
| `test_admin_can_see_overview` | Admin gets `/admin` → 200 with the overview. |
| `test_regular_user_forbidden_from_admin` | Non-admin hitting `/admin` → 403. |
| `test_admin_link_hidden_for_regular_user` | The Admin nav link is absent for a regular user. |

### 3.9 `test_routes.py` — route smoke + auth gating (17)
| Test | Checks |
|------|--------|
| `test_dashboard_ok` | `GET /` → 200 when logged in. |
| `test_subjects_page_ok` | `GET /subjects` → 200. |
| `test_create_subject_appears` | `POST /subjects` then it shows on `/subjects`. |
| `test_subject_detail_and_chapter_flow` | Add module + 90-min chapter; page shows `1h 30m`; set completed 45m → `45m of 1h 30m`. |
| `test_today_and_week_ok` | `/today` and `/week` → 200. |
| `test_missing_subject_404` | `/subjects/999` (nonexistent/foreign) → 404. |
| `test_protected_routes_redirect_when_logged_out` | `/`, `/subjects`, `/today`, `/week` → 302 to `/login` when logged out. |
| `test_subject_page_completed_is_readonly` | Subject page shows read-only completion (no inputs / Done checkbox). |
| `test_plan_page_has_editable_completion` | A planned chapter's `/today` row has the h/m inputs + Done checkbox. |
| `test_completion_ajax_returns_json` | AJAX completion POST returns JSON (completed_minutes/hm/is_done). |
| `test_theme_toggle_present_on_every_page` | Base layout ships the toggle button + the no-flash theme script. |
| `test_completion_update_returns_to_originating_page` | Saving completion from `/today` or `/week` redirects back there (via Referer), not to subject detail. |
| `test_plan_requires_a_date` | Planning without a date does nothing + flashes "Pick a date" (no silent today default). |
| `test_plan_with_a_date_assigns` | Planning with a date assigns the chapter to that date. |
| `test_plan_rejects_past_date` | Planning a past date is refused (flash "past date"); nothing assigned. |
| `test_plan_allows_future_date` | Planning a future date assigns it (shows on `/week`). |
| `test_html_pages_are_not_cached` | Dynamic HTML sends `Cache-Control: no-store`; static assets don't. |

### 3.10 `test_backup.py` — JSON export / import (17)
| Test | Checks |
|------|--------|
| `test_export_structure` | Envelope (format/version/user) + nested subjects with `plan_dates` and `activity`. |
| `test_export_is_json_serialisable` | Export round-trips through `json.dumps`/`loads`. |
| `test_export_then_import_into_another_user` | Import counts correct; imported payload matches the source. |
| `test_import_preserves_completion_without_extra_activity` | Completion restored verbatim; no fabricated activity events. |
| `test_import_keeps_one_plan_date_per_chapter` | Multiple `plan_dates` collapse to the first (one date per chapter). |
| `test_import_v1_backup_converts_completion_to_minutes` | Legacy v1 (0–10) import converts to completed minutes. |
| `test_import_accepts_past_plan_dates` | Import restores past-dated plans verbatim (no-back-dating is route-only). |
| `test_import_is_additive` | Existing subjects kept; imported ones added. |
| `test_invalid_envelope_rejected` (×4 params) | Non-dict / wrong format / bad version / non-list subjects → `BackupError`. |
| `test_invalid_kind_rejected_and_rolls_back` | Bad `kind` raises **and** nothing persists (atomic rollback). |
| `test_bad_date_rejected` | Malformed plan date → `BackupError`. |
| `test_export_route_returns_download` | `GET /export` → 200, `application/json`, attachment header, correct body. |
| `test_import_route_adds_data` | `POST /import` with a file adds the data and redirects. |
| `test_import_route_rejects_bad_json` | Uploading invalid JSON shows "not valid JSON". |

### 3.11 `test_week_plan.py` — rolling 7-day week plan + one-date rule (15)
| Test | Checks |
|------|--------|
| `test_window_is_seven_days_from_today` | 7 day-groups, start=today, end=today+6, chronological; day 0 is today (weekday label correct). |
| `test_window_rolls_with_today` | A different `today` shifts the whole window; still 7 days from that day. |
| `test_today_item_in_first_group` | A chapter planned today lands in `days[0]`, others empty. |
| `test_future_item_in_its_own_day` | Planned today+4 → in `days[4]` only; not in backlog. |
| `test_beyond_window_is_not_shown` | Planned today+8 → in no day-group and not backlog (it's future). |
| `test_multiple_items_same_day_grouped_and_sorted` | Two chapters same day → both in that day, sorted (subject/module/title). |
| `test_overdue_incomplete_in_backlog_not_days` | Past + unfinished → overdue backlog, not a day-group. |
| `test_overdue_complete_excluded` | Past + finished → excluded from backlog. |
| `test_week_page_shows_seven_day_sections` | Rendered `/week` has 7 day sections + each day's date label + Today badge + Overdue backlog. |
| `test_week_page_task_under_its_day` | A chapter planned today+3 shows on the page under that day's heading. |
| `test_week_page_empty_day_shows_nothing_planned` | Days with no tasks render "Nothing planned.". |
| `test_reassigning_moves_chapter` | Re-planning moves the chapter (off the old day, onto the new); appears once. |
| `test_assign_same_date_twice_keeps_one` | Assigning the same date twice keeps a single entry. |
| `test_chapter_appears_once_across_today_and_week` | A planned chapter shows once on the Today page and once in the week. |
| `test_week_page_replan_shows_task_once` | Rendered `/week`: a re-planned chapter's title appears exactly once. |

### 3.12 `test_maintenance.py` — squash duplicate plans (4)
| Test | Checks |
|------|--------|
| `test_squash_keeps_most_recent_and_removes_rest` | 3 dup assignments → keeps highest id (latest), removes 2. |
| `test_squash_leaves_single_assignment_untouched` | A chapter with one assignment is not touched. |
| `test_squash_is_idempotent` | Running again removes nothing. |
| `test_squash_handles_multiple_chapters` | Squashes several chapters at once; counts correct; singletons untouched. |

### 3.13 `test_config.py` — dev / prod / test environments (21)
| Test | Checks |
|------|--------|
| `test_get_config_resolves_names` | `get_config` maps dev/prod/test → the right class; unknown → dev. |
| `test_get_config_reads_env` | `SUBJECT_TRACKER_ENV` selects the config; default is dev. |
| `test_dev_reloads_templates_prod_caches` | Dev auto-reloads templates; prod caches them. |
| `test_prod_debug_off` | `ProdConfig.DEBUG` is False. |
| `test_prod_refuses_default_secret` | `create_app` raises in prod with the default `SECRET_KEY`. |
| `test_prod_with_real_secret_starts` | Prod app boots with a real secret (ENV=prod, DEBUG off). |
| `test_session_cookie_hardening` | Session cookies are HttpOnly + SameSite=Lax. |
| `test_default_create_app_is_dev` | No env → dev; **and** `SUBJECT_TRACKER_DB` set *after* `tracker.config` was imported is still honoured (settings resolve at `create_app` time). Runs in `tmp_path` so it can never write into the repo. |
| `test_env_settings_reads_an_injected_mapping` | `EnvSettings` reads env/DB/secret/HTTPS from an injected dict (no `os.environ`); env name is case-insensitive. |
| `test_env_settings_defaults_when_unset` | Empty environment → dev, `DEFAULT_SECRET`, HTTPS off, cwd-relative `subject_tracker.db`. |
| `test_https_flag_parsing` (×9 params) | `1/true/TRUE/yes/on` → True; `0/false/""/nonsense` → False. |
| `test_explicit_config_value_beats_the_environment` | Precedence: `TestConfig`'s explicit `DATABASE_URL` wins over the env var, while its `FROM_ENV` `SECRET_KEY` comes from the environment. |
| `test_resolve_settings_falls_back_to_env_config` | `resolve_settings()` with no config uses the class named by `SUBJECT_TRACKER_ENV`. |

### 3.14 `test_chapter_order.py` — reordering chapters within a module (33)

Covers the whole feature stack: pure index math, the service rule, legacy
databases that predate the `position` column, isolation, the route, and backup
round-tripping.

**Pure domain math (4)**
| Test | Checks |
|------|--------|
| `test_swap_index_moves_one_step` | `swap_index(2, up, 5) → 1`; `down → 3`. |
| `test_swap_index_returns_none_at_the_ends` | First can't go up, last can't go down, single item can't move — `None`, not an error. |
| `test_swap_index_rejects_bad_direction` | An unknown direction raises `ValueError`. |
| `test_swap_index_out_of_range_is_none` | Index outside `0..count-1` → `None`. |

**Service (10)**
| Test | Checks |
|------|--------|
| `test_new_chapters_get_sequential_positions` | Four added chapters get positions `0..3` in insertion order. |
| `test_move_down_swaps_with_next` | Moving the first chapter down swaps it with the second. |
| `test_move_up_swaps_with_previous` | Moving the third up swaps it with the second. |
| `test_move_up_at_top_is_a_noop` | ▲ on the first row returns `False`, order unchanged. |
| `test_move_down_at_bottom_is_a_noop` | ▼ on the last row returns `False`, order unchanged. |
| `test_move_is_reversible` | Down then up restores the original order. |
| `test_positions_stay_contiguous_after_moves` | After two moves positions are still `0..3` — no gaps or duplicates. |
| `test_move_rejects_bad_direction` | `"sideways"` raises `ValueError`. |
| `test_move_unknown_chapter_raises` | An unknown chapter id raises `ValueError`. |
| `test_reorder_is_confined_to_one_module` | Pushing a chapter past the end of its module never moves it into a sibling module; both modules keep their own chapters. |
| `test_deleting_a_chapter_leaves_the_rest_ordered` | Deleting mid-list keeps order; a later move renumbers over the gap. |
| `test_new_chapter_lands_at_the_end_after_reordering` | A chapter added after reordering appends last. |

**Isolation (1)**
| Test | Checks |
|------|--------|
| `test_cannot_reorder_another_users_chapter` | Another user's `move_chapter` raises and leaves the owner's order untouched. |

**Legacy databases (5)**
| Test | Checks |
|------|--------|
| `test_ensure_columns_adds_position_to_an_old_database` | A hand-built pre-feature `chapters` table (no `position`) gains the column via `create_all`; the existing row survives, defaults to 0 and is queryable. |
| `test_ensure_columns_is_idempotent` | Nothing to add on a fresh DB, and still nothing on a second run. |
| `test_legacy_rows_all_at_zero_keep_insertion_order` | Rows sharing position 0 stay in id order (the `(position, id)` sort). |
| `test_backfill_renumbers_legacy_positions` | `backfill_chapter_positions` turns all-zero positions into `0..n-1` without changing the order. |
| `test_backfill_is_idempotent` | A module already numbered `0..n-1` reports 0 modules affected. |
| `test_move_works_on_legacy_all_zero_positions` | The first move on all-zero data actually moves (renumbering repairs the duplicates). |

**Route (7)**
| Test | Checks |
|------|--------|
| `test_move_route_reorders_and_redirects` | Plain POST (no-JS) → 302 and the rows swap on the reloaded page. |
| `test_move_route_ajax_returns_new_order` | AJAX POST → 200 with `{moved: true, module_id, chapter_ids}` in the new order. |
| `test_move_route_reports_noop_without_changing_anything` | ▲ on the first row → `moved: false`, ids unchanged. |
| `test_move_route_rejects_bad_direction` | An unknown direction → 400. |
| `test_move_route_404s_for_unknown_chapter` | Unknown/foreign chapter id → 404. |
| `test_move_route_requires_login` | Logged out → 302 to `/login`. |
| `test_subject_page_renders_reorder_buttons` | The page ships `.reorder` controls with both directions; the first row's ▲ and last row's ▼ are `disabled`. |

**Backup round-trip (3)**
| Test | Checks |
|------|--------|
| `test_export_lists_chapters_in_display_order` | Export reflects the reordered sequence, not id order. |
| `test_import_preserves_chapter_order` | Import into another account reproduces the order and assigns positions `0..3`. |
| `test_reexport_after_import_is_identical` | Export → import → re-export gives an identical `subjects` payload. |

## 4. Manual QA checklist (before a release)

- [ ] Register an account; land on the dashboard.
- [ ] Add a subject, module, and a 90-min video chapter; detail header shows `1.5h`.
- [ ] Subject page shows completion **read-only** (no inputs); use **Plan** to add it to a day.
- [ ] On the subject page, press ▲/▼ on a chapter → it swaps with its neighbour and the
      order survives a reload. The first row's ▲ and last row's ▼ are greyed out.
- [ ] Reordering a chapter never moves it into a different module.
- [ ] On `/today` or `/week`: tick **Done** → instantly completes (100%); no reload.
- [ ] Edit the h/m inputs and click away → **auto-saves on blur**; the row updates in place.
- [ ] Enter minutes > 59 → inline "Minutes must be 0–59" (no popup); nothing saves.
- [ ] Enter a time exceeding the chapter length → inline "Can't exceed <duration>"; nothing saves.
- [ ] Complete a chapter planned for another day → it counts under **Studied today**.
- [ ] Plan the chapter for today; it appears on `/today`.
- [ ] Plan a chapter for a past day/week; it appears as backlog with "carried from <date>".
- [ ] Open `/week`: 7 day sections from today, today highlighted, tasks under the right day, empty days say "Nothing planned".
- [ ] Set completion to 10; it disappears from `/today` and `/week` backlog.
- [ ] Toggle the theme (🌙/☀️); it persists across pages and charts recolor.
- [ ] Export JSON; register a second account; import the file → data reappears.
- [ ] Log in as an admin; `/admin` lists all users; a regular user gets 403.
- [ ] Delete a subject; its modules/chapters vanish and totals update.

## 5. How to run

```bash
cd subject-tracker
pytest -q                          # run the full suite
pytest tests/test_planning.py -q   # one file
pytest -k backlog -q               # by keyword
pytest -v                          # show each test name
```
