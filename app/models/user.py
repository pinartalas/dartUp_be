from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=True)
    full_name = Column(String, nullable=True)
    username = Column(String(30), unique=True, index=True, nullable=True)
    profile_photo_url = Column(String(2048), nullable=True)
    username_changed_at = Column(DateTime, nullable=True)
    auth_provider = Column(String, nullable=False)
    provider_user_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    games = relationship("Game", back_populates="owner")
