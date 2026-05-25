from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.exceptions import GameServiceError
from app.models.user import User
from app.schemas.game import (
    CreateGameRequest,
    GameStateResponse,
    GameStatsResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
)
from app.services.game_service import GameService
from app.services.game_state_service import GameStateService
from app.services.online_room_service import OnlineRoomService
from app.services.realtime_service import game_connection_manager

router = APIRouter(prefix="/games", tags=["games"])


def _handle_service_error(exc: GameServiceError):
    from fastapi import HTTPException

    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("", response_model=GameStateResponse, status_code=status.HTTP_201_CREATED)
def create_game(
    request: CreateGameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = GameService(db)
    try:
        game = service.create_game(current_user, request)
    except GameServiceError as exc:
        _handle_service_error(exc)
    state_service = GameStateService()
    return state_service.build_game_state(game)


@router.get("/{game_id}", response_model=GameStateResponse)
def get_game(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = GameService(db)
    try:
        game = service.get_game(game_id, current_user.id)
    except GameServiceError as exc:
        _handle_service_error(exc)
    return GameStateService().build_game_state(game)


@router.post("/{game_id}/turns", response_model=SubmitTurnResponse)
async def submit_turn(
    game_id: int,
    request: SubmitTurnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = GameService(db)
    try:
        result = service.submit_turn(game_id, current_user.id, request)
    except GameServiceError as exc:
        _handle_service_error(exc)

    OnlineRoomService(db).mark_finished_if_game_finished(game_id, result.is_finished)
    await game_connection_manager.send_to_game(
        game_id,
        "turn_submitted",
        result,
    )
    return result


@router.post("/{game_id}/bot-turn", response_model=SubmitTurnResponse)
async def submit_bot_turn(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = GameService(db)
    try:
        result = service.submit_bot_turn(game_id, current_user.id)
    except GameServiceError as exc:
        _handle_service_error(exc)

    OnlineRoomService(db).mark_finished_if_game_finished(game_id, result.is_finished)
    await game_connection_manager.send_to_game(
        game_id,
        "turn_submitted",
        result,
    )
    return result


@router.get("/{game_id}/stats", response_model=GameStatsResponse)
def get_game_stats(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = GameService(db)
    try:
        game = service.get_game(game_id, current_user.id)
    except GameServiceError as exc:
        _handle_service_error(exc)
    return GameStateService().build_stats(game)
