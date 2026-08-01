#!/usr/bin/env python3
"""Seed the dev database with two dummy accounts and sample study data.

    python scripts/seed_dev_data.py              # seed (refuses if users exist)
    python scripts/seed_dev_data.py --reset      # wipe those users first, then seed

Creates:
    student / student123   (role user)  — filled with sample subjects + activity
    boss    / boss12345    (role admin) — empty; use it to view /admin

Goes through the service layer (never raw SQL), so everything it writes obeys the
same rules the app enforces. Activity is dated via the injectable ``when``
argument, so the dashboard and backlog have realistic history.

Respects SUBJECT_TRACKER_DB. Dev convenience only — never run against prod data.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

# Make the `tracker` package importable when run as a standalone script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.config import resolve_settings
from tracker.database import Database
from tracker.repositories.user_repository import UserRepository
from tracker.services.auth_service import AuthService
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

STUDENT = ("student", "student123")
ADMIN = ("boss", "boss12345")

# (subject, [(module, [(title, kind, duration_minutes, completed_minutes)])])
SAMPLE = [
    ("Machine Learning", [
        ("Linear Algebra", [
            ("Vectors and spaces", "video", 90, 90),
            ("Matrix multiplication", "video", 75, 75),
            ("Determinants", "video", 60, 30),
            ("Eigenvalues and eigenvectors", "video", 120, 0),
            ("Singular value decomposition", "text", 45, 0),
        ]),
        ("Probability", [
            ("Random variables", "video", 80, 80),
            ("Bayes' theorem", "video", 55, 20),
            ("Distributions cheat sheet", "text", 30, 0),
        ]),
        ("Neural Networks", [
            ("Perceptrons", "video", 65, 0),
            ("Backpropagation by hand", "video", 110, 0),
            ("Activation functions", "text", 40, 0),
        ]),
    ]),
    ("Operating Systems", [
        ("Processes", [
            ("Process lifecycle", "video", 70, 70),
            ("Context switching", "video", 50, 50),
            ("Scheduling algorithms", "video", 95, 45),
        ]),
        ("Memory", [
            ("Virtual memory", "video", 85, 0),
            ("Paging and TLBs", "video", 100, 0),
            ("Allocator design notes", "text", 35, 0),
        ]),
    ]),
    ("Spanish", [
        ("A1 Basics", [
            ("Greetings and introductions", "video", 40, 40),
            ("Present tense verbs", "video", 60, 60),
            ("Numbers and dates", "video", 35, 15),
            ("Food vocabulary", "text", 25, 0),
        ]),
    ]),
]


def seed_student(session, user_id: int, today: date) -> dict[str, int]:
    """Create the sample tree, then plan and back-date activity around *today*."""
    subjects = SubjectService(session, user_id)
    counts = {"subjects": 0, "modules": 0, "chapters": 0, "planned": 0}
    chapters: list = []   # flat list, in creation order

    for subject_name, modules in SAMPLE:
        subject = subjects.add_subject(subject_name)
        counts["subjects"] += 1
        for module_name, chapter_specs in modules:
            module = subjects.add_module(subject.id, module_name)
            counts["modules"] += 1
            for title, kind, duration, completed in chapter_specs:
                chapter = subjects.add_chapter(module.id, title, kind, duration)
                counts["chapters"] += 1
                chapters.append((chapter, completed))

    # Spread the completed work backwards over the last two weeks so the
    # dashboard's "studied today / this week" charts have something to draw.
    # `when` is injected, exactly as the tests do it.
    day_offsets = [0, 0, 1, 2, 3, 4, 6, 8, 9, 11, 13]
    studied = 0
    for i, (chapter, completed) in enumerate([c for c in chapters if c[1] > 0]):
        when = today - timedelta(days=day_offsets[i % len(day_offsets)])
        subjects.set_completed_minutes(chapter.id, completed, when=when)
        studied += completed
    counts["studied_minutes"] = studied

    return counts, chapters


def plan_chapters(session, user_id: int, today: date, chapters: list) -> int:
    """Plan a realistic mix: today, the week ahead, and two overdue (backlog)."""
    planning = PlanningService(session, user_id)
    unfinished = [c for c, completed in chapters if not c.is_done]

    # planned_date offsets from today: two overdue (negative => backlog), one
    # today, then spread across the coming week.
    offsets = [-4, -2, 0, 0, 1, 2, 3, 5, 6]
    planned = 0
    for chapter, offset in zip(unfinished, offsets):
        # The service accepts any date (the no-back-dating rule is route-only),
        # which is what lets us seed overdue backlog items.
        planning.assign(chapter.id, today + timedelta(days=offset))
        planned += 1
    return planned


def main() -> None:
    reset = "--reset" in sys.argv[1:]
    today = date.today()

    db = Database(resolve_settings()["DATABASE_URL"])
    db.create_all()
    session = db.Session()

    auth = AuthService(session)
    users = UserRepository(session)
    existing = [n for n, _ in (STUDENT, ADMIN) if users.get_by_username(n)]
    if existing and not reset:
        print(f"Users already exist: {', '.join(existing)}. Re-run with --reset to replace them.")
        db.remove()
        return
    for name in existing:
        session.delete(users.get_by_username(name))   # cascades to subjects/chapters
    if existing:
        session.commit()
        print(f"Removed existing: {', '.join(existing)}")

    student = auth.register(*STUDENT)
    admin = auth.register(*ADMIN, role="admin")

    counts, chapters = seed_student(session, student.id, today)
    planned = plan_chapters(session, student.id, today, chapters)

    print(f"Seeded '{STUDENT[0]}' (password {STUDENT[1]}):")
    print(f"  {counts['subjects']} subjects, {counts['modules']} modules, "
          f"{counts['chapters']} chapters")
    print(f"  {counts['studied_minutes']} minutes of activity over the last 2 weeks")
    print(f"  {planned} chapters planned (2 overdue -> backlog, rest today..today+6)")
    print(f"Created admin '{ADMIN[0]}' (password {ADMIN[1]}) — visit /admin")
    db.remove()


if __name__ == "__main__":
    main()
