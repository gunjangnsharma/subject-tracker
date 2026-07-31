"""Data access for Subject and Module aggregates, scoped to one user.

Every query is filtered by ``user_id`` and ``get`` enforces ownership (returns
None for another user's row), so a user can never read or mutate data they do
not own even by guessing an id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import Module, Subject


class SubjectRepository:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def add(self, name: str) -> Subject:
        subject = Subject(name=name, user_id=self._user_id)
        self._session.add(subject)
        self._session.flush()
        return subject

    def get(self, subject_id: int) -> Subject | None:
        subject = self._session.get(Subject, subject_id)
        if subject is None or subject.user_id != self._user_id:
            return None
        return subject

    def list_all(self) -> list[Subject]:
        stmt = (
            select(Subject)
            .where(Subject.user_id == self._user_id)
            .order_by(Subject.name)
        )
        return list(self._session.scalars(stmt))

    def delete(self, subject: Subject) -> None:
        self._session.delete(subject)


class ModuleRepository:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def add(self, subject_id: int, name: str) -> Module:
        module = Module(subject_id=subject_id, name=name)
        self._session.add(module)
        self._session.flush()
        return module

    def get(self, module_id: int) -> Module | None:
        module = self._session.get(Module, module_id)
        if module is None or module.subject.user_id != self._user_id:
            return None
        return module

    def delete(self, module: Module) -> None:
        self._session.delete(module)
