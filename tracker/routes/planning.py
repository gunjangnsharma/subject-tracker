"""Routes for today's plan, the week's plan, and assigning chapters to dates."""

from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from tracker.auth import current_user
from tracker.services.planning_service import PlanningService

bp = Blueprint("planning", __name__)


@bp.before_request
def _require_login():
    if current_user() is None:
        return redirect(url_for("auth.login"))


def _service() -> PlanningService:
    return PlanningService(g.session, current_user().id)


def _parse_date(raw: str | None) -> date | None:
    """Parse an ISO date, or None if it is missing/invalid (no silent default)."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.get("/today")
def today():
    plan = _service().today_plan(date.today())
    return render_template("today.html", plan=plan)


@bp.get("/week")
def week():
    plan = _service().rolling_plan(date.today())
    return render_template("week.html", plan=plan)


@bp.post("/chapters/<int:chapter_id>/plan")
def assign(chapter_id: int):
    back = request.referrer or url_for("planning.today")
    planned_date = _parse_date(request.form.get("planned_date"))
    if planned_date is None:
        # A date is required — never assign to "today" by default.
        flash("Pick a date to plan this chapter.", "error")
        return redirect(back)
    if planned_date < date.today():
        # No back-dating: you can only plan for today or a future day.
        flash("You can't plan a chapter for a past date.", "error")
        return redirect(back)
    try:
        _service().assign(chapter_id, planned_date)
        flash(f"Chapter planned for {planned_date.isoformat()}.", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(back)
