"""Data access for Subject and Module aggregates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import Module, Subject


class SubjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, name: str) -> Subject:
        subject = Subject(name=name)
        self._session.add(subject)
        self._session.flush()
        return subject

    def get(self, subject_id: int) -> Subject | None:
        return self._session.get(Subject, subject_id)

    def list_all(self) -> list[Subject]:
        return list(self._session.scalars(select(Subject).order_by(Subject.name)))

    def delete(self, subject: Subject) -> None:
        self._session.delete(subject)


class ModuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, subject_id: int, name: str) -> Module:
        module = Module(subject_id=subject_id, name=name)
        self._session.add(module)
        self._session.flush()
        return module

    def get(self, module_id: int) -> Module | None:
        return self._session.get(Module, module_id)

    def delete(self, module: Module) -> None:
        self._session.delete(module)
