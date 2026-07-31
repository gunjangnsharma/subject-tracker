"""Authentication use-cases: register and verify users.

Passwords are hashed with Werkzeug (PBKDF2). Plain passwords are never stored.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from tracker.models import USER_ROLES, User
from tracker.repositories.user_repository import UserRepository

MIN_PASSWORD_LEN = 6


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)

    def register(self, username: str, password: str, role: str = "user") -> User:
        username = (username or "").strip()
        if not username:
            raise ValueError("Username is required.")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
        if role not in USER_ROLES:
            raise ValueError(f"role must be one of {USER_ROLES}.")
        if self._users.get_by_username(username) is not None:
            raise ValueError("That username is already taken.")
        user = self._users.add(username, generate_password_hash(password), role)
        self._session.commit()
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        user = self._users.get_by_username((username or "").strip())
        if user is None:
            return None
        if not check_password_hash(user.password_hash, password or ""):
            return None
        return user

    def get(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def list_users(self) -> list[User]:
        return self._users.list_all()
