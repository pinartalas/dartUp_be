from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import AuthResponse, SocialLoginRequest, UserResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/social-login", response_model=AuthResponse)
def social_login(request: SocialLoginRequest, db: Session = Depends(get_db)):
    if request.provider not in ("apple", "google"):
        raise HTTPException(status_code=400, detail="Unsupported auth provider")

    existing_user = (
        db.query(User)
        .filter(
            User.auth_provider == request.provider,
            User.provider_user_id == request.provider_user_id,
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

    new_user = User(
        email=request.email,
        full_name=request.display_name,
        auth_provider=request.provider,
        provider_user_id=request.provider_user_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(new_user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user,
    }


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
