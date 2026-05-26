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
import pytest
from pydantic import ValidationError


def test_legs_match_stays_active_until_target_wins(db_session, owner):
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
    assert first_leg.game.players[0].current_score == 301
    assert first_leg.game.settings["match"]["hand_wins"][str(player_id)] == 1

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

def test_legs_match_requires_target_wins():
    with pytest.raises(ValidationError):
        GameSettings(match=MatchSettings(mode=MatchMode.LEGS))


def test_off_match_rejects_target_wins():
    with pytest.raises(ValidationError):
        GameSettings(match=MatchSettings(mode=MatchMode.OFF, target_wins=2))