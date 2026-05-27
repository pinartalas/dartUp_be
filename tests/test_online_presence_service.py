import asyncio
from datetime import datetime, timedelta, timezone

from app.api.routes import games as game_routes
from app.api.routes import online_rooms as online_room_routes
from app.models.game import GamePlayer
from app.schemas.game import GameType
from app.schemas.online_room import (
    CreateOnlineRoomRequest,
    JoinOnlineRoomRequest,
    LeaveOnlineGameRequest,
    OnlineLeaveReason,
    OnlineRoomStatus,
)
from app.services.online_presence_service import OnlinePresenceService
from app.services.online_room_service import OnlineRoomService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_online_game(db_session, owner, other_user):
    room_service = OnlineRoomService(db_session)
    room = room_service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )
    joined = room_service.join_room(
        room.room_code,
        other_user,
        JoinOnlineRoomRequest(),
    )
    assert joined.game_id is not None
    assert joined.game is not None
    return room, joined


def _player_for_user(db_session, game_id: int, user_id: int) -> GamePlayer:
    return (
        db_session.query(GamePlayer)
        .filter(GamePlayer.game_id == game_id, GamePlayer.user_id == user_id)
        .one()
    )


def test_leave_online_game_forfeits_and_get_returns_final_state(
    db_session,
    owner,
    other_user,
):
    room, joined = _create_online_game(db_session, owner, other_user)
    host_player = _player_for_user(db_session, joined.game_id, owner.id)
    guest_player = _player_for_user(db_session, joined.game_id, other_user.id)

    result = OnlinePresenceService(db_session).leave_game(
        joined.game_id,
        owner.id,
        OnlineLeaveReason.USER_QUIT.value,
    )

    assert result.response.game.status == "forfeited"
    assert result.response.is_finished is True
    assert result.response.winner is not None
    assert result.response.winner.player_id == guest_player.id
    assert result.response.forfeit is not None
    assert result.response.forfeit.player_id == host_player.id
    assert result.response.forfeit.reason == OnlineLeaveReason.USER_QUIT.value
    assert [event.event_type for event in result.events] == [
        "player_left",
        "game_forfeited",
    ]

    state = game_routes.get_game(joined.game_id, db_session, other_user)
    assert state.status == "forfeited"
    assert state.is_finished is True
    assert state.winner is not None
    assert state.winner.player_id == guest_player.id
    assert state.forfeit is not None
    assert state.forfeit.player_id == host_player.id
    assert state.players[0].current_score == 301

    room_state = OnlineRoomService(db_session).get_room(room.room_code, other_user.id)
    assert room_state.status == OnlineRoomStatus.FINISHED


def test_disconnect_then_reconnect_restores_online_presence(
    db_session,
    owner,
    other_user,
):
    _, joined = _create_online_game(db_session, owner, other_user)
    presence = OnlinePresenceService(db_session)

    disconnect_event = presence.mark_disconnected(joined.game_id, owner.id)
    assert disconnect_event is not None
    assert disconnect_event.event_type == "player_disconnected"

    disconnected_player = _player_for_user(db_session, joined.game_id, owner.id)
    assert disconnected_player.presence_state == "disconnected"
    assert disconnected_player.disconnected_at is not None

    reconnect_event = presence.mark_connected(joined.game_id, owner.id)
    assert reconnect_event is not None
    assert reconnect_event.event_type == "player_reconnected"

    reconnected_player = _player_for_user(db_session, joined.game_id, owner.id)
    assert reconnected_player.presence_state == "online"
    assert reconnected_player.disconnected_at is None


def test_expired_disconnect_forfeits_game_to_opponent(
    db_session,
    owner,
    other_user,
):
    _, joined = _create_online_game(db_session, owner, other_user)
    presence = OnlinePresenceService(db_session)
    presence.mark_disconnected(joined.game_id, owner.id)

    host_player = _player_for_user(db_session, joined.game_id, owner.id)
    host_player.disconnected_at = _utcnow() - timedelta(seconds=31)
    db_session.commit()

    events = presence.process_timeouts(timeout_seconds=30)

    assert [event.event_type for event in events] == [
        "player_left",
        "game_forfeited",
    ]
    state = game_routes.get_game(joined.game_id, db_session, other_user)
    assert state.status == "forfeited"
    assert state.forfeit is not None
    assert state.forfeit.player_id == host_player.id
    assert state.forfeit.reason == "timeout"


def test_stale_heartbeat_marks_player_disconnected_without_forfeit(
    db_session,
    owner,
    other_user,
):
    _, joined = _create_online_game(db_session, owner, other_user)
    presence = OnlinePresenceService(db_session)
    presence.mark_connected(joined.game_id, owner.id)

    host_player = _player_for_user(db_session, joined.game_id, owner.id)
    host_player.last_seen_at = _utcnow() - timedelta(seconds=31)
    db_session.commit()

    events = presence.process_timeouts(timeout_seconds=30)

    assert [event.event_type for event in events] == ["player_disconnected"]
    state = game_routes.get_game(joined.game_id, db_session, other_user)
    assert state.status == "active"
    assert state.players[0].presence_state == "disconnected"


def test_leave_endpoint_broadcasts_player_left_and_forfeit(
    db_session,
    owner,
    other_user,
    monkeypatch,
):
    _, joined = _create_online_game(db_session, owner, other_user)
    sent_events = []

    async def fake_send_to_game(game_id, event_type, payload, *, exclude_user_id=None):
        sent_events.append((game_id, event_type, payload, exclude_user_id))

    monkeypatch.setattr(
        online_room_routes.game_connection_manager,
        "send_to_game",
        fake_send_to_game,
    )

    response = asyncio.run(
        online_room_routes.leave_online_game(
            joined.game_id,
            LeaveOnlineGameRequest(reason=OnlineLeaveReason.LEFT_SCREEN),
            db_session,
            owner,
        )
    )

    assert response.game.status == "forfeited"
    assert [event[1] for event in sent_events] == [
        "player_left",
        "game_forfeited",
    ]
