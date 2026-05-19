from copy import deepcopy
from typing import Any, Optional

from app.schemas.game import DartThrowInput
from app.services.scoring.base import (
    ComputedThrow,
    GameScoringService,
    PlayerScoringState,
    TurnScoringResult,
)


class X01ScoringService(GameScoringService):
    def create_initial_player_state(
        self,
        *,
        player_id: int,
        name: str,
        player_order: int,
        game_variant: Optional[int],
        settings: dict[str, Any],
    ) -> PlayerScoringState:
        if game_variant is None:
            raise ValueError("x01 game requires game_variant")
        return PlayerScoringState(
            player_id=player_id,
            name=name,
            player_order=player_order,
            current_score=game_variant,
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
        computed = self.normalize_throws(throws)
        x01_settings = settings.get("x01", {}) if settings else {}
        double_out = bool(x01_settings.get("double_out", False))
        double_in = bool(x01_settings.get("double_in", False))

        players = deepcopy(all_players)
        player = next(p for p in players if p.player_id == active_player.player_id)

        score_before = player.current_score or 0
        score = score_before
        turn_total = 0
        scoring_open = not double_in or player.has_double_in

        for dart in computed:
            if double_in and not scoring_open:
                if self._is_double_in_dart(dart):
                    scoring_open = True
                    player.has_double_in = True
                else:
                    continue

            turn_total += dart.score
            score -= dart.score

            if score < 0:
                return self._bust_result(
                    player=player,
                    players=players,
                    score_before=score_before,
                    score_after=score,
                    turn_total=turn_total,
                )

            if double_out and score == 1:
                return self._bust_result(
                    player=player,
                    players=players,
                    score_before=score_before,
                    score_after=score,
                    turn_total=turn_total,
                )

            if score == 0:
                if double_out and not self._is_valid_finish_dart(dart):
                    return self._bust_result(
                        player=player,
                        players=players,
                        score_before=score_before,
                        score_after=score,
                        turn_total=turn_total,
                    )
                player.current_score = 0
                return TurnScoringResult(
                    turn_score=turn_total,
                    score_before=score_before,
                    score_after=0,
                    is_bust=False,
                    is_finished=True,
                    winner_player_id=player.player_id,
                    updated_players=players,
                )

        if double_in and not player.has_double_in:
            return TurnScoringResult(
                turn_score=0,
                score_before=score_before,
                score_after=score_before,
                is_bust=False,
                updated_players=players,
            )

        player.current_score = score
        return TurnScoringResult(
            turn_score=turn_total,
            score_before=score_before,
            score_after=score,
            is_bust=False,
            updated_players=players,
        )

    @staticmethod
    def _bust_result(
        *,
        player: PlayerScoringState,
        players: list[PlayerScoringState],
        score_before: int,
        score_after: int,
        turn_total: int,
    ) -> TurnScoringResult:
        player.current_score = score_before
        return TurnScoringResult(
            turn_score=turn_total,
            score_before=score_before,
            score_after=score_after,
            is_bust=True,
            updated_players=players,
        )

    @staticmethod
    def _is_double_in_dart(dart: ComputedThrow) -> bool:
        if dart.score <= 0:
            return False
        if dart.segment == "bull" and dart.multiplier == 2:
            return True
        return dart.multiplier == 2

    @staticmethod
    def _is_valid_finish_dart(dart: ComputedThrow) -> bool:
        if dart.score == 0:
            return False
        if dart.segment == "bull" and dart.multiplier == 2:
            return True
        return dart.multiplier == 2
