# Subject Tracker — Test Plan

Built in parallel with the app. Each milestone adds the tests listed here.
Run everything with `pytest` from the `subject-tracker/` directory.

Last updated: 2026-08-01

---

## 1. Strategy

- **Unit tests** for pure logic in `tracker/domain.py` (no DB, no Flask) — fast, deterministic.
- **Integration tests** for services against an in-memory SQLite DB — verify repos + rules together.
- **Route/smoke tests** via Flask's test client — verify pages render and actions persist.
- Dates that drive backlog logic are injected (functions take a `today` argument), so tests
  never depend on the real clock.

## 2. Test matrix

### 2.1 Domain math (`test_domain.py`) — milestone: core-domain
| # | Case | Expectation |
|---|------|-------------|
| D1 | `minutes_to_hours(90)` | `1.5` |
| D2 | `minutes_to_hours(0)` | `0.0` |
| D3 | `completed_minutes(120, 5)` | `60` (2h video half done) |
| D4 | `completed_minutes(60, 10)` | `60` (fully done) |
| D5 | `completed_minutes(60, 0)` | `0` |
| D6 | `percent(0, 0)` | `0` (no divide-by-zero) |
| D7 | `percent(30, 120)` | `25.0` |
| D8 | completion clamped to 0–10 (reject 11 / -1) | raises / clamps |

### 2.2 Roll-ups (`test_rollups.py`) — milestone: core-domain
| # | Case | Expectation |
|---|------|-------------|
| R1 | Module with chapters 60@10 and 120@5 | total 180, completed 120, remaining 60 |
| R2 | Subject with two modules | totals sum correctly |
| R3 | Empty module | total 0, completed 0, percent 0 |
| R4 | Deleting a subject removes its modules and chapters (cascade) | counts drop to 0 |

### 2.3 Subject/module/chapter CRUD (`test_subjects.py`) — milestone: core-domain
| # | Case | Expectation |
|---|------|-------------|
| S1 | Add subject → appears in list | present |
| S2 | Add module under subject | linked to subject |
| S3 | Add chapter under module (video, 90 min) | stored, completion default 0 |
| S4 | Update completion to 5 | persisted, completed minutes reflect it |
| S5 | Delete chapter | gone; module total recalculated |

### 2.4 Planning & backlog (`test_planning.py`) — milestone: planning
| # | Case | Expectation |
|---|------|-------------|
| P1 | Assign chapter to today → shows in today's plan | present, not backlog |
| P2 | Chapter planned yesterday, completion 5 → today's backlog | present as carried-over |
| P3 | Chapter planned yesterday, completion 10 → NOT in backlog | absent |
| P4 | Chapter planned last week, incomplete → weekly backlog | present |
| P5 | Chapter planned earlier this week → week plan, not weekly backlog | present in plan |
| P6 | Finishing a backlog chapter (set 10) removes it from today & week backlog | absent after |
| P7 | `week_bounds(Wed)` returns Mon..Sun of that week | correct range |

### 2.5 Routes / smoke (`test_routes.py`) — milestone: ui
| # | Case | Expectation |
|---|------|-------------|
| W1 | `GET /` returns 200 and lists subjects | 200 |
| W2 | `POST /subjects` then `GET /` shows it | present |
| W3 | `GET /subjects/<id>` renders modules/chapters | 200 |
| W4 | `POST /chapters/<id>/completion` updates value | redirect + persisted |
| W5 | `GET /today` and `GET /week` return 200 | 200 |

### 2.6 Activity log (`test_activity.py`) — milestone: dashboard
| # | Case | Expectation |
|---|------|-------------|
| A1 | Set completion 0→5 on 120-min chapter | logs +60 minutes on the given date |
| A2 | Then 5→3 | logs −24 minutes (36−60) |
| A3 | Set same value again | no event logged |
| A4 | No `when` given | event dated today |

### 2.7 Dashboard aggregation (`test_dashboard.py`) — milestone: dashboard
| # | Case | Expectation |
|---|------|-------------|
| B1 | Overall progress | sums all subjects' totals/completed |
| B2 | Today stats | planned/done/backlog counts + studied minutes correct |
| B3 | Today done count | finished planned chapter counted |
| B4 | Week per-day studied | positive deltas bucketed to the right weekday |
| B5 | Week per-day planned | assignment durations bucketed per day |
| B6 | Week shape | 7 days Mon–Sun, correct start |
| B7 | Empty dashboard | zeros, no errors |

### 2.8 Auth (`test_auth.py`) — milestone: auth
| # | Case | Expectation |
|---|------|-------------|
| C1 | Register | password stored hashed, role defaults to `user` |
| C2 | Short password / duplicate username | raises ValueError |
| C3 | Authenticate right/wrong/unknown | returns user / None / None |
| C4 | Register via route | logs in, lands on dashboard |
| C5 | Login → logout → protected page | redirects to `/login` |
| C6 | Bad login | shows "Invalid username or password" |
| C7 | Protected routes logged out | 302 → `/login` |

### 2.9 Multi-user isolation (`test_isolation.py`) — milestone: auth
| # | Case | Expectation |
|---|------|-------------|
| I1 | Each user's list is their own | no cross-user leakage |
| I2 | Fetch another user's subject by id | None (ownership enforced) |
| I3 | Edit another user's chapter | None / raises (denied) |
| I4 | Plan another user's chapter | raises ValueError |
| I5 | Dashboard is scoped | other user's totals are zero |
| I6 | Admin can see `/admin` | 200 |
| I7 | Regular user hits `/admin` | 403 |
| I8 | Admin link hidden for regular user | not in nav |

### 2.10 JSON backup (`test_backup.py`) — milestone: backup
| # | Case | Expectation |
|---|------|-------------|
| K1 | Export structure | format/version/user + nested subjects with plan_dates & activity |
| K2 | Export is JSON-serialisable | round-trips through `json` |
| K3 | Export → import into another user | counts correct; payload matches source |
| K4 | Import preserves completion | no fabricated activity events |
| K5 | Import is additive | existing subjects kept, new ones added |
| K6 | Invalid envelope (format/version/type) | raises BackupError |
| K7 | Invalid kind mid-import | raises + atomic rollback (nothing persisted) |
| K8 | Bad date | raises BackupError |
| K9 | `GET /export` | 200, JSON mimetype, attachment header, correct body |
| K10 | `POST /import` with file | adds data, redirects |
| K11 | `POST /import` bad JSON | shows "not valid JSON" |

## 3. Manual QA checklist (before a release)

- [ ] Add a subject, module, and a 90-min video chapter; header shows `1.5h`.
- [ ] Set completion to 5; module and subject bars move to reflect partial progress.
- [ ] Plan the chapter for today; it appears on `/today`.
- [ ] Re-plan a chapter for yesterday (or wait a day); it appears as backlog on `/today`.
- [ ] Set completion to 10; it disappears from `/today` and `/week` backlog.
- [ ] Delete a subject; its modules/chapters vanish and totals update.

## 4. How to run

```bash
cd subject-tracker
pytest -q            # all tests
pytest tests/test_planning.py -q   # one file
```
