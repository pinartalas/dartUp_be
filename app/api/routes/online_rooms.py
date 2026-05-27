import json
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
    LeaveOnlineGameRequest,
    OnlineGameLeaveResponse,
    OnlineRoomCleanupResponse,
    OnlineRoomListResponse,
    OnlineRoomResponse,
)
from app.services.game_service import GameService
from app.services.online_room_service import OnlineRoomService
from app.services.online_presence_service import OnlinePresenceService, PresenceEvent
from app.services.realtime_service import game_connection_manager

router = APIRouter(prefix="/online-rooms", tags=["online-rooms"])


def _handle_online_room_error(exc: OnlineRoomError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _handle_game_service_error(exc: GameServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


async def _broadcast_presence_events(events: list[PresenceEvent]) -> None:
    for event in events:
        await game_connection_manager.send_to_game(
            event.game_id,
            event.event_type,
            event.payload,
            exclude_user_id=event.exclude_user_id,
        )


def _is_heartbeat_message(message: str) -> bool:
    if message in {"heartbeat", "ping"}:
        return True
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return False
    if isinstance(data, str):
        return data in {"heartbeat", "ping"}
    if not isinstance(data, dict):
        return False
    return data.get("type") in {"heartbeat", "ping"}


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


@router.post("/current/cancel", response_model=OnlineRoomCleanupResponse)
def cancel_current_user_waiting_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cancelled_count = OnlineRoomService(db).cancel_waiting_rooms_for_user(
        current_user.id,
    )
    return OnlineRoomCleanupResponse(cancelled_count=cancelled_count)


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


@router.post("/games/{game_id}/leave", response_model=OnlineGameLeaveResponse)
async def leave_online_game(
    game_id: int,
    request: LeaveOnlineGameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = OnlinePresenceService(db).leave_game(
            game_id,
            current_user.id,
            request.reason.value,
        )
    except OnlineRoomError as exc:
        _handle_online_room_error(exc)

    await _broadcast_presence_events(result.events)
    return result.response


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
        GameService(db).get_game(game_id, user_id)
    except (HTTPException, GameServiceError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    finally:
        db.close()

    await game_connection_manager.connect(game_id, user_id, websocket)

    db = SessionLocal()
    try:
        reconnect_event = OnlinePresenceService(db).mark_connected(game_id, user_id)
        game = GameService(db).get_game(game_id, user_id)
        initial_state = GameService(db).state_service.build_game_state(game)
    except (GameServiceError, OnlineRoomError):
        game_connection_manager.disconnect(game_id, user_id, websocket)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    finally:
        db.close()

    if reconnect_event is not None:
        await _broadcast_presence_events([reconnect_event])

    await game_connection_manager.send_to_socket(
        websocket,
        "game_state",
        initial_state,
    )

    try:
        while True:
            message = await websocket.receive_text()
            if not _is_heartbeat_message(message):
                continue

            db = SessionLocal()
            try:
                OnlinePresenceService(db).heartbeat(game_id, user_id)
            finally:
                db.close()
    except WebSocketDisconnect:
        should_mark_disconnected = game_connection_manager.disconnect(
            game_id,
            user_id,
            websocket,
        )
        if not should_mark_disconnected:
            return

        db = SessionLocal()
        try:
            disconnect_event = OnlinePresenceService(db).mark_disconnected(
                game_id,
                user_id,
            )
        finally:
            db.close()

        if disconnect_event is not None:
            await _broadcast_presence_events([disconnect_event])
