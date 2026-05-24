import random

from app.core.config import CRICKET_SEGMENTS
from app.models.game import Game, GamePlayer
from app.schemas.game import DartThrowInput


BOARD_SEGMENTS = tuple(str(segment) for segment in range(1, 21))
DARTBOARD_ORDER = (
    "20",
    "1",
    "18",
    "4",
    "13",
    "6",
    "10",
    "15",
    "2",
    "17",
    "3",
    "19",
    "7",
    "16",
    "8",
    "11",
    "14",
    "9",
    "12",
    "5",
)

DIFFICULTY_PROFILES = {
    "easy": {
        "miss_chance": 0.30,
        "accuracy": 0.35,
        "near_miss": 0.40,
        "checkout_attempt": 0.25,
    },
    "medium": {
        "miss_chance": 0.15,
        "accuracy": 0.55,
        "near_miss": 0.30,
        "checkout_attempt": 0.50,
    },
    "hard": {
        "miss_chance": 0.05,
        "accuracy": 0.78,
        "near_miss": 0.17,
        "checkout_attempt": 0.85,
    },
}

SCORING_TARGETS = {
    "easy": [
        ("20", 1, 16),
        ("19", 1, 14),
        ("18", 1, 12),
        ("17", 1, 10),
        ("16", 1, 8),
        ("20", 2, 4),
        ("19", 2, 3),
        ("18", 2, 3),
        ("20", 3, 2),
    ],
    "medium": [
        ("20", 3, 18),
        ("19", 3, 14),
        ("18", 3, 12),
        ("17", 3, 8),
        ("20", 1, 14),
        ("19", 1, 10),
        ("18", 1, 8),
        ("20", 2, 5),
        ("19", 2, 4),
        ("bull", 1, 3),
    ],
    "hard": [
        ("20", 3, 34),
        ("19", 3, 16),
        ("18", 3, 10),
        ("20", 1, 8),
        ("19", 1, 5),
        ("20", 2, 5),
        ("bull", 2, 4),
    ],
}


