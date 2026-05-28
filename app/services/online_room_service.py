import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import OnlineRoomError
from app.models.game import Game, Turn
from app.models.online_room import OnlineRoom
from app.models.user import User
from app.schemas.game import CreateGameRequest, PlayerCreateInput
from app.schemas.online_room import (
    CreateOnlineRoomRequest,
    JoinOnlineRoomRequest,
    OnlineRoomListResponse,
    OnlineRoomResponse,
    OnlineRoomStatus,
)
from app.services.game_service import GameService
from app.services.game_state_service import GameStateService


ROOM_CODE_LENGTH = 6
ROOM_CODE_CHARS = string.ascii_uppercase + string.digits
ONLINE = "online"
LEFT = "left"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OnlineRoomService:
    def __init__(self, db: Session):
        self.db = db
        self.game_state_service = GameStateService()

    def create_room(
        self,
        host: User,
        request: CreateOnlineRoomRequest,
    ) -> OnlineRoomResponse:
        self.cancel_waiting_rooms_for_user(host.id)

        room = OnlineRoom(
            room_code=self._generate_room_code(),
            host_user_id=host.id,
            host_player_name=self._resolve_player_name(host, request.player_name),
            game_type=request.game_type.value,
            game_variant=request.game_variant,
            settings=self._serialize_settings(request.settings),
            status=OnlineRoomStatus.WAITING.value,
            host_presence_state=ONLINE,
            host_last_seen_at=_utcnow(),
        )
        self.db.add(room)
        self.db.commit()

        return self._build_response(self._load_room(room.id), host.id)

    def list_waiting_rooms(
        self,
        current_user_id: int,
        *,
        include_own: bool = True,
        limit: int = 50,
    ) -> OnlineRoomListResponse:
        query = (
            self.db.query(OnlineRoom)
            .filter(OnlineRoom.status == OnlineRoomStatus.WAITING.value)
            .order_by(OnlineRoom.created_at.desc())
            .limit(limit)
        )
        if not include_own:
            query = query.filter(OnlineRoom.host_user_id != current_user_id)

        return OnlineRoomListResponse(
            rooms=[
                self._build_response(room, current_user_id)
                for room in query.all()
            ]
        )

    def get_room(self, room_code: str, current_user_id: int) -> OnlineRoomResponse:
        room = self._load_room_by_code(room_code)
        return self._build_response(room, current_user_id)

    def join_room(
        self,
        room_code: str,
        guest: User,
        request: JoinOnlineRoomRequest,
    ) -> OnlineRoomResponse:
        room = self._load_room_by_code(room_code, for_update=True)

        if room.status == OnlineRoomStatus.ACTIVE.value and room.guest_user_id == guest.id:
            return self._build_response(room, guest.id)

        if room.status != OnlineRoomStatus.WAITING.value:
            raise OnlineRoomError("Room is not available", status_code=409)

        if room.host_user_id == guest.id:
            raise OnlineRoomError("You cannot join your own room", status_code=400)

        game = GameService(self.db).create_game(
            room.host,
            CreateGameRequest(
                game_type=room.game_type,
                game_variant=room.game_variant,
                players=[
                    PlayerCreateInput(
                        name=room.host_player_name,
                        user_id=room.host_user_id,
                    ),
                    PlayerCreateInput(
                        name=self._resolve_player_name(guest, request.player_name),
                        user_id=guest.id,
                    ),
                ],
                starting_player=0,
                settings=self._settings_request_value(room.settings),
            ),
            commit=False,
        )
        game.settings = {
            **(game.settings or {}),
            "online": {
                "room_id": room.id,
                "room_uuid": room.room_uuid,
                "room_code": room.room_code,
            },
        }

        room.guest_user_id = guest.id
        room.guest_player_name = self._resolve_player_name(guest, request.player_name)
        room.game_id = game.id
        room.status = OnlineRoomStatus.ACTIVE.value
        self.db.commit()

        return self._build_response(self._load_room(room.id), guest.id)

    def cancel_room(self, room_code: str, host_id: int) -> OnlineRoomResponse:
        room = self._load_room_by_code(room_code, for_update=True)
        if room.host_user_id != host_id:
            raise OnlineRoomError("Only the host can cancel this room", status_code=403)
        if room.status != OnlineRoomStatus.WAITING.value:
            raise OnlineRoomError("Only waiting rooms can be cancelled", status_code=400)

        now = _utcnow()
        room.status = OnlineRoomStatus.CANCELLED.value
        room.host_presence_state = LEFT
        room.host_left_at = now
        room.host_leave_reason = "user_quit"
        self.db.commit()
        return self._build_response(self._load_room(room.id), host_id)

    def heartbeat_waiting_room(
        self,
        room_code: str,
        host_id: int,
    ) -> OnlineRoomResponse:
        room = self._load_room_by_code(room_code, for_update=True)
        if room.host_user_id != host_id:
            raise OnlineRoomError("Only the host can heartbeat this room", status_code=403)
        if room.status != OnlineRoomStatus.WAITING.value:
            raise OnlineRoomError("Only waiting rooms can receive heartbeat", status_code=400)

        room.host_presence_state = ONLINE
        room.host_last_seen_at = _utcnow()
        room.host_disconnected_at = None
        room.host_left_at = None
        room.host_leave_reason = None
        self.db.commit()
        return self._build_response(self._load_room(room.id), host_id)

    def leave_waiting_room(
        self,
        room_code: str,
        host_id: int,
        reason: str,
    ) -> OnlineRoomResponse:
        room = self._load_room_by_code(room_code, for_update=True)
        if room.host_user_id != host_id:
            raise OnlineRoomError("Only the host can leave this room", status_code=403)
        if room.status != OnlineRoomStatus.WAITING.value:
            raise OnlineRoomError("Only waiting rooms can be left", status_code=400)

        self._cancel_waiting_room_for_host(room, reason)
        self.db.commit()
        return self._build_response(self._load_room(room.id), host_id)

    def cancel_stale_waiting_rooms(self, timeout_seconds: int) -> int:
        cutoff = _utcnow() - timedelta(seconds=timeout_seconds)
        rooms = (
            self.db.query(OnlineRoom)
            .filter(OnlineRoom.status == OnlineRoomStatus.WAITING.value)
            .all()
        )

        cancelled_count = 0
        for room in rooms:
            last_seen_at = room.host_last_seen_at or room.created_at
            if last_seen_at is None or last_seen_at > cutoff:
                continue
            self._cancel_waiting_room_for_host(room, "timeout")
            room.host_disconnected_at = last_seen_at
            cancelled_count += 1

        if cancelled_count:
            self.db.commit()
        return cancelled_count

    def cancel_waiting_rooms_for_user(self, user_id: int) -> int:
        rooms = (
            self.db.query(OnlineRoom)
            .filter(
                OnlineRoom.host_user_id == user_id,
                OnlineRoom.status == OnlineRoomStatus.WAITING.value,
            )
            .all()
        )
        if not rooms:
            return 0

        for room in rooms:
            self._cancel_waiting_room_for_host(room, "user_quit")

        self.db.commit()
        return len(rooms)

    def mark_finished_if_game_finished(self, game_id: int, is_finished: bool) -> None:
        if not is_finished:
            return

        room = (
            self.db.query(OnlineRoom)
            .filter(
                OnlineRoom.game_id == game_id,
                OnlineRoom.status == OnlineRoomStatus.ACTIVE.value,
            )
            .first()
        )
        if room is None:
            return

        room.status = OnlineRoomStatus.FINISHED.value
        self.db.commit()

    def _generate_room_code(self) -> str:
        for _ in range(20):
            code = "".join(
                secrets.choice(ROOM_CODE_CHARS)
                for _ in range(ROOM_CODE_LENGTH)
            )
            exists = (
                self.db.query(OnlineRoom.id)
                .filter(OnlineRoom.room_code == code)
                .first()
            )
            if exists is None:
                return code

        raise OnlineRoomError("Could not generate a unique room code", status_code=500)

    def _load_room(self, room_id: int) -> OnlineRoom:
        room = (
            self.db.query(OnlineRoom)
            .options(
                joinedload(OnlineRoom.host),
                joinedload(OnlineRoom.guest),
                joinedload(OnlineRoom.game).joinedload(Game.players),
                joinedload(OnlineRoom.game).joinedload(Game.turns).joinedload(Turn.throws),
            )
            .filter(OnlineRoom.id == room_id)
            .first()
        )
        if room is None:
            raise OnlineRoomError("Room not found", status_code=404)
        return room

    def _load_room_by_code(
        self,
        room_code: str,
        *,
        for_update: bool = False,
    ) -> OnlineRoom:
        if for_update:
            room = (
                self.db.query(OnlineRoom)
                .filter(OnlineRoom.room_code == room_code.upper())
                .with_for_update()
                .first()
            )
            if room is None:
                raise OnlineRoomError("Room not found", status_code=404)
            return self._load_room(room.id)

        query = (
            self.db.query(OnlineRoom)
            .options(
                joinedload(OnlineRoom.host),
                joinedload(OnlineRoom.guest),
                joinedload(OnlineRoom.game).joinedload(Game.players),
                joinedload(OnlineRoom.game).joinedload(Game.turns).joinedload(Turn.throws),
            )
            .filter(OnlineRoom.room_code == room_code.upper())
        )

        room = query.first()
        if room is None:
            raise OnlineRoomError("Room not found", status_code=404)
        return room

    def _build_response(
        self,
        room: OnlineRoom,
        current_user_id: int,
    ) -> OnlineRoomResponse:
        is_host = room.host_user_id == current_user_id
        is_guest = room.guest_user_id == current_user_id
        return OnlineRoomResponse(
            id=room.id,
            room_uuid=room.room_uuid,
            room_code=room.room_code,
            status=OnlineRoomStatus(room.status),
            host_user_id=room.host_user_id,
            guest_user_id=room.guest_user_id,
            game_id=room.game_id,
            game_type=room.game_type,
            game_variant=room.game_variant,
            settings=room.settings or {},
            host_player_name=room.host_player_name,
            guest_player_name=room.guest_player_name,
            host_presence_state=room.host_presence_state,
            host_last_seen_at=room.host_last_seen_at,
            host_disconnected_at=room.host_disconnected_at,
            host_left_at=room.host_left_at,
            host_leave_reason=room.host_leave_reason,
            created_at=room.created_at,
            updated_at=room.updated_at,
            is_host=is_host,
            is_guest=is_guest,
            can_join=(
                room.status == OnlineRoomStatus.WAITING.value
                and room.host_user_id != current_user_id
            ),
            game=(
                self.game_state_service.build_game_state(room.game)
                if room.game is not None
                else None
            ),
        )

    @staticmethod
    def _resolve_player_name(user: User, provided_name: Optional[str]) -> str:
        if user.username and user.username.strip():
            return user.username.strip()
        if provided_name and provided_name.strip():
            return provided_name.strip()
        if user.full_name:
            return user.full_name
        if user.email:
            return user.email
        return f"Player {user.id}"

    @staticmethod
    def _serialize_settings(settings) -> dict:
        if settings is None:
            return {}

        data = settings.model_dump(exclude_none=True)

        if settings.x01:
            data["x01"] = settings.x01.model_dump()
        
        if settings.match:
            data["match"] = settings.match.model_dump()
            
        return data

    @staticmethod
    def _cancel_waiting_room_for_host(room: OnlineRoom, reason: str) -> None:
        now = _utcnow()
        room.status = OnlineRoomStatus.CANCELLED.value
        room.host_presence_state = LEFT
        room.host_left_at = now
        room.host_leave_reason = reason

    @staticmethod
    def _settings_request_value(settings: dict):
        if not settings:
            return None
        return settings
