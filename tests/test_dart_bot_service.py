import random

from app.models.game import Game, GamePlayer
from app.services.dart_bot_service import DartBotService


def _sample_x01_darts(difficulty: str, *, count: int = 120):
    service = DartBotService()
    return [
        service._generate_x01_dart(501, difficulty, double_out=False)
        for _ in range(count)
    ]


def test_medium_x01_darts_are_not_forced_to_double_twenty():
    random.seed(11)

    darts = _sample_x01_darts("medium")

    double_twenty_count = sum(
        dart.segment == "20" and dart.multiplier == 2 for dart in darts
    )
    unique_hits = {(dart.segment, dart.multiplier) for dart in darts}

    assert double_twenty_count < len(darts) * 0.20
    assert len(unique_hits) >= 8


def test_x01_difficulty_profiles_scale_average_score():
    service = DartBotService()

    def average_score(difficulty: str) -> float:
        random.seed(23)
        darts = [
            service._generate_x01_dart(501, difficulty, double_out=False)
            for _ in range(250)
        ]
        return sum(service._dart_score(dart) for dart in darts) / len(darts)

    assert average_score("hard") > average_score("medium") > average_score("easy")


def test_medium_double_out_checkout_is_attempted_but_not_guaranteed():
    random.seed(7)
    service = DartBotService()

    darts = [
        service._generate_x01_dart(40, "medium", double_out=True)
        for _ in range(80)
    ]
    double_twenty_count = sum(
        dart.segment == "20" and dart.multiplier == 2 for dart in darts
    )

    assert 5 < double_twenty_count < 35


def test_generate_turn_reads_double_out_setting():
    random.seed(7)
    service = DartBotService()
    game = Game(game_type="x01", game_variant=501, settings={"x01": {"double_out": True}})
    bot = GamePlayer(is_bot=True, bot_difficulty="medium", current_score=40)

    throws = service.generate_turn(game, bot)

    assert len(throws) == 3
