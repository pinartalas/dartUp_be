from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class GameConnectionManager:
    def __init__(self):
        self._connections: dict[int, dict[int, set[WebSocket]]] = {}

    async def connect(self, game_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        game_connections = self._connections.setdefault(game_id, {})
        game_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, game_id: int, user_id: int, websocket: WebSocket) -> bool:
        game_connections = self._connections.get(game_id)
        if game_connections is None:
            return True

        user_connections = game_connections.get(user_id)
        if user_connections is None:
            return True

        user_connections.discard(websocket)
        has_user_connections = bool(user_connections)
        if not has_user_connections:
            game_connections.pop(user_id, None)
        if not game_connections:
            self._connections.pop(game_id, None)
        return not has_user_connections

    async def send_to_socket(
        self,
        websocket: WebSocket,
        event_type: str,
        payload,
    ) -> None:
        await websocket.send_json(
            {
                "type": event_type,
                "payload": jsonable_encoder(payload),
            }
        )

    async def send_to_game(
        self,
        game_id: int,
        event_type: str,
        payload,
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        game_connections = self._connections.get(game_id, {})
        connections: list[tuple[int, WebSocket]] = []
        for user_id, sockets in game_connections.items():
            if exclude_user_id is not None and user_id == exclude_user_id:
                continue
            connections.extend((user_id, websocket) for websocket in sockets)

        for user_id, websocket in connections:
            try:
                await self.send_to_socket(websocket, event_type, payload)
            except RuntimeError:
                self.disconnect(game_id, user_id, websocket)


game_connection_manager = GameConnectionManager()
