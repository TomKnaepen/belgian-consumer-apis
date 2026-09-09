"""Credential resolution.

Every client accepts each credential as either a plain value or a
zero-argument callable, and resolves it per request. Hosts whose configuration
can change at runtime pass a callable so a freshly entered value applies
immediately; a script passes the string it read from the environment.

Resolving once at construction time is the mistake this module exists to make
hard: it silently pins a rotated token or a re-pasted cookie to its startup
value.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from .errors import CredentialMissing

Credential: TypeAlias = "str | Callable[[], str] | None"


def resolve(credential: Credential, name: str, *, required: bool = True) -> str:
    value = credential() if callable(credential) else credential
    value = (value or "").strip()
    if not value and required:
        raise CredentialMissing(
            f"{name} is not set. See docs/reverse-engineering for how to obtain it."
        )
    return value


def from_env(*names: str) -> Callable[[], str]:
    """Read the first of *names* that is set, at call time."""

    def read() -> str:
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        return ""

    return read


class TokenStore:
    """A JSON file mapping a user key to a credential.

    Reads are per call so an externally rewritten file is picked up without a
    restart. Writes are atomic and the file is kept owner-only, because for
    Pluxee the value in it is the only thing standing between the caller and a
    manual browser re-authentication.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_all(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, user: str) -> str:
        return self.read_all().get(user.lower(), "")

    def reader(self, user: str) -> Callable[[], str]:
        return lambda: self.get(user)

    def set(self, user: str, token: str) -> None:
        data = self.read_all()
        data[user.lower()] = token
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
