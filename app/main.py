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
from app.core.config import CORS_ORIGINS, UPLOADS_DIR
from app.core.request_logging import install_request_logging
from app.db.schema_updates import ensure_user_profile_columns
from app.db.session import Base, engine
import app.models  # noqa: F401 — register ORM models with Base

app = FastAPI(title="DartUP Backend", version="1.0.0")
install_request_logging(app)

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
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.include_router(auth_router)
app.include_router(games_router)
app.include_router(online_rooms_router)
app.include_router(request_logs_router)
app.include_router(users_router)


@app.get("/")
def root():
    return {"message": "DartUP Backend Running"}
