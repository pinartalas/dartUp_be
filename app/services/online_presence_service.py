from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import OnlineRoomError
from app.models.game import Game, GamePlayer
from app.models.online_room import OnlineRoom
from app.schemas.online_room import OnlineGameLeaveResponse, OnlineRoomStatus
from app.services.game_state_service import GameStateService


ONLINE = "online"
DISCONNECTED = "disconnected"
LEFT = "left"
TERMINAL_GAME_STATUSES = {"finished", "forfeited", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class PresenceEvent:
    game_id: int
    event_type: str
    payload: Any
    exclude_user_id: Optional[int] = None


@dataclass
class PresenceActionResult:
    response: OnlineGameLeaveResponse
    events: list[PresenceEvent]


class OnlinePresenceService:
    def __init__(self, db: Session):
        self.db = db
        self.state_service = GameStateService()

    def mark_connected(
        self,
        game_id: int,
        user_id: int,
    ) -> Optional[PresenceEvent]:
        game = self._load_online_game(game_id)
        player = self._player_for_user(game, user_id)

        if self._is_terminal(game):
            return None

        previous_state = player.presence_state or ONLINE
        if previous_state == LEFT:
            return None

        now = _utcnow()
        player.presence_state = ONLINE
        player.last_seen_at = now
        player.disconnected_at = None
        player.leave_reason = None
        self.db.commit()

        if previous_state != DISCONNECTED:
            return None

        return PresenceEvent(
            game_id=game.id,
            event_type="player_reconnected",
            payload=self._player_event_payload(game.id, player),
            exclude_user_id=user_id,
        )

    def heartbeat(self, game_id: int, user_id: int) -> None:
        game = self._load_online_game(game_id)
        player = self._player_for_user(game, user_id)

        if self._is_terminal(game) or player.presence_state == LEFT:
            return

        player.presence_state = ONLINE
        player.last_seen_at = _utcnow()
        player.disconnected_at = None
        player.leave_reason = None
        self.db.commit()

    def mark_disconnected(
        self,
        game_id: int,
        user_id: int,
    ) -> Optional[PresenceEvent]:
        game = self._load_online_game(game_id)
        player = self._player_for_user(game, user_id)

        if self._is_terminal(game) or player.presence_state == LEFT:
            return None
        if player.presence_state == DISCONNECTED:
            return None

        now = _utcnow()
        player.presence_state = DISCONNECTED
        player.last_seen_at = now
        player.disconnected_at = now
        player.leave_reason = None
        self.db.commit()

        return PresenceEvent(
            game_id=game.id,
            event_type="player_disconnected",
            payload=self._player_event_payload(game.id, player),
            exclude_user_id=user_id,
        )

    def leave_game(
        self,
        game_id: int,
        user_id: int,
        reason: str,
    ) -> PresenceActionResult:
        game = self._load_online_game(game_id)
        player = self._player_for_user(game, user_id)

        if self._is_terminal(game):
            state = self.state_service.build_game_state(game)
            return PresenceActionResult(
                response=OnlineGameLeaveResponse(
                    game=state,
                    is_finished=state.is_finished,
                    winner=state.winner,
                    forfeit=state.forfeit,
                ),
                events=[],
            )

        now = _utcnow()
        player.presence_state = LEFT
        player.left_at = now
        player.leave_reason = reason
        player.disconnected_at = None
        player.last_seen_at = now

        opponent = self._opponent_for(game, player)
        room = self._room_for_game(game.id)

        if opponent is None:
            self._cancel_game(game, now)
            if room is not None:
                room.status = OnlineRoomStatus.CANCELLED.value
        else:
            self._forfeit_game(
                game=game,
                forfeiting_player=player,
                winner=opponent,
                reason=reason,
                finished_at=now,
            )
            if room is not None:
                room.status = OnlineRoomStatus.FINISHED.value

        self.db.commit()

        game = self._load_online_game(game.id)
        state = self.state_service.build_game_state(game)
        player = self._player_for_user(game, user_id)

        events = [
            PresenceEvent(
                game_id=game.id,
                event_type="player_left",
                payload=self._player_event_payload(game.id, player),
                exclude_user_id=user_id,
            )
        ]
        if state.forfeit is not None:
            events.append(
                PresenceEvent(
                    game_id=game.id,
                    event_type="game_forfeited",
                    payload=self._game_forfeited_payload(state),
                )
            )

        return PresenceActionResult(
            response=OnlineGameLeaveResponse(
                game=state,
                is_finished=state.is_finished,
                winner=state.winner,
                forfeit=state.forfeit,
            ),
            events=events,
        )

    def process_timeouts(self, timeout_seconds: int) -> list[PresenceEvent]:
        now = _utcnow()
        cutoff = now - timedelta(seconds=timeout_seconds)
        events: list[PresenceEvent] = []

        for game in self._active_online_games():
            if self._is_terminal(game):
                continue
            for player in game.players:
                if (
                    player.presence_state == ONLINE
                    and player.last_seen_at is not None
                    and player.last_seen_at <= cutoff
                ):
                    player.presence_state = DISCONNECTED
                    player.disconnected_at = now
                    player.leave_reason = None
                    self.db.commit()
                    events.append(
                        PresenceEvent(
                            game_id=game.id,
                            event_type="player_disconnected",
                            payload=self._player_event_payload(game.id, player),
                            exclude_user_id=player.user_id,
                        )
                    )

        for game in self._active_online_games():
            if self._is_terminal(game):
                continue
            expired_players = [
                player
                for player in game.players
                if (
                    player.presence_state == DISCONNECTED
                    and player.disconnected_at is not None
                    and player.disconnected_at <= cutoff
                )
            ]
            if not expired_players:
                continue

            player = min(expired_players, key=lambda p: p.disconnected_at or now)
            self._timeout_forfeit(game, player, now)
            self.db.commit()

            game = self._load_online_game(game.id)
            player = self._player_by_id(game, player.id)
            state = self.state_service.build_game_state(game)
            events.append(
                PresenceEvent(
                    game_id=game.id,
                    event_type="player_left",
                    payload=self._player_event_payload(game.id, player),
                    exclude_user_id=player.user_id,
                )
            )
            events.append(
                PresenceEvent(
                    game_id=game.id,
                    event_type="game_forfeited",
                    payload=self._game_forfeited_payload(state),
                )
            )

        return events

    def _timeout_forfeit(
        self,
        game: Game,
        player: GamePlayer,
        finished_at: datetime,
    ) -> None:
        player.presence_state = LEFT
        player.left_at = finished_at
        player.leave_reason = "timeout"

        opponent = self._opponent_for(game, player)
        room = self._room_for_game(game.id)
        if opponent is None:
            self._cancel_game(game, finished_at)
            if room is not None:
                room.status = OnlineRoomStatus.CANCELLED.value
            return

        self._forfeit_game(
            game=game,
            forfeiting_player=player,
            winner=opponent,
            reason="timeout",
            finished_at=finished_at,
        )
        if room is not None:
            room.status = OnlineRoomStatus.FINISHED.value

    def _forfeit_game(
        self,
        *,
        game: Game,
        forfeiting_player: GamePlayer,
        winner: GamePlayer,
        reason: str,
        finished_at: datetime,
    ) -> None:
        game.status = "forfeited"
        game.finished_at = finished_at
        game.winner_player_id = winner.id
        game.current_player_id = None

        for player in game.players:
            player.is_winner = player.id == winner.id

        settings = dict(game.settings or {})
        settings["forfeit"] = {
            "player_id": forfeiting_player.id,
            "reason": reason,
        }
        game.settings = settings

    @staticmethod
    def _cancel_game(game: Game, finished_at: datetime) -> None:
        game.status = "cancelled"
        game.finished_at = finished_at
        game.winner_player_id = None
        game.current_player_id = None
        for player in game.players:
            player.is_winner = False

    def _load_online_game(self, game_id: int) -> Game:
        game = (
            self.db.query(Game)
            .options(joinedload(Game.players))
            .filter(Game.id == game_id)
            .first()
        )
        if game is None:
            raise OnlineRoomError("Game not found", status_code=404)
        if not self._is_online_game(game):
            raise OnlineRoomError("Game is not an online room game", status_code=400)
        return game

    def _active_online_games(self) -> list[Game]:
        games = (
            self.db.query(Game)
            .options(joinedload(Game.players))
            .filter(Game.status == "active")
            .all()
        )
        return [game for game in games if self._is_online_game(game)]

    def _room_for_game(self, game_id: int) -> Optional[OnlineRoom]:
        return (
            self.db.query(OnlineRoom)
            .filter(OnlineRoom.game_id == game_id)
            .first()
        )

    @staticmethod
    def _is_online_game(game: Game) -> bool:
        online_settings = (game.settings or {}).get("online")
        return bool(online_settings and online_settings.get("room_id"))

    @staticmethod
    def _is_terminal(game: Game) -> bool:
        return game.status in TERMINAL_GAME_STATUSES

    @staticmethod
    def _player_for_user(game: Game, user_id: int) -> GamePlayer:
        player = next((p for p in game.players if p.user_id == user_id), None)
        if player is None:
            raise OnlineRoomError("Not allowed to access this game", status_code=403)
        return player

    @staticmethod
    def _player_by_id(game: Game, player_id: int) -> GamePlayer:
        player = next((p for p in game.players if p.id == player_id), None)
        if player is None:
            raise OnlineRoomError("Player not found in this game", status_code=400)
        return player

    @staticmethod
    def _opponent_for(game: Game, player: GamePlayer) -> Optional[GamePlayer]:
        return next(
            (
                opponent
                for opponent in game.players
                if opponent.id != player.id and not opponent.is_bot
            ),
            None,
        )

    @staticmethod
    def _player_event_payload(game_id: int, player: GamePlayer) -> dict[str, Any]:
        return {
            "game_id": game_id,
            "player": {
                "player_id": player.id,
                "user_id": player.user_id,
                "name": player.name,
                "presence_state": player.presence_state,
                "last_seen_at": player.last_seen_at,
                "disconnected_at": player.disconnected_at,
                "left_at": player.left_at,
                "reason": player.leave_reason,
            },
        }

    @staticmethod
    def _game_forfeited_payload(state) -> dict[str, Any]:
        return {
            "game": state,
            "is_finished": True,
            "winner": state.winner,
            "forfeit": state.forfeit,
        }
