from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.exceptions import GameServiceError, OnlineRoomError
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.online_room import (
    CreateOnlineRoomRequest,
    JoinOnlineRoomRequest,
    OnlineRoomListResponse,
    OnlineRoomResponse,
)
from app.services.game_service import GameService
from app.services.online_room_service import OnlineRoomService
from app.services.realtime_service import game_connection_manager

router = APIRouter(prefix="/online-rooms", tags=["online-rooms"])


def _handle_online_room_error(exc: OnlineRoomError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _handle_game_service_error(exc: GameServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "",
    response_model=OnlineRoomResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_online_room(
    request: CreateOnlineRoomRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return OnlineRoomService(db).create_room(current_user, request)
    except OnlineRoomError as exc:
        _handle_online_room_error(exc)


@router.get("", response_model=OnlineRoomListResponse)
def list_online_rooms(
    include_own: Annotated[bool, Query(alias="includeOwn")] = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OnlineRoomService(db).list_waiting_rooms(
        current_user.id,
        include_own=include_own,
        limit=limit,
    )


@router.get("/{room_code}", response_model=OnlineRoomResponse)
def get_online_room(
    room_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return OnlineRoomService(db).get_room(room_code, current_user.id)
    except OnlineRoomError as exc:
        _handle_online_room_error(exc)


@router.post("/{room_code}/join", response_model=OnlineRoomResponse)
async def join_online_room(
    room_code: str,
    request: JoinOnlineRoomRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        room = OnlineRoomService(db).join_room(room_code, current_user, request)
    except OnlineRoomError as exc:
        _handle_online_room_error(exc)

    if room.game_id is not None:
        await game_connection_manager.send_to_game(
            room.game_id,
            "room_joined",
            room,
        )
    return room


@router.post("/{room_code}/cancel", response_model=OnlineRoomResponse)
def cancel_online_room(
    room_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return OnlineRoomService(db).cancel_room(room_code, current_user.id)
    except OnlineRoomError as exc:
        _handle_online_room_error(exc)


@router.websocket("/games/{game_id}/ws")
async def watch_online_game(
    websocket: WebSocket,
    game_id: int,
    token: Annotated[Optional[str], Query()] = None,
):
    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db = SessionLocal()
    try:
        user_id = decode_access_token(token)
        game = GameService(db).get_game(game_id, user_id)
        initial_state = GameService(db).state_service.build_game_state(game)
    except (HTTPException, GameServiceError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    finally:
        db.close()

    await game_connection_manager.connect(game_id, websocket)
    await game_connection_manager.send_to_socket(
        websocket,
        "game_state",
        initial_state,
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        game_connection_manager.disconnect(game_id, websocket)
