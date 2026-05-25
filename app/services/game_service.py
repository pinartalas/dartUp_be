from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import GameServiceError
from app.models.game import DartThrow, Game, GamePlayer, Turn
from app.models.user import User
from app.schemas.game import (
    CreateGameRequest,
    DartThrowInput,
    SubmitTurnRequest,
    SubmitTurnResponse,
)
from app.services.dart_bot_service import DartBotService
from app.services.game_state_service import GameStateService
from app.services.scoring.base import PlayerScoringState
from app.services.scoring.factory import get_scoring_service


class GameService:
    def __init__(self, db: Session):
        self.db = db
        self.state_service = GameStateService()
        self.bot_service = DartBotService()

    def create_game(
        self,
        owner: User,
        request: CreateGameRequest,
        *,
        commit: bool = True,
    ) -> Game:
        scoring = get_scoring_service(request.game_type.value)
        settings = self._serialize_settings(request)

        game = Game(
            owner_id=owner.id,
            game_type=request.game_type.value,
            game_variant=request.game_variant,
            settings=settings,
            status="active",
            turn_sequence=0,
        )
        self.db.add(game)
        self.db.flush()

        players: list[GamePlayer] = []
        for index, player_input in enumerate(request.players):
            game_player = GamePlayer(
                game_id=game.id,
                user_id=player_input.user_id,
                name=player_input.name,
                player_order=index,
                is_bot=player_input.is_bot,
                bot_difficulty=(
                    player_input.bot_difficulty.value
                    if player_input.bot_difficulty
                    else None
                ),
            )
            self.db.add(game_player)
            self.db.flush()

            state = scoring.create_initial_player_state(
                player_id=game_player.id,
                name=game_player.name,
                player_order=game_player.player_order,
                game_variant=request.game_variant,
                settings=settings,
            )
            self._apply_state_to_player(game_player, state, request.game_type.value)
            players.append(game_player)

        starting_player = players[request.starting_player]
        game.current_player_id = starting_player.id

        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return self._load_game(game.id)

    def get_game(self, game_id: int, user_id: int) -> Game:
        game = self._load_game(game_id)
        self._assert_can_access_game(game, user_id)
        return game

    def submit_turn(
        self,
        game_id: int,
        user_id: int,
        request: SubmitTurnRequest,
    ) -> SubmitTurnResponse:
        game = self._load_game(game_id)
        self._assert_can_access_game(game, user_id)

        if game.status != "active":
            raise GameServiceError("Game is already finished", status_code=400)

        if game.current_player_id != request.player_id:
            raise GameServiceError("It is not this player's turn", status_code=400)

        active_player = self._get_player(game, request.player_id)
        if active_player.is_bot:
            raise GameServiceError(
                "Use bot-turn endpoint for bot players",
                status_code=400,
            )
        if self._is_online_game(game) and active_player.user_id != user_id:
            raise GameServiceError(
                "You can only submit turns for your online player",
                status_code=403,
            )

        return self._process_turn(game, active_player, request.throws)

    def submit_bot_turn(self, game_id: int, user_id: int) -> SubmitTurnResponse:
        game = self._load_game(game_id)
        self._assert_can_access_game(game, user_id)

        if game.status != "active":
            raise GameServiceError("Game is already finished", status_code=400)

        if game.current_player_id is None:
            raise GameServiceError("No active player", status_code=400)

        bot_player = self._get_player(game, game.current_player_id)
        if not bot_player.is_bot:
            raise GameServiceError("Current player is not a bot", status_code=400)

        throws = self.bot_service.generate_turn(game, bot_player)
        return self._process_turn(game, bot_player, throws)

    def _process_turn(
        self,
        game: Game,
        active_player: GamePlayer,
        throws: list[DartThrowInput],
    ) -> SubmitTurnResponse:
        scoring = get_scoring_service(game.game_type)

        player_states = [self._to_scoring_state(p) for p in game.players]
        active_state = next(
            s for s in player_states if s.player_id == active_player.id
        )

        result = scoring.process_turn(
            active_player=active_state,
            all_players=player_states,
            throws=throws,
            settings=game.settings or {},
            game_variant=game.game_variant,
        )

        game.turn_sequence += 1
        turn = Turn(
            game_id=game.id,
            player_id=active_player.id,
            turn_number=game.turn_sequence,
            turn_score=result.turn_score,
            score_before=result.score_before,
            score_after=result.score_after,
            points_scored=result.points_scored,
            is_bust=result.is_bust,
        )
        self.db.add(turn)
        self.db.flush()

        computed_throws = scoring.normalize_throws(throws)
        for dart in computed_throws:
            self.db.add(
                DartThrow(
                    turn_id=turn.id,
                    throw_order=dart.throw_order,
                    segment=dart.segment,
                    multiplier=dart.multiplier,
                    score=dart.score,
                )
            )

        for updated in result.updated_players:
            player = self._get_player(game, updated.player_id)
            self._apply_state_to_player(player, updated, game.game_type)

        active_db_player = self._get_player(game, active_player.id)
        active_db_player.total_darts_thrown += 3
        if game.game_type == "x01" and not result.is_bust:
            active_db_player.total_points_scored += result.turn_score
        elif game.game_type == "cricket":
            active_db_player.total_points_scored = active_db_player.cricket_state.get(
                "points", 0
            )

        next_player_id: Optional[int] = None

        if result.is_finished and result.winner_player_id:
            self._finish_game(game, result.winner_player_id)
        else:
            next_player = self._next_player(game, active_player)
            game.current_player_id = next_player.id
            next_player_id = next_player.id

        self.db.commit()

        game = self._load_game(game.id)
        turn = (
            self.db.query(Turn)
            .options(joinedload(Turn.throws))
            .filter(Turn.id == turn.id)
            .one()
        )

        return SubmitTurnResponse(
            game=self.state_service.build_game_state(game),
            turn_result=self.state_service.build_turn_result(turn),
            next_player_id=next_player_id,
            is_finished=game.status == "finished",
            winner=self.state_service._build_winner(game),
        )

    def _finish_game(self, game: Game, winner_player_id: int) -> None:
        game.status = "finished"
        game.finished_at = datetime.utcnow()
        game.winner_player_id = winner_player_id
        game.current_player_id = None
        for player in game.players:
            player.is_winner = player.id == winner_player_id

    @staticmethod
    def _next_player(game: Game, current: GamePlayer) -> GamePlayer:
        ordered = sorted(game.players, key=lambda p: p.player_order)
        index = next(i for i, p in enumerate(ordered) if p.id == current.id)
        return ordered[(index + 1) % len(ordered)]

    def _load_game(self, game_id: int) -> Game:
        game = (
            self.db.query(Game)
            .options(
                joinedload(Game.players),
                joinedload(Game.turns).joinedload(Turn.throws),
            )
            .filter(Game.id == game_id)
            .first()
        )
        if game is None:
            raise GameServiceError("Game not found", status_code=404)
        return game

    @staticmethod
    def _assert_can_access_game(game: Game, user_id: int) -> None:
        if game.owner_id == user_id:
            return
        if any(player.user_id == user_id for player in game.players):
            return
        raise GameServiceError("Not allowed to access this game", status_code=403)

    @staticmethod
    def _is_online_game(game: Game) -> bool:
        online_settings = (game.settings or {}).get("online")
        return bool(online_settings and online_settings.get("room_id"))

    @staticmethod
    def _get_player(game: Game, player_id: int) -> GamePlayer:
        player = next((p for p in game.players if p.id == player_id), None)
        if player is None:
            raise GameServiceError("Player not found in this game", status_code=400)
        return player

    @staticmethod
    def _serialize_settings(request: CreateGameRequest) -> dict[str, Any]:
        if request.settings is None:
            return {}
        data = request.settings.model_dump(exclude_none=True)
        if request.settings.x01:
            data["x01"] = request.settings.x01.model_dump()
        return data

    @staticmethod
    def _to_scoring_state(player: GamePlayer) -> PlayerScoringState:
        cricket_marks = {}
        cricket_points = 0
        if player.cricket_state:
            cricket_marks = dict(player.cricket_state.get("marks", {}))
            cricket_points = player.cricket_state.get("points", 0)

        return PlayerScoringState(
            player_id=player.id,
            name=player.name,
            player_order=player.player_order,
            current_score=player.current_score,
            cricket_marks=cricket_marks,
            cricket_points=cricket_points,
        )

    @staticmethod
    def _apply_state_to_player(
        player: GamePlayer,
        state: PlayerScoringState,
        game_type: str,
    ) -> None:
        if game_type == "x01":
            player.current_score = state.current_score
        elif game_type == "cricket":
            player.cricket_state = {
                "marks": state.cricket_marks,
                "points": state.cricket_points,
            }
            player.current_score = None
