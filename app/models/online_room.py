import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.db.session import Base


def _generate_room_uuid() -> str:
    return str(uuid.uuid4())


class OnlineRoom(Base):
    __tablename__ = "online_rooms"
    __table_args__ = (
        Index("ix_online_rooms_status_created", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_uuid = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=_generate_room_uuid,
    )
    room_code = Column(String(12), unique=True, index=True, nullable=False)

    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    guest_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)

    host_player_name = Column(String, nullable=False)
    guest_player_name = Column(String, nullable=True)

    game_type = Column(String(20), nullable=False, index=True)
    game_variant = Column(Integer, nullable=True)
    settings = Column(JSON, nullable=False, default=lambda: {})

    status = Column(String(20), nullable=False, default="waiting", index=True)
    host_presence_state = Column(String(20), nullable=False, default="online", index=True)
    host_last_seen_at = Column(DateTime, nullable=True)
    host_disconnected_at = Column(DateTime, nullable=True)
    host_left_at = Column(DateTime, nullable=True)
    host_leave_reason = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    host = relationship("User", foreign_keys=[host_user_id])
    guest = relationship("User", foreign_keys=[guest_user_id])
    game = relationship("Game", foreign_keys=[game_id])
