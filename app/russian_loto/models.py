from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from app.store.database.sqlalchemy_base import db
from sqlalchemy import (
    Column,
    Integer,
    VARCHAR,
    DATETIME,
    BOOLEAN,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import relationship


@dataclass
class GameSession:
    chat_id: int
    start_date: datetime
    last_event_date: datetime
    type: str = "simple"
    status: str = "started"


@dataclass
class Player:
    id: int
    name: str
    times_won: int
    times_led: int
    times_played: int


@dataclass
class Barrel:
    id: int
    bag_id: int
    barrel_number: int


@dataclass
class SessionPlayer:
    session_id: int
    player_id: int
    card_number: Optional[int]
    role: str = "lead"


@dataclass
class CardCell:
    # id: int
    session_id: int
    player_id: int
    row_index: int
    cell_index: int
    barrel_number: Optional[int]
    is_covered: bool = False


class GameSessionModel(db):
    __tablename__ = "Session"
    chat_id = Column(Integer, primary_key=True, autoincrement=False)
    type = Column(VARCHAR(45), nullable=False, default="simple")
    status = Column(VARCHAR(45), nullable=False, default="started")
    start_date = Column(DATETIME, nullable=False)
    last_event_date = Column(DATETIME, nullable=False)
    barrel = relationship("BarrelModel")
    session_player = relationship("SessionPlayerModel")

    def __repr__(self) -> str:
        return f"<GameSessionModel(chat_id='{self.chat_id}', type='{self.type}', status='{self.status}', " \
               f"start_date='{self.start_date}', last_event_date='{self.last_event_date}')>"


class PlayerModel(db):
    __tablename__ = "Player"
    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(VARCHAR(45), nullable=False)
    times_won = Column(Integer, nullable=False, default=0)
    times_led = Column(Integer, nullable=False, default=0)
    times_played = Column(Integer, nullable=False, default=0)
    session_player = relationship("SessionPlayerModel")

    def __repr__(self) -> str:
        return f"<PlayerModel(id='{self.id}', name='{self.name}', times_won='{self.times_won}', " \
               f"times_led='{self.times_led}', times_played='{self.times_played}')>"


class BarrelModel(db):
    __tablename__ = "Barrel"
    id = Column(Integer, primary_key=True)
    bag_id = Column(Integer, ForeignKey("Session.chat_id", ondelete="CASCADE"), nullable=False)
    barrel_number = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<BarrelModel(id='{self.id}', bag_id='{self.bag_id}', barrel_number='{self.barrel_number}')>"


class SessionPlayerModel(db):
    __tablename__ = "SessionPlayer"
    session_id = Column(Integer, ForeignKey("Session.chat_id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(Integer, ForeignKey("Player.id", ondelete="CASCADE"), primary_key=True)
    role = Column(VARCHAR(45), nullable=False, default="lead")
    card_number = Column(Integer, nullable=True)
    # card_cell = relationship("CardCellModel")

    def __repr__(self) -> str:
        return f"<SessionPlayerModel(session_id='{self.session_id}', player_id='{self.player_id}', " \
               f"role='{self.role}', card_number='{self.card_number}')>"


class CardCellModel(db):
    __tablename__ = "CardCell"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("SessionPlayer.session_id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("SessionPlayer.player_id", ondelete="CASCADE"), nullable=False)
    row_index = Column(Integer, nullable=False)
    cell_index = Column(Integer, nullable=False)
    barrel_number = Column(Integer, nullable=True)
    is_covered = Column(BOOLEAN, nullable=False, default=False)

    session = relationship("SessionPlayerModel", foreign_keys=[session_id])
    player = relationship("SessionPlayerModel", foreign_keys=[player_id])

    __table_args__ = (UniqueConstraint("session_id", "player_id", "row_index", "cell_index", name="_card_uc_"), )

    def __repr__(self) -> str:
        return f"<CardCellModel(id='{self.id}', session_id='{self.session_id}', player_id='{self.player_id}', " \
               f"row_index='{self.row_index}', cell_index='{self.cell_index}', barrel_number='{self.barrel_number}', " \
               f"is_covered='{self.is_covered}')>"
