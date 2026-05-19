import math
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import GameHistoryError
from app.models.game import Game, GamePlayer
from app.repositories.game_history_repository import GameHistoryRepository
from app.schemas.game import GameStatus
from app.schemas.game_history import (
    GameHistoryDateGroup,
    GameHistoryEntry,
    GameHistoryListResponse,
    GameHistoryQueryParams,
    GameHistoryStatistics,
    HistoryPeriod,
    PaginationMeta,
)


class GameHistoryService:
    def __init__(self, db: Session):
        self.repository = GameHistoryRepository(db)

    def get_user_game_history(
        self,
        owner_id: int,
        params: GameHistoryQueryParams,
    ) -> GameHistoryListResponse:
        if params.status is not None and params.status != GameStatus.FINISHED:
            return self._empty_response(params.page, params.limit)

        finished_from, finished_to = self._resolve_finished_range(params)
        game_type = params.game_type.value if params.game_type else None
        status = params.status.value if params.status else None

        total = self.repository.count_finished_games(
            owner_id,
            finished_from=finished_from,
            finished_to=finished_to,
            game_type=game_type,
            game_mode=params.game_mode,
            status=status,
        )

        offset = (params.page - 1) * params.limit
        games = self.repository.list_finished_games(
            owner_id,
            finished_from=finished_from,
            finished_to=finished_to,
            game_type=game_type,
            game_mode=params.game_mode,
            status=status,
            offset=offset,
            limit=params.limit,
        )

        return GameHistoryListResponse(
            data=self._group_by_date(games, owner_id),
            pagination=self._build_pagination(
                page=params.page,
                limit=params.limit,
                total=total,
            ),
        )

    @staticmethod
    def _resolve_finished_range(
        params: GameHistoryQueryParams,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        if params.period is None:
            return None, None

        now = datetime.utcnow()

        if params.period == HistoryPeriod.LAST_WEEK:
            return now - timedelta(days=7), now

        if params.period == HistoryPeriod.LAST_MONTH:
            return now - timedelta(days=30), now

        if params.period == HistoryPeriod.CUSTOM:
            assert params.start_date is not None and params.end_date is not None
            start = datetime.combine(params.start_date, time.min)
            end = datetime.combine(params.end_date, time.max)
            return start, end

        raise GameHistoryError("Invalid period value")

    def _group_by_date(
        self,
        games: list[Game],
        owner_id: int,
    ) -> list[GameHistoryDateGroup]:
        groups: list[GameHistoryDateGroup] = []
        current_date: Optional[date] = None
        current_games: list[GameHistoryEntry] = []

        for game in games:
            if game.finished_at is None:
                continue

            finished_date = game.finished_at.date()
            entry = self._build_entry(game, owner_id)

            if current_date != finished_date:
                if current_games:
                    groups.append(
                        GameHistoryDateGroup(date=current_date, games=current_games)
                    )
                current_date = finished_date
                current_games = [entry]
            else:
                current_games.append(entry)

        if current_date is not None and current_games:
            groups.append(GameHistoryDateGroup(date=current_date, games=current_games))

        return groups

    def _build_entry(self, game: Game, owner_id: int) -> GameHistoryEntry:
        owner_player = self._find_owner_player(game, owner_id)
        statistics = self._build_statistics(game, owner_player)
        result = self._resolve_result(owner_player)
        score = owner_player.total_points_scored if owner_player else 0

        duration_seconds = 0
        if game.finished_at and game.started_at:
            duration_seconds = max(
                0,
                int((game.finished_at - game.started_at).total_seconds()),
            )

        return GameHistoryEntry(
            game_id=game.game_uuid,
            game_type=game.game_type,
            game_mode=game.game_variant,
            status=game.status,
            started_at=game.started_at,
            finished_at=game.finished_at,
            duration_seconds=duration_seconds,
            result=result,
            score=score,
            statistics=statistics,
        )

    @staticmethod
    def _find_owner_player(game: Game, owner_id: int) -> Optional[GamePlayer]:
        linked = next((p for p in game.players if p.user_id == owner_id), None)
        if linked is not None:
            return linked
        if len(game.players) == 1:
            return game.players[0]
        return None

    @staticmethod
    def _resolve_result(owner_player: Optional[GamePlayer]) -> str:
        if owner_player is None:
            return "UNKNOWN"
        return "WIN" if owner_player.is_winner else "LOSS"

    @staticmethod
    def _build_statistics(
        game: Game,
        owner_player: Optional[GamePlayer],
    ) -> GameHistoryStatistics:
        if owner_player is None:
            return GameHistoryStatistics(
                total_turns=0,
                successful_turns=0,
                bust_count=0,
                total_darts_thrown=0,
                average_per_turn=None,
                highest_turn_score=0,
                accuracy=None,
            )

        player_turns = [t for t in game.turns if t.player_id == owner_player.id]
        bust_count = sum(1 for t in player_turns if t.is_bust)
        successful_turns = len(player_turns) - bust_count
        turn_scores = [t.turn_score for t in player_turns if not t.is_bust]
        highest = max(turn_scores, default=0)
        average = (
            round(sum(turn_scores) / len(turn_scores), 2) if turn_scores else None
        )
        accuracy = (
            round((successful_turns / len(player_turns)) * 100, 2)
            if player_turns
            else None
        )

        return GameHistoryStatistics(
            total_turns=len(player_turns),
            successful_turns=successful_turns,
            bust_count=bust_count,
            total_darts_thrown=owner_player.total_darts_thrown,
            average_per_turn=average,
            highest_turn_score=highest,
            accuracy=accuracy,
        )

    @staticmethod
    def _build_pagination(page: int, limit: int, total: int) -> PaginationMeta:
        total_pages = math.ceil(total / limit) if total > 0 else 0
        return PaginationMeta(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        )

    @staticmethod
    def _empty_response(page: int, limit: int) -> GameHistoryListResponse:
        return GameHistoryListResponse(
            data=[],
            pagination=PaginationMeta(
                page=page,
                limit=limit,
                total=0,
                total_pages=0,
            ),
        )
