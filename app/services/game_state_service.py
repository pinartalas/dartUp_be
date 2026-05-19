from typing import Optional

from app.models.game import Game, GamePlayer, Turn
from app.schemas.game import (
    CricketStateResponse,
    GameStateResponse,
    GameStatsResponse,
    PlayerStateResponse,
    PlayerStatsResponse,
    ThrowResponse,
    TurnResultResponse,
    WinnerResponse,
)


class GameStateService:
    def build_game_state(self, game: Game) -> GameStateResponse:
        players = self._build_player_states(game)
        winner = self._build_winner(game)
        return GameStateResponse(
            id=game.id,
            game_uuid=game.game_uuid,
            game_type=game.game_type,
            game_variant=game.game_variant,
            status=game.status,
            settings=game.settings or {},
            players=players,
            current_player_id=game.current_player_id,
            turn_sequence=game.turn_sequence,
            started_at=game.started_at,
            finished_at=game.finished_at,
            is_finished=game.status == "finished",
            winner=winner,
        )

    def build_turn_result(self, turn: Turn) -> TurnResultResponse:
        return TurnResultResponse(
            turn_id=turn.id,
            turn_number=turn.turn_number,
            turn_score=turn.turn_score,
            score_before=turn.score_before,
            score_after=turn.score_after,
            points_scored=turn.points_scored,
            is_bust=turn.is_bust,
            throws=[ThrowResponse.model_validate(t) for t in turn.throws],
        )

    def build_stats(self, game: Game) -> GameStatsResponse:
        winner = self._build_winner(game)
        player_stats: list[PlayerStatsResponse] = []

        for player in sorted(game.players, key=lambda p: p.player_order):
            turns = [t for t in game.turns if t.player_id == player.id]
            turn_scores = [t.turn_score for t in turns if not t.is_bust]
            bust_count = sum(1 for t in turns if t.is_bust)
            highest = max(turn_scores, default=0)
            average = (
                round(sum(turn_scores) / len(turn_scores), 2) if turn_scores else None
            )

            player_stats.append(
                PlayerStatsResponse(
                    player_id=player.id,
                    name=player.name,
                    total_darts_thrown=player.total_darts_thrown,
                    total_points_scored=player.total_points_scored,
                    turn_count=len(turns),
                    average_per_turn=average,
                    highest_turn_score=highest,
                    bust_count=bust_count,
                    current_score=player.current_score,
                    cricket_state=self._cricket_state_from_player(player),
                )
            )

        return GameStatsResponse(
            game_id=game.id,
            game_uuid=game.game_uuid,
            game_type=game.game_type,
            game_variant=game.game_variant,
            status=game.status,
            started_at=game.started_at,
            finished_at=game.finished_at,
            winner=winner,
            total_turns=len(game.turns),
            players=player_stats,
        )

    def _build_player_states(self, game: Game) -> list[PlayerStateResponse]:
        return [
            PlayerStateResponse(
                id=player.id,
                name=player.name,
                user_id=player.user_id,
                player_order=player.player_order,
                current_score=player.current_score,
                cricket_state=self._cricket_state_from_player(player),
                total_darts_thrown=player.total_darts_thrown,
                total_points_scored=player.total_points_scored,
                is_winner=player.is_winner,
                is_active=player.id == game.current_player_id,
            )
            for player in sorted(game.players, key=lambda p: p.player_order)
        ]

    @staticmethod
    def _cricket_state_from_player(
        player: GamePlayer,
    ) -> Optional[CricketStateResponse]:
        if not player.cricket_state:
            return None
        return CricketStateResponse(
            marks=player.cricket_state.get("marks", {}),
            points=player.cricket_state.get("points", 0),
        )

    @staticmethod
    def _build_winner(game: Game) -> Optional[WinnerResponse]:
        if game.winner_player_id is None:
            return None
        winner = next(
            (p for p in game.players if p.id == game.winner_player_id),
            None,
        )
        if winner is None:
            return None
        return WinnerResponse(player_id=winner.id, name=winner.name)
