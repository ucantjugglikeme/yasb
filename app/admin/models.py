from dataclasses import dataclass
from hashlib import sha256
from typing import Optional
from aiohttp_session import Session

from app.store.database.sqlalchemy_base import db
from sqlalchemy import (
    Column,
    Integer,
    VARCHAR
)


@dataclass
class Admin:
    id: int
    email: str
    password: Optional[str] = None

    def is_password_valid(self, password: str):
        return self.password == sha256(password.encode()).hexdigest()

    @classmethod
    def from_session(cls, session: Optional[Session]) -> Optional["Admin"]:
        return cls(id=session["admin"]["id"], email=session["admin"]["email"])


class AdminModel(db):
    __tablename__ = "Admin"
    id = Column(Integer, primary_key=True)
    email = Column(VARCHAR(50), nullable=False, unique=True)
    password = Column(VARCHAR(64), nullable=False)
