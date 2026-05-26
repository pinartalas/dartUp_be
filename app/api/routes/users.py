from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.exceptions import GameHistoryError, ProfileError
from app.models.user import User
from app.schemas.auth import (
    ProfilePhotoUploadResponse,
    ProfileUpdateRequest,
    UserResponse,
)
from app.schemas.game import GameStatus, GameType
from app.schemas.game_history import (
    GameHistoryListResponse,
    GameHistoryQueryParams,
    HistoryPeriod,
)
from app.services.game_history_service import GameHistoryService
from app.services.profile_photo_storage import LocalProfilePhotoStorage
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/users", tags=["users"])


def _handle_history_error(exc: GameHistoryError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _handle_profile_error(exc: ProfileError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.patch("/me/profile", response_model=UserResponse)
def update_my_profile(
    request: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProfileService(db)
    try:
        return service.update_profile(current_user, request)
    except ProfileError as exc:
        _handle_profile_error(exc)


@router.post("/me/profile/photo", response_model=ProfilePhotoUploadResponse)
async def upload_my_profile_photo(
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    storage = LocalProfilePhotoStorage()
    service = ProfileService(db)
    try:
        filename = await storage.save(photo)
        profile_photo_url = str(
            request.url_for("uploads", path=f"profile-photos/{filename}")
        )
        return {
            "profile_photo_url": service.update_profile_photo(
                current_user,
                profile_photo_url,
            )
        }
    except ProfileError as exc:
        _handle_profile_error(exc)


@router.get("/me/game-history", response_model=GameHistoryListResponse)
def get_my_game_history(
    period: Annotated[Optional[HistoryPeriod], Query()] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate")] = None,
    game_type: Annotated[Optional[GameType], Query(alias="gameType")] = None,
    game_mode: Annotated[Optional[int], Query(alias="gameMode")] = None,
    status: Annotated[Optional[GameStatus], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        params = GameHistoryQueryParams(
            period=period,
            startDate=start_date,
            endDate=end_date,
            gameType=game_type,
            gameMode=game_mode,
            status=status,
            page=page,
            limit=limit,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    service = GameHistoryService(db)
    try:
        return service.get_user_game_history(current_user.id, params)
    except GameHistoryError as exc:
        _handle_history_error(exc)
