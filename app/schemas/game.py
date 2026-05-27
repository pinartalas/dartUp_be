from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class GameType(str, Enum):
    X01 = "x01"
    CRICKET = "cricket"


class GameStatus(str, Enum):
    ACTIVE = "active"
    FINISHED = "finished"
    FORFEITED = "forfeited"
    CANCELLED = "cancelled"


class PlayerPresenceState(str, Enum):
    ONLINE = "online"
    DISCONNECTED = "disconnected"
    LEFT = "left"


class X01Settings(BaseModel):
    double_out: bool = False
    double_in: bool = False

class MatchMode(str, Enum):
    OFF = "off"
    LEGS = "legs"

class MatchSettings(BaseModel):
    mode: MatchMode = MatchMode.OFF
    target_wins: Optional[int] = Field(None, ge=2)

    @model_validator(mode="after")
    def validate_match_settings(self) -> "MatchSettings":
        if self.mode == MatchMode.LEGS and self.target_wins is None:
            raise ValueError("legs match mode requires target_wins")
        if self.mode == MatchMode.OFF and self.target_wins is not None:
            raise ValueError("off match mode must not set target_wins")
        return self

class GameSettings(BaseModel):
    x01: Optional[X01Settings] = None
    match: Optional[MatchSettings] = None

class BotDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PlayerCreateInput(BaseModel):
    name: str
    user_id: Optional[int] = None
    is_bot: bool = False
    bot_difficulty: Optional[BotDifficulty] = None

    @model_validator(mode="after")
    def validate_bot_config(self) -> "PlayerCreateInput":
        if self.is_bot:
            if self.user_id is not None:
                raise ValueError("bot players must not have user_id")
            if self.bot_difficulty is None:
                self.bot_difficulty = BotDifficulty.MEDIUM
        elif self.bot_difficulty is not None:
            raise ValueError("non-bot players must not set bot_difficulty")

        return self


class CreateGameRequest(BaseModel):
    game_type: GameType
    game_variant: Optional[int] = Field(
        None,
        description="301, 501 for x01; null for cricket",
    )
    players: list[PlayerCreateInput] = Field(..., min_length=1, max_length=8)
    starting_player: int = Field(
        0,
        ge=0,
        description="Index in players list for the first thrower",
    )
    settings: Optional[GameSettings] = None

    @model_validator(mode="after")
    def validate_game_config(self) -> "CreateGameRequest":
        if self.game_type == GameType.X01:
            if self.game_variant not in (301, 501, 701, 1001):
                raise ValueError("x01 games require game_variant 301, 501, 701, or 1001")
        elif self.game_type == GameType.CRICKET and self.game_variant is not None:
            raise ValueError("cricket games must not set game_variant")
        if self.starting_player >= len(self.players):
            raise ValueError("starting_player index is out of range")
        return self


class DartThrowInput(BaseModel):
    segment: str = Field(..., description="1-20, bull, or miss")
    multiplier: int = Field(..., ge=1, le=3)
    score: Optional[int] = Field(None, ge=0, description="Ignored; computed server-side")


class SubmitTurnRequest(BaseModel):
    player_id: int
    throws: list[DartThrowInput] = Field(..., min_length=3, max_length=3)


class ThrowResponse(BaseModel):
    id: int
    throw_order: int
    segment: str
    multiplier: int
    score: int

    model_config = {"from_attributes": True}


class TurnResultResponse(BaseModel):
    turn_id: int
    turn_number: int
    turn_score: int
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    points_scored: Optional[int] = None
    is_bust: bool
    throws: list[ThrowResponse]


class CricketStateResponse(BaseModel):
    marks: dict[str, int]
    points: int


class PlayerStateResponse(BaseModel):
    id: int
    name: str
    user_id: Optional[int] = None
    player_order: int
    is_bot: bool
    bot_difficulty: Optional[BotDifficulty] = None
    current_score: Optional[int] = None
    cricket_state: Optional[CricketStateResponse] = None
    total_darts_thrown: int
    total_points_scored: int
    is_winner: bool
    is_active: bool = False
    presence_state: PlayerPresenceState = PlayerPresenceState.ONLINE
    last_seen_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    left_at: Optional[datetime] = None
    leave_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class WinnerResponse(BaseModel):
    player_id: int
    name: str


class ForfeitResponse(BaseModel):
    player_id: int
    reason: str


class GameStateResponse(BaseModel):
    id: int
    game_uuid: str
    game_type: str
    game_variant: Optional[int] = None
    status: str
    settings: dict[str, Any]
    players: list[PlayerStateResponse]
    current_player_id: Optional[int] = None
    turn_sequence: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    is_finished: bool
    winner: Optional[WinnerResponse] = None
    forfeit: Optional[ForfeitResponse] = None


class SubmitTurnResponse(BaseModel):
    game: GameStateResponse
    turn_result: TurnResultResponse
    next_player_id: Optional[int] = None
    is_finished: bool
    winner: Optional[WinnerResponse] = None


class PlayerStatsResponse(BaseModel):
    player_id: int
    name: str
    total_darts_thrown: int
    total_points_scored: int
    turn_count: int
    average_per_turn: Optional[float] = None
    highest_turn_score: int
    bust_count: int
    current_score: Optional[int] = None
    cricket_state: Optional[CricketStateResponse] = None


class GameStatsResponse(BaseModel):
    game_id: int
    game_uuid: str
    game_type: str
    game_variant: Optional[int] = None
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    winner: Optional[WinnerResponse] = None
    total_turns: int
    players: list[PlayerStatsResponse]
