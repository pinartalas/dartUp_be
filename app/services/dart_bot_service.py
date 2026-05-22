import random

from app.core.config import CRICKET_SEGMENTS
from app.models.game import Game, GamePlayer
from app.schemas.game import DartThrowInput


class DartBotService:
    def generate_turn(self, game: Game, bot_player: GamePlayer) -> list[DartThrowInput]:
        difficulty = bot_player.bot_difficulty or "medium"

        if game.game_type == "x01":
            return self._generate_x01_turn(bot_player, difficulty)

        if game.game_type == "cricket":
            return self._generate_cricket_turn(bot_player, difficulty)

        raise ValueError("Unsupported game type")

    def _generate_x01_turn(
        self,
        bot_player: GamePlayer,
        difficulty: str,
    ) -> list[DartThrowInput]:
        throws: list[DartThrowInput] = []
        remaining_score = bot_player.current_score or 0
        for _ in range(3):
            dart = self._generate_x01_dart(remaining_score, difficulty)
            throws.append(dart)
            remaining_score -= self._dart_score(dart)

            if remaining_score <= 0:
                break

        return self._fill_with_misses(throws)

    def _generate_cricket_turn(
        self,
        bot_player: GamePlayer,
        difficulty: str,
    ) -> list[DartThrowInput]:
        cricket_state = bot_player.cricket_state or {}
        marks = cricket_state.get("marks", {})

        open_segments = [
            segment
            for segment in CRICKET_SEGMENTS
            if marks.get(segment, 0) < 3
        ]

        target_segments = open_segments or list(CRICKET_SEGMENTS)

        return [
            self._generate_cricket_dart(target_segments, difficulty)
            for _ in range(3)
        ]

    def _generate_x01_dart(
        self,
        remaining_score: int,
        difficulty: str,
    ) -> DartThrowInput:
        if self._should_miss(difficulty):
            return DartThrowInput(segment="miss", multiplier=1)

        if remaining_score <= 40 and remaining_score % 2 == 0:
            return DartThrowInput(segment=str(remaining_score // 2), multiplier=2)

        if remaining_score >= 60 and difficulty == "hard":
            return DartThrowInput(segment="20", multiplier=3)

        if remaining_score >= 40 and difficulty in ("medium", "hard"):
            return DartThrowInput(segment="20", multiplier=2)

        segment = str(random.randint(1, 20))
        multiplier = self._choose_multiplier(difficulty)
        return DartThrowInput(segment=segment, multiplier=multiplier)

    def _generate_cricket_dart(
        self,
        target_segments: list[str],
        difficulty: str,
    ) -> DartThrowInput:
        if self._should_miss(difficulty):
            return DartThrowInput(segment="miss", multiplier=1)

        segment = random.choice(target_segments)
        multiplier = self._choose_multiplier(difficulty)

        if segment == "bull" and multiplier == 3:
            multiplier = 2

        return DartThrowInput(segment=segment, multiplier=multiplier)

    @staticmethod
    def _choose_multiplier(difficulty: str) -> int:
        if difficulty == "easy":
            return random.choices([1, 2, 3], weights=[75, 20, 5])[0]
        if difficulty == "hard":
            return random.choices([1, 2, 3], weights=[25, 35, 40])[0]

        return random.choices([1, 2, 3], weights=[50, 30, 20])[0]

    @staticmethod
    def _should_miss(difficulty: str) -> bool:
        miss_chance_by_difficulty = {
            "easy": 0.30,
            "medium": 0.15,
            "hard": 0.05,
        }
        miss_chance = miss_chance_by_difficulty.get(difficulty, 0.15)
        return random.random() < miss_chance

    @staticmethod
    def _dart_score(dart: DartThrowInput) -> int:
        if dart.segment == "miss":
            return 0
        if dart.segment == "bull":
            return 50 if dart.multiplier == 2 else 25
        return int(dart.segment) * dart.multiplier

    @staticmethod
    def _fill_with_misses(
        throws: list[DartThrowInput],
    ) -> list[DartThrowInput]:
        while len(throws) < 3:
            throws.append(DartThrowInput(segment="miss", multiplier=1))
        return throws
