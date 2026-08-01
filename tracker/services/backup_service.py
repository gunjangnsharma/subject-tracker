"""Export / import a user's data as a standard JSON backup.

Backup format (``format: "subject-tracker-backup"``, ``version: 1``):

    {
      "format": "subject-tracker-backup",
      "version": 1,
      "exported_at": "<ISO-8601 UTC>",
      "user": {"username": "<name>"},
      "subjects": [
        {"name": "...", "modules": [
          {"name": "...", "chapters": [
            {"title": "...", "kind": "video|text",
             "duration_minutes": <int>, "completion": <0-10>,
             "plan_dates": ["YYYY-MM-DD", ...],
             "activity": [{"occurred_on": "YYYY-MM-DD", "minutes_delta": <float>}]}
          ]}
        ]}
      ]
    }

Import is **additive**: the subjects in the file are added to the current
user's account (existing data is left untouched). It is atomic — any validation
error rolls the whole import back. Completion, plan dates and activity history
are restored verbatim (import writes rows directly, so it does not generate new
activity events).

**Chapter order** travels as the order of the ``chapters`` array — there is no
``position`` field. Export lists each module's chapters in display order, and
import assigns positions sequentially as it walks the array, so a re-export
reproduces the original order exactly. This keeps hand-authored files simple
(list chapters in the order you want them) and needs no format-version bump.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from tracker import domain
from tracker.models import CHAPTER_KINDS
from tracker.repositories.activity_repository import ActivityRepository
from tracker.repositories.chapter_repository import ChapterRepository
from tracker.repositories.plan_repository import PlanRepository
from tracker.repositories.subject_repository import ModuleRepository, SubjectRepository
from tracker.services.auth_service import AuthService

BACKUP_FORMAT = "subject-tracker-backup"
BACKUP_VERSION = 2                 # v2 stores completed_minutes
SUPPORTED_VERSIONS = (1, 2)        # v1 stored completion on a 0..10 scale


@dataclass(frozen=True)
class ImportSummary:
    subjects: int
    modules: int
    chapters: int
    plans: int
    activity: int


class BackupError(ValueError):
    """Raised when an uploaded backup is malformed or unsupported."""


class BackupService:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id
        self._auth = AuthService(session)
        self._subjects = SubjectRepository(session, user_id)
        self._modules = ModuleRepository(session, user_id)
        self._chapters = ChapterRepository(session, user_id)
        self._plans = PlanRepository(session, user_id)
        self._activity = ActivityRepository(session, user_id)

    # --- Export ------------------------------------------------------------
    def export_data(self) -> dict:
        user = self._auth.get(self._user_id)
        return {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user": {"username": user.username if user else None},
            "subjects": [self._export_subject(s) for s in self._subjects.list_all()],
        }

    def _export_subject(self, subject) -> dict:
        return {
            "name": subject.name,
            "modules": [self._export_module(m) for m in subject.modules],
        }

    def _export_module(self, module) -> dict:
        return {
            # `module.chapters` is ordered by (position, id), so the array order
            # *is* the chapter order; import replays it. See the module docstring.
            "name": module.name,
            "chapters": [self._export_chapter(c) for c in module.chapters],
        }

    @staticmethod
    def _export_chapter(chapter) -> dict:
        return {
            "title": chapter.title,
            "kind": chapter.kind,
            "duration_minutes": chapter.duration_minutes,
            "completed_minutes": chapter.completed_minutes,
            "plan_dates": [a.planned_date.isoformat() for a in chapter.assignments],
            "activity": [
                {"occurred_on": e.occurred_on.isoformat(), "minutes_delta": e.minutes_delta}
                for e in chapter.events
            ],
        }

    # --- Import ------------------------------------------------------------
    def import_data(self, data) -> ImportSummary:
        self._validate_envelope(data)
        self._version = data.get("version")   # drives v1 vs v2 completion parsing
        counts = {"subjects": 0, "modules": 0, "chapters": 0, "plans": 0, "activity": 0}
        try:
            for s_index, subj in enumerate(self._require_list(data, "subjects")):
                self._import_subject(subj, s_index, counts)
            self._session.commit()
        except BackupError:
            self._session.rollback()
            raise
        except Exception as exc:  # malformed data mid-way -> undo everything
            self._session.rollback()
            raise BackupError(f"Could not import backup: {exc}") from exc
        return ImportSummary(**counts)

    def _import_subject(self, subj: dict, index: int, counts: dict) -> None:
        name = self._require_str(subj, "name", f"subjects[{index}]")
        subject = self._subjects.add(name)
        counts["subjects"] += 1
        for m_index, mod in enumerate(subj.get("modules", []) or []):
            self._import_module(subject.id, mod, f"subjects[{index}].modules[{m_index}]", counts)

    def _import_module(self, subject_id: int, mod: dict, where: str, counts: dict) -> None:
        name = self._require_str(mod, "name", where)
        module = self._modules.add(subject_id, name)
        counts["modules"] += 1
        for c_index, ch in enumerate(mod.get("chapters", []) or []):
            self._import_chapter(module.id, ch, f"{where}.chapters[{c_index}]", counts)

    def _import_chapter(self, module_id: int, ch: dict, where: str, counts: dict) -> None:
        title = self._require_str(ch, "title", where)
        kind = ch.get("kind", "video")
        if kind not in CHAPTER_KINDS:
            raise BackupError(f"{where}.kind must be one of {CHAPTER_KINDS}, got {kind!r}.")
        duration = self._require_int(ch, "duration_minutes", where, minimum=0)
        if self._version == 1:
            # v1 stored a 0..10 completion; convert to completed minutes.
            completion = max(0, min(10, self._require_int(ch, "completion", where, minimum=0)))
            completed = round(duration * completion / 10)
        else:
            completed = self._require_int(ch, "completed_minutes", where, minimum=0)
        completed = domain.clamp_completed(duration, completed)

        chapter = self._chapters.add(module_id, title, kind, duration)
        chapter.completed_minutes = completed  # set verbatim (no activity side-effect)
        counts["chapters"] += 1

        # One date per chapter: keep only the first plan date (older backups may
        # carry several; the current format emits at most one).
        plan_dates = ch.get("plan_dates", []) or []
        if plan_dates:
            self._plans.add(chapter.id, self._parse_date(plan_dates[0], where, "plan_dates"))
            counts["plans"] += 1

        for ev in ch.get("activity", []) or []:
            when = self._parse_date(ev.get("occurred_on"), where, "activity.occurred_on")
            delta = self._to_float(ev.get("minutes_delta"), where, "activity.minutes_delta")
            self._activity.add(chapter.id, when, delta)
            counts["activity"] += 1

    # --- Validation helpers ------------------------------------------------
    @staticmethod
    def _validate_envelope(data) -> None:
        if not isinstance(data, dict):
            raise BackupError("Backup must be a JSON object.")
        if data.get("format") != BACKUP_FORMAT:
            raise BackupError(f"Not a {BACKUP_FORMAT!r} file.")
        if data.get("version") not in SUPPORTED_VERSIONS:
            raise BackupError(f"Unsupported backup version: {data.get('version')!r}.")

    @staticmethod
    def _require_list(data: dict, key: str) -> list:
        value = data.get(key)
        if not isinstance(value, list):
            raise BackupError(f"'{key}' must be a list.")
        return value

    @staticmethod
    def _require_str(obj: dict, key: str, where: str) -> str:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BackupError(f"{where}.{key} is required and must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _require_int(obj: dict, key: str, where: str, minimum: int | None = None) -> int:
        value = obj.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise BackupError(f"{where}.{key} must be an integer.")
        if minimum is not None and value < minimum:
            raise BackupError(f"{where}.{key} must be >= {minimum}.")
        return value

    @staticmethod
    def _to_float(value, where: str, field: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise BackupError(f"{where}.{field} must be a number.")

    @staticmethod
    def _parse_date(value, where: str, field: str) -> date:
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            raise BackupError(f"{where}.{field} must be an ISO date (YYYY-MM-DD), got {value!r}.")
