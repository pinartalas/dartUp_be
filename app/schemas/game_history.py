from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.game import GameStatus, GameType

DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100


class HistoryPeriod(str, Enum):
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class GameHistoryQueryParams(BaseModel):
    period: Optional[HistoryPeriod] = None
    start_date: Optional[date] = Field(None, alias="startDate")
    end_date: Optional[date] = Field(None, alias="endDate")
    game_type: Optional[GameType] = Field(None, alias="gameType")
    game_mode: Optional[int] = Field(
        None,
        alias="gameMode",
        description="Game variant, e.g. 301 or 501 for x01",
    )
    status: Optional[GameStatus] = Field(
        None,
        description="Only finished games are returned; other values yield empty results",
    )
    page: int = Field(1, ge=1)
    limit: int = Field(DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_period_and_dates(self) -> "GameHistoryQueryParams":
        if self.period == HistoryPeriod.CUSTOM:
            if self.start_date is None or self.end_date is None:
                raise ValueError(
                    "startDate and endDate are required when period is custom"
                )
            if self.start_date > self.end_date:
                raise ValueError("startDate must be on or before endDate")
        elif self.period is not None and (
            self.start_date is not None or self.end_date is not None
        ):
            raise ValueError(
                "startDate and endDate are only allowed when period is custom"
            )
        return self


class GameHistoryStatistics(BaseModel):
    total_turns: int
    successful_turns: int
    bust_count: int
    total_darts_thrown: int
    average_per_turn: Optional[float] = None
    highest_turn_score: int
    accuracy: Optional[float] = Field(
        None,
        description="Percentage of non-bust turns",
    )


class GameHistoryEntry(BaseModel):
    game_id: str
    game_type: str
    game_mode: Optional[int] = None
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: int
    result: str
    score: int
    statistics: GameHistoryStatistics


class GameHistoryDateGroup(BaseModel):
    date: date
    games: list[GameHistoryEntry]


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class GameHistoryListResponse(BaseModel):
    data: list[GameHistoryDateGroup]
    pagination: PaginationMeta
