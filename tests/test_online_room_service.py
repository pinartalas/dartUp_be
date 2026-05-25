import pytest

from app.api.routes import games as game_routes
from app.api.routes import online_rooms as online_room_routes
from app.core.exceptions import GameServiceError, OnlineRoomError
from app.schemas.game import (
    CreateGameRequest,
    DartThrowInput,
    GameType,
    PlayerCreateInput,
    SubmitTurnRequest,
)
from app.schemas.online_room import (
    CreateOnlineRoomRequest,
    JoinOnlineRoomRequest,
    OnlineRoomStatus,
)
from app.services.game_service import GameService
from app.services.online_room_service import OnlineRoomService


def test_create_and_join_online_room_creates_game(db_session, owner, other_user):
    service = OnlineRoomService(db_session)

    room = service.create_room(
        owner,
        CreateOnlineRoomRequest(
            game_type=GameType.X01,
            game_variant=301,
            player_name="Host",
        ),
    )

    assert room.status == OnlineRoomStatus.WAITING
    assert room.room_code
    assert room.can_join is False

    joined = service.join_room(
        room.room_code,
        other_user,
        JoinOnlineRoomRequest(player_name="Guest"),
    )

    assert joined.status == OnlineRoomStatus.ACTIVE
    assert joined.game_id is not None
    assert joined.guest_user_id == other_user.id
    assert joined.game is not None
    assert [player.user_id for player in joined.game.players] == [
        owner.id,
        other_user.id,
    ]


def test_host_cannot_join_own_room(db_session, owner):
    service = OnlineRoomService(db_session)
    room = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )

    with pytest.raises(OnlineRoomError):
        service.join_room(room.room_code, owner, JoinOnlineRoomRequest())


def test_creating_new_online_room_cancels_previous_waiting_room(db_session, owner):
    service = OnlineRoomService(db_session)
    previous = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )

    current = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=501),
    )

    assert (
        service.get_room(previous.room_code, owner.id).status
        == OnlineRoomStatus.CANCELLED
    )
    assert current.status == OnlineRoomStatus.WAITING


def test_cancel_current_user_waiting_rooms_endpoint(db_session, owner, other_user):
    service = OnlineRoomService(db_session)
    active = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )
    active = service.join_room(
        active.room_code,
        other_user,
        JoinOnlineRoomRequest(),
    )
    other_waiting = service.create_room(
        other_user,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=501),
    )
    owner_waiting = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.CRICKET),
    )

    response = online_room_routes.cancel_current_user_waiting_rooms(db_session, owner)

    assert response.cancelled_count == 1
    assert (
        service.get_room(owner_waiting.room_code, owner.id).status
        == OnlineRoomStatus.CANCELLED
    )
    assert service.get_room(active.room_code, owner.id).status == OnlineRoomStatus.ACTIVE
    assert (
        service.get_room(other_waiting.room_code, other_user.id).status
        == OnlineRoomStatus.WAITING
    )


def test_creating_local_game_cancels_waiting_online_room(db_session, owner):
    service = OnlineRoomService(db_session)
    room = service.create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )

    game_routes.create_game(
        CreateGameRequest(
            game_type=GameType.X01,
            game_variant=501,
            players=[PlayerCreateInput(name="Local Player", user_id=owner.id)],
        ),
        db_session,
        owner,
    )

    assert (
        service.get_room(room.room_code, owner.id).status
        == OnlineRoomStatus.CANCELLED
    )


def test_online_game_turns_must_match_authenticated_player(
    db_session,
    owner,
    other_user,
):
    room = OnlineRoomService(db_session).create_room(
        owner,
        CreateOnlineRoomRequest(game_type=GameType.X01, game_variant=301),
    )
    joined = OnlineRoomService(db_session).join_room(
        room.room_code,
        other_user,
        JoinOnlineRoomRequest(),
    )
    assert joined.game is not None

    host_player = joined.game.players[0]
    guest_player = joined.game.players[1]
    throws = [
        DartThrowInput(segment="20", multiplier=1),
        DartThrowInput(segment="20", multiplier=1),
        DartThrowInput(segment="20", multiplier=1),
    ]

    game_service = GameService(db_session)
    with pytest.raises(GameServiceError):
        game_service.submit_turn(
            joined.game.id,
            other_user.id,
            SubmitTurnRequest(player_id=host_player.id, throws=throws),
        )

    game_service.submit_turn(
        joined.game.id,
        owner.id,
        SubmitTurnRequest(player_id=host_player.id, throws=throws),
    )

    with pytest.raises(GameServiceError):
        game_service.submit_turn(
            joined.game.id,
            owner.id,
            SubmitTurnRequest(player_id=guest_player.id, throws=throws),
        )
