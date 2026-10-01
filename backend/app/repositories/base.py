from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


class Repository(Generic[T]):
    def __init__(self, session: Session) -> None:
        self.session = session