class DartBotService:
    def generate_turn(self, game: Game, bot_player: GamePlayer) -> list[DartThrowInput]:
        difficulty = bot_player.bot_difficulty or "medium"

        if game.game_type == "x01":
            return self._generate_x01_turn(game, bot_player, difficulty)

        if game.game_type == "cricket":
            return self._generate_cricket_turn(bot_player, difficulty)

        raise ValueError("Unsupported game type")

    def _generate_x01_turn(
        self,
        game: Game,
        bot_player: GamePlayer,
        difficulty: str,
    ) -> list[DartThrowInput]:
        throws: list[DartThrowInput] = []
        remaining_score = bot_player.current_score or 0
        double_out = bool(
            (game.settings or {}).get("x01", {}).get("double_out", False)
        )
        for _ in range(3):
            dart = self._generate_x01_dart(remaining_score, difficulty, double_out)
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
        double_out: bool,
    ) -> DartThrowInput:
        if self._should_miss(difficulty):
            return DartThrowInput(segment="miss", multiplier=1)

        checkout = self._checkout_target(remaining_score, double_out)
        if checkout and self._should_attempt_checkout(difficulty):
            return self._apply_accuracy(checkout, difficulty)

        if remaining_score <= 60:
            target = self._choose_safe_x01_target(remaining_score, double_out)
        else:
            target = self._choose_scoring_target(difficulty)

        return self._apply_accuracy(target, difficulty)

    def _checkout_target(
        self,
        remaining_score: int,
        double_out: bool,
    ) -> DartThrowInput | None:
        if remaining_score <= 0:
            return None

        if remaining_score == 50:
            return DartThrowInput(segment="bull", multiplier=2)

        if double_out:
            if remaining_score <= 40 and remaining_score % 2 == 0:
                return DartThrowInput(segment=str(remaining_score // 2), multiplier=2)
            return None

        for multiplier in (3, 2, 1):
            if remaining_score % multiplier != 0:
                continue
            segment = remaining_score // multiplier
            if 1 <= segment <= 20:
                return DartThrowInput(segment=str(segment), multiplier=multiplier)

        if remaining_score == 25:
            return DartThrowInput(segment="bull", multiplier=1)

        return None

    def _choose_safe_x01_target(
        self,
        remaining_score: int,
        double_out: bool,
    ) -> DartThrowInput:
        candidates: list[tuple[str, int, int]] = []
        for segment in BOARD_SEGMENTS:
            for multiplier in (1, 2, 3):
                score = int(segment) * multiplier
                if score >= remaining_score:
                    continue
                if double_out and remaining_score - score == 1:
                    continue
                candidates.append((segment, multiplier, self._safe_target_weight(score)))

        for segment, multiplier, score in (("bull", 1, 25), ("bull", 2, 50)):
            if score < remaining_score and not (
                double_out and remaining_score - score == 1
            ):
                candidates.append((segment, multiplier, self._safe_target_weight(score)))

        if not candidates:
            return DartThrowInput(segment="miss", multiplier=1)

        segment, multiplier, _ = random.choices(
            candidates,
            weights=[weight for _, _, weight in candidates],
        )[0]
        return DartThrowInput(segment=segment, multiplier=multiplier)

    @staticmethod
    def _safe_target_weight(score: int) -> int:
        return max(score, 1)

    def _choose_scoring_target(self, difficulty: str) -> DartThrowInput:
        targets = SCORING_TARGETS.get(difficulty, SCORING_TARGETS["medium"])
        segment, multiplier, _ = random.choices(
            targets,
            weights=[weight for _, _, weight in targets],
        )[0]
        return DartThrowInput(segment=segment, multiplier=multiplier)

    def _apply_accuracy(
        self,
        target: DartThrowInput,
        difficulty: str,
    ) -> DartThrowInput:
        profile = self._difficulty_profile(difficulty)
        roll = random.random()
        if roll < profile["accuracy"]:
            return target
        if roll < profile["accuracy"] + profile["near_miss"]:
            return self._near_miss(target)
        return self._random_dart(difficulty)

    def _near_miss(self, target: DartThrowInput) -> DartThrowInput:
        if target.segment == "miss":
            return target

        if target.segment == "bull":
            return random.choice(
                [
                    DartThrowInput(segment="bull", multiplier=1),
                    DartThrowInput(
                        segment=random.choice(BOARD_SEGMENTS),
                        multiplier=1,
                    ),
                    DartThrowInput(segment="miss", multiplier=1),
                ]
            )

        adjacent = self._adjacent_segments(target.segment)
        if target.multiplier == 1:
            return DartThrowInput(segment=random.choice(adjacent), multiplier=1)

        near_hits = [
            DartThrowInput(segment=target.segment, multiplier=1),
            DartThrowInput(segment=adjacent[0], multiplier=target.multiplier),
            DartThrowInput(segment=adjacent[1], multiplier=target.multiplier),
            DartThrowInput(segment=adjacent[0], multiplier=1),
            DartThrowInput(segment=adjacent[1], multiplier=1),
        ]
        return random.choice(near_hits)

    @staticmethod
    def _adjacent_segments(segment: str) -> tuple[str, str]:
        if segment not in DARTBOARD_ORDER:
            return (str(max(int(segment) - 1, 1)), str(min(int(segment) + 1, 20)))
        index = DARTBOARD_ORDER.index(segment)
        return (
            DARTBOARD_ORDER[(index - 1) % len(DARTBOARD_ORDER)],
            DARTBOARD_ORDER[(index + 1) % len(DARTBOARD_ORDER)],
        )

    def _random_dart(self, difficulty: str) -> DartThrowInput:
        return DartThrowInput(
            segment=random.choice(BOARD_SEGMENTS),
            multiplier=self._choose_multiplier(difficulty),
        )

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
        miss_chance = DartBotService._difficulty_profile(difficulty)["miss_chance"]
        return random.random() < miss_chance

    @staticmethod
    def _should_attempt_checkout(difficulty: str) -> bool:
        chance = DartBotService._difficulty_profile(difficulty)["checkout_attempt"]
        return random.random() < chance

    @staticmethod
    def _difficulty_profile(difficulty: str) -> dict[str, float]:
        return DIFFICULTY_PROFILES.get(difficulty, DIFFICULTY_PROFILES["medium"])

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
