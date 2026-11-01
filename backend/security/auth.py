"""Single local admin, memory-only expiring sessions, and a bounded login rate."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from backend.core.export_io import write_binary
from backend.core.rules_loader import StrictModel

COOKIE = "spr_admin"
SESSION_SECONDS = 1800
HASHER = PasswordHasher()


class AdminCredentials(StrictModel):
    password_hash: str
    generation: str
    created_utc: datetime


class AuthStatus(StrictModel):
    configured: bool
    authenticated: bool
    role: Literal["admin", "reviewer"]
    expires_utc: datetime | None = None


class AuthFailure(ValueError):
    pass


class RateLimited(AuthFailure):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Too many sign-in attempts. Try again after the indicated delay.")


def initialize_admin(root: Path, password: str, *, reset: bool = False) -> None:
    if not 12 <= len(password) <= 1024:
        raise AuthFailure("Use a password between 12 and 1024 characters.")
    path = root / "config/admin.json"
    if path.exists() and not reset:
        raise AuthFailure(
            "Admin is already initialized. Use the explicit reset command to replace it."
        )
    credentials = AdminCredentials(
        password_hash=HASHER.hash(password),
        generation=secrets.token_hex(16),
        created_utc=datetime.now(UTC),
    )
    # Exclusive creation prevents two initializations from replacing each other.
    if not reset:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(credentials.model_dump_json(indent=2).encode())
            handle.flush()
            os.fsync(handle.fileno())
    else:
        write_binary(path, credentials.model_dump_json(indent=2).encode())


class AuthService:
    def __init__(self, root: Path, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = root / "config/admin.json"
        self.clock = clock
        self.lock = RLock()
        self.sessions: dict[str, tuple[float, datetime, str]] = {}
        self.attempts: deque[float] = deque()

    def credentials(self) -> AdminCredentials | None:
        if not self.path.exists():
            return None
        if self.path.stat().st_mode & 0o077:
            raise AuthFailure(
                "Admin credentials must have file permissions 600. Run the admin reset CLI."
            )
        try:
            return AdminCredentials.model_validate_json(self.path.read_bytes())
        except ValueError as exc:
            raise AuthFailure("Admin configuration is invalid. Use the admin reset CLI.") from exc

    def status(self, token: str | None) -> AuthStatus:
        with self.lock:
            credentials = self.credentials()
            now = self.clock()
            self.sessions = {
                key: value
                for key, value in self.sessions.items()
                if value[0] > now and credentials and value[2] == credentials.generation
            }
            session = (
                self.sessions.get(hashlib.sha256(token.encode()).hexdigest()) if token else None
            )
            return AuthStatus(
                configured=credentials is not None,
                authenticated=session is not None,
                role="admin" if session else "reviewer",
                expires_utc=session[1] if session else None,
            )

    def login(self, password: str) -> tuple[str, AuthStatus]:
        with self.lock:
            now = self.clock()
            while self.attempts and self.attempts[0] <= now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 5:
                raise RateLimited(max(1, int(61 - (now - self.attempts[0]))))
            self.attempts.append(now)
            credentials = self.credentials()
            if credentials is None:
                raise AuthFailure(
                    "Admin is not initialized. Run python -m backend.admin init locally."
                )
            if not 1 <= len(password) <= 1024:
                raise AuthFailure("Sign-in failed.")
            try:
                HASHER.verify(credentials.password_hash, password)
            except (VerificationError, InvalidHashError) as exc:
                raise AuthFailure("Sign-in failed.") from exc
            token = secrets.token_urlsafe(32)
            expires = datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (
                now + SESSION_SECONDS,
                expires,
                credentials.generation,
            )
            return token, self.status(token)

    def logout(self, token: str | None) -> None:
        with self.lock:
            if token:
                self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
