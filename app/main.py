import asyncio
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    auth_router,
    games_router,
    online_rooms_router,
    request_logs_router,
    users_router,
)
from app.core.config import (
    CORS_ORIGINS,
    ONLINE_DISCONNECT_TIMEOUT_SECONDS,
    ONLINE_PRESENCE_SWEEP_INTERVAL_SECONDS,
    UPLOADS_DIR,
)
from app.core.request_logging import install_request_logging
from app.db.schema_updates import (
    ensure_game_player_presence_columns,
    ensure_user_profile_columns,
)
from app.db.session import Base, SessionLocal, engine
from app.services.online_presence_service import OnlinePresenceService
from app.services.realtime_service import game_connection_manager
import app.models  # noqa: F401 — register ORM models with Base

app = FastAPI(title="DartUP Backend", version="1.0.0")
install_request_logging(app)
online_presence_timeout_task: asyncio.Task | None = None

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

Base.metadata.create_all(bind=engine)
ensure_user_profile_columns(engine)
ensure_game_player_presence_columns(engine)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.include_router(auth_router)
app.include_router(games_router)
app.include_router(online_rooms_router)
app.include_router(request_logs_router)
app.include_router(users_router)


async def _online_presence_timeout_loop() -> None:
    while True:
        await asyncio.sleep(ONLINE_PRESENCE_SWEEP_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            events = OnlinePresenceService(db).process_timeouts(
                ONLINE_DISCONNECT_TIMEOUT_SECONDS,
            )
        finally:
            db.close()

        for event in events:
            await game_connection_manager.send_to_game(
                event.game_id,
                event.event_type,
                event.payload,
                exclude_user_id=event.exclude_user_id,
            )


@app.on_event("startup")
async def start_online_presence_timeout_loop() -> None:
    global online_presence_timeout_task
    if online_presence_timeout_task is None or online_presence_timeout_task.done():
        online_presence_timeout_task = asyncio.create_task(
            _online_presence_timeout_loop(),
        )


@app.on_event("shutdown")
async def stop_online_presence_timeout_loop() -> None:
    if online_presence_timeout_task is None:
        return
    online_presence_timeout_task.cancel()
    with suppress(asyncio.CancelledError):
        await online_presence_timeout_task


@app.get("/")
def root():
    return {"message": "DartUP Backend Running"}
