#!/usr/bin/env python3
"""One-time cleanup: squash duplicate plan assignments (one date per chapter).

Run from the subject-tracker/ directory:

    python scripts/squash_duplicate_plans.py            # apply the cleanup
    python scripts/squash_duplicate_plans.py --dry-run  # preview, change nothing

Respects the SUBJECT_TRACKER_DB env var (defaults to ./subject_tracker.db).
Idempotent: running it again after a clean-up removes nothing.
"""

import os
import sys

# Make the `tracker` package importable when run as a standalone script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.config import resolve_settings
from tracker.database import Database
from tracker.maintenance import squash_duplicate_plans


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]

    # Same database the app would open (SUBJECT_TRACKER_DB, else ./subject_tracker.db).
    db = Database(resolve_settings()["DATABASE_URL"])
    db.create_all()
    session = db.Session()

    result = squash_duplicate_plans(session)

    if dry_run:
        session.rollback()
        print(
            f"[dry-run] would remove {result.assignments_removed} duplicate "
            f"assignment(s) across {result.chapters_affected} chapter(s). "
            f"No changes made."
        )
    else:
        session.commit()
        print(
            f"Removed {result.assignments_removed} duplicate assignment(s) across "
            f"{result.chapters_affected} chapter(s); kept the most recent per chapter."
        )
    db.remove()


if __name__ == "__main__":
    main()
