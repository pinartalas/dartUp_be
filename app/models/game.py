import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def _generate_game_uuid() -> str:
    return str(uuid.uuid4())


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        Index("ix_games_owner_status_finished", "owner_id", "status", "finished_at"),
        Index("ix_games_finished_at", "finished_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    game_uuid = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=_generate_game_uuid,
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    game_type = Column(String(20), nullable=False, index=True)
    game_variant = Column(Integer, nullable=True)
    settings = Column(JSON, nullable=False, default=lambda: {})

    status = Column(String(20), nullable=False, default="active", index=True)
    current_player_id = Column(Integer, ForeignKey("game_players.id"), nullable=True)
    winner_player_id = Column(Integer, ForeignKey("game_players.id"), nullable=True)
    turn_sequence = Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    owner = relationship("User", back_populates="games", foreign_keys=[owner_id])
    players = relationship(
        "GamePlayer",
        back_populates="game",
        foreign_keys="GamePlayer.game_id",
        cascade="all, delete-orphan",
        order_by="GamePlayer.player_order",
    )
    turns = relationship(
        "Turn",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Turn.turn_number",
    )
    current_player = relationship(
        "GamePlayer",
        foreign_keys=[current_player_id],
        post_update=True,
    )
    winner_player = relationship(
        "GamePlayer",
        foreign_keys=[winner_player_id],
        post_update=True,
    )


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (
        UniqueConstraint("game_id", "player_order", name="uq_game_player_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name = Column(String, nullable=False)
    player_order = Column(Integer, nullable=False)

    is_bot = Column(Boolean, nullable=False, default=False)
    bot_difficulty = Column(String(20), nullable=True)

    current_score = Column(Integer, nullable=True)
    cricket_state = Column(JSON, nullable=True)

    total_darts_thrown = Column(Integer, nullable=False, default=0)
    total_points_scored = Column(Integer, nullable=False, default=0)
    is_winner = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    game = relationship("Game", back_populates="players", foreign_keys=[game_id])
    turns = relationship("Turn", back_populates="player", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint("game_id", "turn_number", name="uq_game_turn_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("game_players.id"), nullable=False, index=True)

    turn_number = Column(Integer, nullable=False)
    turn_score = Column(Integer, nullable=False, default=0)
    score_before = Column(Integer, nullable=True)
    score_after = Column(Integer, nullable=True)
    points_scored = Column(Integer, nullable=True)
    is_bust = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    game = relationship("Game", back_populates="turns")
    player = relationship("GamePlayer", back_populates="turns")
    throws = relationship(
        "DartThrow",
        back_populates="turn",
        cascade="all, delete-orphan",
        order_by="DartThrow.throw_order",
    )


class DartThrow(Base):
    __tablename__ = "dart_throws"

    id = Column(Integer, primary_key=True, index=True)
    turn_id = Column(Integer, ForeignKey("turns.id"), nullable=False, index=True)

    throw_order = Column(Integer, nullable=False)
    segment = Column(String(10), nullable=False)
    multiplier = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    turn = relationship("Turn", back_populates="throws")
