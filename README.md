# Subject Tracker

A simple Flask + SQLite web app to track study progress across subjects, modules and
chapters — with daily/weekly planning and automatic backlog rollover.

- **Full design & rebuild guide:** [docs/BUILD_CONTEXT.md](docs/BUILD_CONTEXT.md)
- **Test plan:** [docs/TEST_PLAN.md](docs/TEST_PLAN.md)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py     # http://127.0.0.1:5000
pytest            # run tests
```
