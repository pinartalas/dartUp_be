from app.api.routes.auth import router as auth_router
from app.api.routes.games import router as games_router
from app.api.routes.users import router as users_router

__all__ = ["auth_router", "games_router", "users_router"]
