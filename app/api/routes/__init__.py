from app.api.routes.auth import router as auth_router
from app.api.routes.games import router as games_router
from app.api.routes.online_rooms import router as online_rooms_router
from app.api.routes.request_logs import router as request_logs_router
from app.api.routes.users import router as users_router

__all__ = [
    "auth_router",
    "games_router",
    "online_rooms_router",
    "request_logs_router",
    "users_router",
]
