"""Data access for User."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, username: str, password_hash: str, role: str) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self._session.scalars(stmt).first()

    def list_all(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(User.username)))
