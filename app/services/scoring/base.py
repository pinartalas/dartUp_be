from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.schemas.game import DartThrowInput


@dataclass
class ComputedThrow:
    segment: str
    multiplier: int
    score: int
    throw_order: int


@dataclass
class PlayerScoringState:
    player_id: int
    name: str
    player_order: int
    current_score: Optional[int] = None
    cricket_marks: dict[str, int] = field(default_factory=dict)
    cricket_points: int = 0
    has_double_in: bool = False


@dataclass
class TurnScoringResult:
    turn_score: int
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    points_scored: Optional[int] = None
    is_bust: bool = False
    is_finished: bool = False
    winner_player_id: Optional[int] = None
    updated_players: list[PlayerScoringState] = field(default_factory=list)


class GameScoringService(ABC):
    @abstractmethod
    def create_initial_player_state(
        self,
        *,
        player_id: int,
        name: str,
        player_order: int,
        game_variant: Optional[int],
        settings: dict[str, Any],
    ) -> PlayerScoringState:
        pass

    @abstractmethod
    def process_turn(
        self,
        *,
        active_player: PlayerScoringState,
        all_players: list[PlayerScoringState],
        throws: list[DartThrowInput],
        settings: dict[str, Any],
        game_variant: Optional[int],
    ) -> TurnScoringResult:
        pass

    @staticmethod
    def compute_dart_score(segment: str, multiplier: int) -> int:
        segment = segment.lower().strip()
        if segment in ("miss", "0", ""):
            return 0
        if segment == "bull":
            if multiplier == 1:
                return 25
            if multiplier >= 2:
                return 50
            return 0
        if segment.isdigit():
            return int(segment) * multiplier
        return 0

    @staticmethod
    def normalize_throws(throws: list[DartThrowInput]) -> list[ComputedThrow]:
        return [
            ComputedThrow(
                segment=t.segment.lower().strip(),
                multiplier=t.multiplier,
                score=GameScoringService.compute_dart_score(t.segment, t.multiplier),
                throw_order=index + 1,
            )
            for index, t in enumerate(throws)
        ]
