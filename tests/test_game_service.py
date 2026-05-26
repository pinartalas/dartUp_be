import pytest
from pydantic import ValidationError

from app.core.exceptions import GameServiceError
from app.schemas.game import (
    CreateGameRequest,
    DartThrowInput,
    GameSettings,
    GameType,
    MatchMode,
    MatchSettings,
    PlayerCreateInput,
    SubmitTurnRequest,
)
from app.services.game_service import GameService


def test_legs_match_waits_for_continue_until_target_wins(db_session, owner):
    service = GameService(db_session)
    game = service.create_game(
        owner,
        CreateGameRequest(
            game_type=GameType.X01,
            game_variant=301,
            players=[PlayerCreateInput(name="Player", user_id=owner.id)],
            settings=GameSettings(
                match=MatchSettings(mode=MatchMode.LEGS, target_wins=2),
            ),
        ),
    )
    player_id = game.players[0].id

    score_180 = [
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
    ]
    finish_121 = [
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="1", multiplier=1),
    ]

    service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=player_id, throws=score_180),
    )
    first_leg = service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=player_id, throws=finish_121),
    )

    assert first_leg.is_finished is False
    assert first_leg.game.status == "active"
    assert first_leg.game.current_player_id is None
    assert first_leg.game.players[0].current_score == 0
    assert first_leg.game.settings["match"]["pending_next_leg"] is True
    assert first_leg.game.settings["match"]["hand_wins"][str(player_id)] == 1
    assert first_leg.game.settings["match"]["completed_legs"][0]["winner_player_id"] == player_id
    assert first_leg.game.settings["match"]["completed_legs"][0]["players"][0][
        "points_scored"
    ] == 301

    with pytest.raises(GameServiceError):
        service.submit_turn(
            game.id,
            owner.id,
            SubmitTurnRequest(player_id=player_id, throws=score_180),
        )

    continued = service.continue_next_leg(game.id, owner.id)
    assert continued.current_player_id == player_id
    assert continued.players[0].current_score == 301
    assert continued.settings["match"]["pending_next_leg"] is False
    assert continued.settings["match"]["current_hand"] == 2

    service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=player_id, throws=score_180),
    )
    final_leg = service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=player_id, throws=finish_121),
    )

    assert final_leg.is_finished is True
    assert final_leg.game.status == "finished"
    assert final_leg.winner is not None
    assert final_leg.winner.player_id == player_id
    assert final_leg.game.settings["match"]["hand_wins"][str(player_id)] == 2


def test_cancel_pending_leg_finishes_with_current_leader(db_session, owner):
    service = GameService(db_session)
    game = service.create_game(
        owner,
        CreateGameRequest(
            game_type=GameType.X01,
            game_variant=301,
            players=[
                PlayerCreateInput(name="Leader", user_id=owner.id),
                PlayerCreateInput(name="Opponent"),
            ],
            settings=GameSettings(
                match=MatchSettings(mode=MatchMode.LEGS, target_wins=2),
            ),
        ),
    )
    leader_id = game.players[0].id
    opponent_id = game.players[1].id
    score_180 = [
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
    ]
    finish_121 = [
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="20", multiplier=3),
        DartThrowInput(segment="1", multiplier=1),
    ]
    miss_turn = [
        DartThrowInput(segment="miss", multiplier=1),
        DartThrowInput(segment="miss", multiplier=1),
        DartThrowInput(segment="miss", multiplier=1),
    ]

    service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=leader_id, throws=score_180),
    )
    service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=opponent_id, throws=miss_turn),
    )
    first_leg = service.submit_turn(
        game.id,
        owner.id,
        SubmitTurnRequest(player_id=leader_id, throws=finish_121),
    )

    assert first_leg.game.settings["match"]["pending_next_leg"] is True

    cancelled = service.cancel_next_leg(game.id, owner.id)

    assert cancelled.status == "finished"
    assert cancelled.winner_player_id == leader_id
    assert cancelled.settings["match"]["pending_next_leg"] is False
    assert cancelled.settings["match"]["cancelled_after_hand"] == 1


def test_legs_match_requires_target_wins():
    with pytest.raises(ValidationError):
        GameSettings(match=MatchSettings(mode=MatchMode.LEGS))


def test_off_match_rejects_target_wins():
    with pytest.raises(ValidationError):
        GameSettings(match=MatchSettings(mode=MatchMode.OFF, target_wins=2))