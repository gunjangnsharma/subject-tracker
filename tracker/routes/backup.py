"""Routes to export the current user's data as JSON and import it back."""

from __future__ import annotations

import json
from datetime import date

from flask import Blueprint, Response, current_app, flash, g, redirect, request, url_for

from tracker.auth import current_user
from tracker.services.backup_service import BackupError, BackupService

bp = Blueprint("backup", __name__)


@bp.before_request
def _require_login():
    if current_user() is None:
        return redirect(url_for("auth.login"))


def _service() -> BackupService:
    return BackupService(g.session, current_user().id)


@bp.get("/export")
def export():
    data = _service().export_data()
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    filename = f"subject-tracker-{current_user().username}-{date.today().isoformat()}.json"
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.post("/import")
def import_backup():
    file = request.files.get("backup")
    if file is None or not file.filename:
        flash("Please choose a JSON backup file to import.", "error")
        return redirect(url_for("subjects.index"))
    try:
        raw = file.read().decode("utf-8")
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        flash("That file is not valid JSON.", "error")
        return redirect(url_for("subjects.index"))

    try:
        summary = _service().import_data(data)
    except BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("subjects.index"))

    flash(
        f"Imported {summary.subjects} subject(s), {summary.modules} module(s), "
        f"{summary.chapters} chapter(s), {summary.plans} plan(s) and "
        f"{summary.activity} activity record(s).",
        "info",
    )
    return redirect(url_for("subjects.index"))
