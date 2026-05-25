from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.game import Game, GamePlayer
from app.schemas.game import GameStatus


class GameHistoryRepository:
    """Data access for finished game history queries."""

    def __init__(self, db: Session):
        self.db = db

    def count_finished_games(
        self,
        owner_id: int,
        *,
        finished_from: Optional[datetime] = None,
        finished_to: Optional[datetime] = None,
        game_type: Optional[str] = None,
        game_mode: Optional[int] = None,
        status: Optional[str] = None,
    ) -> int:
        query = self._base_query(
            owner_id,
            finished_from=finished_from,
            finished_to=finished_to,
            game_type=game_type,
            game_mode=game_mode,
            status=status,
        )
        return query.with_entities(func.count(func.distinct(Game.id))).scalar() or 0

    def list_finished_games(
        self,
        owner_id: int,
        *,
        finished_from: Optional[datetime] = None,
        finished_to: Optional[datetime] = None,
        game_type: Optional[str] = None,
        game_mode: Optional[int] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Game]:
        query = self._base_query(
            owner_id,
            finished_from=finished_from,
            finished_to=finished_to,
            game_type=game_type,
            game_mode=game_mode,
            status=status,
        )
        return (
            query.options(
                joinedload(Game.players),
                joinedload(Game.turns),
            )
            .order_by(Game.finished_at.desc(), Game.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def _base_query(
        self,
        owner_id: int,
        *,
        finished_from: Optional[datetime] = None,
        finished_to: Optional[datetime] = None,
        game_type: Optional[str] = None,
        game_mode: Optional[int] = None,
        status: Optional[str] = None,
    ):
        query = self.db.query(Game).outerjoin(
            GamePlayer,
            GamePlayer.game_id == Game.id,
        ).filter(
            or_(Game.owner_id == owner_id, GamePlayer.user_id == owner_id),
            Game.status == GameStatus.FINISHED.value,
            Game.finished_at.isnot(None),
        ).distinct()

        if status is not None:
            query = query.filter(Game.status == status)

        if finished_from is not None:
            query = query.filter(Game.finished_at >= finished_from)
        if finished_to is not None:
            query = query.filter(Game.finished_at <= finished_to)
        if game_type is not None:
            query = query.filter(Game.game_type == game_type)
        if game_mode is not None:
            query = query.filter(Game.game_variant == game_mode)

        return query
