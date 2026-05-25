from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class GameConnectionManager:
    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, game_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(game_id, set()).add(websocket)

    def disconnect(self, game_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(game_id)
        if connections is None:
            return

        connections.discard(websocket)
        if not connections:
            self._connections.pop(game_id, None)

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

    async def send_to_game(self, game_id: int, event_type: str, payload) -> None:
        connections = list(self._connections.get(game_id, set()))
        for websocket in connections:
            try:
                await self.send_to_socket(websocket, event_type, payload)
            except RuntimeError:
                self.disconnect(game_id, websocket)


game_connection_manager = GameConnectionManager()
