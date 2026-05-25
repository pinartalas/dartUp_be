from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.game import GameSettings, GameStateResponse, GameType


class OnlineRoomStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class CreateOnlineRoomRequest(BaseModel):
    game_type: GameType
    game_variant: Optional[int] = Field(
        None,
        description="301, 501 for x01; null for cricket",
    )
    settings: Optional[GameSettings] = None
    player_name: Optional[str] = Field(None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_game_config(self) -> "CreateOnlineRoomRequest":
        if self.game_type == GameType.X01:
            if self.game_variant not in (301, 501, 701, 1001):
                raise ValueError("x01 rooms require game_variant 301, 501, 701, or 1001")
        elif self.game_type == GameType.CRICKET and self.game_variant is not None:
            raise ValueError("cricket rooms must not set game_variant")
        return self


class JoinOnlineRoomRequest(BaseModel):
    player_name: Optional[str] = Field(None, min_length=1, max_length=100)


class OnlineRoomCleanupResponse(BaseModel):
    cancelled_count: int


class OnlineRoomResponse(BaseModel):
    id: int
    room_uuid: str
    room_code: str
    status: OnlineRoomStatus
    host_user_id: int
    guest_user_id: Optional[int] = None
    game_id: Optional[int] = None
    game_type: str
    game_variant: Optional[int] = None
    settings: dict[str, Any]
    host_player_name: str
    guest_player_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_host: bool = False
    is_guest: bool = False
    can_join: bool = False
    game: Optional[GameStateResponse] = None


class OnlineRoomListResponse(BaseModel):
    rooms: list[OnlineRoomResponse]
