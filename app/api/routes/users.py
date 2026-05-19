from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.exceptions import GameHistoryError
from app.models.user import User
from app.schemas.game import GameStatus, GameType
from app.schemas.game_history import (
    GameHistoryListResponse,
    GameHistoryQueryParams,
    HistoryPeriod,
)
from app.services.game_history_service import GameHistoryService

router = APIRouter(prefix="/users", tags=["users"])


def _handle_history_error(exc: GameHistoryError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/me/game-history", response_model=GameHistoryListResponse)
def get_my_game_history(
    period: Annotated[Optional[HistoryPeriod], Query()] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate")] = None,
    game_type: Annotated[Optional[GameType], Query(alias="gameType")] = None,
    game_mode: Annotated[Optional[int], Query(alias="gameMode")] = None,
    status: Annotated[Optional[GameStatus], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        params = GameHistoryQueryParams(
            period=period,
            startDate=start_date,
            endDate=end_date,
            gameType=game_type,
            gameMode=game_mode,
            status=status,
            page=page,
            limit=limit,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    service = GameHistoryService(db)
    try:
        return service.get_user_game_history(current_user.id, params)
    except GameHistoryError as exc:
        _handle_history_error(exc)
