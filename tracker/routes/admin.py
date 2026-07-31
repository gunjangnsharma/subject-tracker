"""Admin-only overview: every user and their total progress.

Demonstrates role-based views — regular users never reach this page; admins get
an aggregate across all accounts (read-only).
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, g, render_template

from tracker import domain
from tracker.auth import admin_required
from tracker.services.auth_service import AuthService
from tracker.services.subject_service import SubjectService

bp = Blueprint("admin", __name__)


@dataclass(frozen=True)
class UserOverview:
    id: int
    username: str
    role: str
    subject_count: int
    progress: domain.Progress


@bp.get("/admin")
@admin_required
def overview():
    users = AuthService(g.session).list_users()
    rows = []
    for user in users:
        # Scope a SubjectService to each user to reuse the roll-up logic.
        subjects = SubjectService(g.session, user.id).list_subjects()
        progress = domain.sum_progress([s.progress for s in subjects])
        rows.append(
            UserOverview(
                id=user.id,
                username=user.username,
                role=user.role,
                subject_count=len(subjects),
                progress=progress,
            )
        )
    return render_template("admin.html", rows=rows)
