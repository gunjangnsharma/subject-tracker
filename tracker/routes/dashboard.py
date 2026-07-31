"""The main dashboard: overall progress + today + this-week activity."""

from __future__ import annotations

import json
from datetime import date

from flask import Blueprint, g, render_template

from tracker.auth import current_user, login_required
from tracker.services.dashboard_service import DashboardService

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@login_required
def home():
    view = DashboardService(g.session, current_user().id).build(date.today())

    # Data payloads for the client-side charts (kept minimal & explicit).
    charts = {
        "overall": {
            "completed": round(view.overall.completed_hours, 2),
            "remaining": round(view.overall.remaining_hours, 2),
        },
        "subjects": {
            "labels": [s.name for s in view.subjects],
            "completed": [round(s.progress.completed_hours, 2) for s in view.subjects],
            "remaining": [round(s.progress.remaining_hours, 2) for s in view.subjects],
        },
        "week": {
            "labels": [d.label for d in view.week.days],
            "studied": [round(d.studied_hours, 2) for d in view.week.days],
            "planned": [round(d.planned_hours, 2) for d in view.week.days],
        },
    }
    return render_template("dashboard.html", view=view, charts_json=json.dumps(charts))
