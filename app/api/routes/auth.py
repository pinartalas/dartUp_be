from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LogoutResponse,
    SocialLoginRequest,
    UserResponse,
)
from app.services.google_auth_service import GoogleAuthError, verify_google_id_token
from app.services.online_room_service import OnlineRoomService

router = APIRouter(tags=["auth"])

EMAIL_ALREADY_REGISTERED_MESSAGE = (
    "Bu e-posta adresi zaten kayıtlı. Lütfen farklı bir adres ile giriş yapınız."
)


@router.post("/auth/social-login", response_model=AuthResponse)
def social_login(request: SocialLoginRequest, db: Session = Depends(get_db)):
    if request.provider not in ("apple", "google"):
        raise HTTPException(status_code=400, detail="Unsupported auth provider")

    provider = request.provider
    provider_user_id = request.provider_user_id
    email = request.email
    display_name = request.display_name

    if request.provider == "google":
        try:
            google_identity = verify_google_id_token(request.id_token or "")
        except GoogleAuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        provider_user_id = google_identity.provider_user_id
        email = google_identity.email
        display_name = google_identity.display_name

    existing_user = (
        db.query(User)
        .filter(
            User.auth_provider == provider,
            User.provider_user_id == provider_user_id,
        )
        .first()
    )

    if existing_user:
        access_token = create_access_token(existing_user.id)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": existing_user,
        }

    if email:
        conflicting_user = db.query(User).filter(User.email == email).first()
        if conflicting_user:
            raise HTTPException(
                status_code=409,
                detail=EMAIL_ALREADY_REGISTERED_MESSAGE,
            )

    new_user = User(
        email=email,
        full_name=display_name,
        auth_provider=provider,
        provider_user_id=provider_user_id,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=EMAIL_ALREADY_REGISTERED_MESSAGE,
        ) from exc
    db.refresh(new_user)

    access_token = create_access_token(new_user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user,
    }


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    OnlineRoomService(db).cancel_waiting_rooms_for_user(current_user.id)
    return {"message": "Logged out successfully"}


@router.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@router.get("/users/{user_id}", response_model=AuthResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    access_token = create_access_token(user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }
