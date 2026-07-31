# Subject Tracker

A Flask + SQLite web app to track study progress across subjects, modules and
chapters — with per-user accounts, daily/weekly planning and automatic backlog
rollover, an activity-tracking charts dashboard, a light/dark theme, and JSON
backup/restore.

- **Full design & rebuild guide:** [docs/BUILD_CONTEXT.md](docs/BUILD_CONTEXT.md)
- **Test plan (every test explained):** [docs/TEST_PLAN.md](docs/TEST_PLAN.md)

## Setup (once)

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run — local machine

```bash
python run.py            # http://127.0.0.1:5000  (localhost only)
DEBUG=1 python run.py    # with auto-reload/debugger (localhost only)
```

Open `/register` to create an account. The SQLite file `subject_tracker.db` is
created automatically on first run.

## Run — reachable from other devices on your Wi-Fi (LAN)

```bash
HOST=0.0.0.0 SUBJECT_TRACKER_SECRET="$(python -c 'import secrets;print(secrets.token_hex(16))')" python run.py
```

Then open `http://<this-machine-LAN-IP>:5000` from the other device
(find the IP with `ipconfig getifaddr en0` on macOS Wi-Fi). Plain HTTP — fine on a
trusted network, not for the public internet. See BUILD_CONTEXT §12 for details.

## Tests

```bash
pytest            # all 77 tests
pytest -v         # show each test name
```

## Make an admin (no UI for this)

```bash
python - <<'PY'
from tracker import create_app
from tracker.services.auth_service import AuthService
s = create_app().database.Session()
AuthService(s).register("boss", "secret123", role="admin")
PY
```

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `SUBJECT_TRACKER_DB` | `sqlite:///<cwd>/subject_tracker.db` | Database URL. |
| `SUBJECT_TRACKER_SECRET` | `dev-secret-change-me` | Session signing key — set a real one when exposed. |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind interface / port (`HOST=0.0.0.0` for LAN). |
| `DEBUG` | off | `1` enables the debugger — localhost only. |
