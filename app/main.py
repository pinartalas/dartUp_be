from fastapi import FastAPI

from app.api.routes import auth_router, games_router, users_router
from app.db.session import Base, engine
import app.models  # noqa: F401 — register ORM models with Base

app = FastAPI(title="DartUP Backend", version="1.0.0")

Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
app.include_router(games_router)
app.include_router(users_router)


@app.get("/")
def root():
    return {"message": "DartUP Backend Running"}
