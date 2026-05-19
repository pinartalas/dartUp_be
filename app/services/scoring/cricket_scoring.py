from copy import deepcopy
from typing import Any, Optional

from app.core.config import CRICKET_SEGMENTS
from app.schemas.game import DartThrowInput
from app.services.scoring.base import (
    GameScoringService,
    PlayerScoringState,
    TurnScoringResult,
)


class CricketScoringService(GameScoringService):
    def create_initial_player_state(
        self,
        *,
        player_id: int,
        name: str,
        player_order: int,
        game_variant: Optional[int],
        settings: dict[str, Any],
    ) -> PlayerScoringState:
        return PlayerScoringState(
            player_id=player_id,
            name=name,
            player_order=player_order,
            cricket_marks={segment: 0 for segment in CRICKET_SEGMENTS},
            cricket_points=0,
        )

    def process_turn(
        self,
        *,
        active_player: PlayerScoringState,
        all_players: list[PlayerScoringState],
        throws: list[DartThrowInput],
        settings: dict[str, Any],
        game_variant: Optional[int],
    ) -> TurnScoringResult:
        players = deepcopy(all_players)
        player = next(p for p in players if p.player_id == active_player.player_id)
        opponents = [p for p in players if p.player_id != player.player_id]

        points_before = player.cricket_points
        computed = self.normalize_throws(throws)

        for dart in computed:
            self._apply_dart(player, opponents, dart.segment, dart.multiplier)

        points_scored = player.cricket_points - points_before
        winner_id = self._find_winner(players)

        return TurnScoringResult(
            turn_score=points_scored,
            points_scored=points_scored,
            is_bust=False,
            is_finished=winner_id is not None,
            winner_player_id=winner_id,
            updated_players=players,
        )

    def _apply_dart(
        self,
        player: PlayerScoringState,
        opponents: list[PlayerScoringState],
        segment: str,
        multiplier: int,
    ) -> None:
        segment = segment.lower().strip()
        if segment not in CRICKET_SEGMENTS:
            return

        marks = player.cricket_marks
        current = marks.get(segment, 0)
        marks_value = multiplier

        if current >= 3:
            self._score_on_opponents(player, opponents, segment, marks_value)
            return

        new_marks = current + marks_value
        if new_marks <= 3:
            marks[segment] = new_marks
            return

        marks[segment] = 3
        excess = new_marks - 3
        self._score_on_opponents(player, opponents, segment, excess)

    def _score_on_opponents(
        self,
        player: PlayerScoringState,
        opponents: list[PlayerScoringState],
        segment: str,
        marks_value: int,
    ) -> None:
        segment_value = self._segment_value(segment)
        for opponent in opponents:
            if opponent.cricket_marks.get(segment, 0) < 3:
                player.cricket_points += segment_value * marks_value

    @staticmethod
    def _segment_value(segment: str) -> int:
        if segment == "bull":
            return 25
        return int(segment)

    def _find_winner(self, players: list[PlayerScoringState]) -> Optional[int]:
        for player in players:
            if not all(player.cricket_marks.get(s, 0) >= 3 for s in CRICKET_SEGMENTS):
                continue
            if all(
                player.cricket_points >= opponent.cricket_points
                for opponent in players
                if opponent.player_id != player.player_id
            ):
                return player.player_id
        return None
