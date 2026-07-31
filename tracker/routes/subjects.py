"""Routes for subjects, modules and chapters."""

from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from tracker.services.subject_service import SubjectService

bp = Blueprint("subjects", __name__)


def _service() -> SubjectService:
    return SubjectService(g.session)


@bp.get("/")
def dashboard():
    subjects = _service().list_subjects()
    return render_template("dashboard.html", subjects=subjects)


@bp.post("/subjects")
def create_subject():
    try:
        _service().add_subject(request.form.get("name", ""))
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("subjects.dashboard"))


@bp.post("/subjects/<int:subject_id>/delete")
def delete_subject(subject_id: int):
    _service().delete_subject(subject_id)
    return redirect(url_for("subjects.dashboard"))


@bp.get("/subjects/<int:subject_id>")
def subject_detail(subject_id: int):
    subject = _service().get_subject(subject_id)
    if subject is None:
        abort(404)
    return render_template("subject_detail.html", subject=subject)


@bp.post("/subjects/<int:subject_id>/modules")
def create_module(subject_id: int):
    try:
        _service().add_module(subject_id, request.form.get("name", ""))
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("subjects.subject_detail", subject_id=subject_id))


@bp.post("/modules/<int:module_id>/delete")
def delete_module(module_id: int):
    service = _service()
    module = service.get_module(module_id)  # for redirect target
    subject_id = module.subject_id if module else None
    service.delete_module(module_id)
    if subject_id is None:
        return redirect(url_for("subjects.dashboard"))
    return redirect(url_for("subjects.subject_detail", subject_id=subject_id))


@bp.post("/modules/<int:module_id>/chapters")
def create_chapter(module_id: int):
    service = _service()
    module = service.get_module(module_id)
    if module is None:
        abort(404)
    try:
        duration = int(request.form.get("duration_minutes", "0") or 0)
    except ValueError:
        duration = 0
    try:
        service.add_chapter(
            module_id,
            request.form.get("title", ""),
            request.form.get("kind", "video"),
            duration,
        )
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("subjects.subject_detail", subject_id=module.subject_id))


@bp.post("/chapters/<int:chapter_id>/completion")
def update_completion(chapter_id: int):
    service = _service()
    chapter = service.get_chapter(chapter_id)
    if chapter is None:
        abort(404)
    subject_id = chapter.module.subject_id
    try:
        value = int(request.form.get("completion", "0") or 0)
    except ValueError:
        value = 0
    service.set_completion(chapter_id, value)
    return redirect(url_for("subjects.subject_detail", subject_id=subject_id))


@bp.post("/chapters/<int:chapter_id>/delete")
def delete_chapter(chapter_id: int):
    service = _service()
    chapter = service.get_chapter(chapter_id)
    if chapter is None:
        abort(404)
    subject_id = chapter.module.subject_id
    service.delete_chapter(chapter_id)
    return redirect(url_for("subjects.subject_detail", subject_id=subject_id))
