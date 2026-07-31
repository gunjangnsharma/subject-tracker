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


def _parse_date(raw: str | None, default: date) -> date:
    if not raw:
        return default
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return default


@bp.get("/today")
def today():
    plan = _service().today_plan(date.today())
    return render_template("today.html", plan=plan)


@bp.get("/week")
def week():
    plan = _service().week_plan(date.today())
    return render_template("week.html", plan=plan)


@bp.post("/chapters/<int:chapter_id>/plan")
def assign(chapter_id: int):
    planned_date = _parse_date(request.form.get("planned_date"), date.today())
    try:
        _service().assign(chapter_id, planned_date)
        flash("Chapter added to plan.", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    # Return to wherever the user came from, else today's plan.
    return redirect(request.referrer or url_for("planning.today"))
