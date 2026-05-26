from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ProfileError
from app.models.user import User
from app.schemas.auth import ProfileUpdateRequest


USERNAME_CHANGE_COOLDOWN = timedelta(days=14)


class ProfileService:
    def __init__(self, db: Session):
        self.db = db

    def update_profile(
        self,
        user: User,
        request: ProfileUpdateRequest,
    ) -> User:
        if "username" in request.model_fields_set:
            self._update_username(user, request.username)

        if "profile_photo_url" in request.model_fields_set:
            user.profile_photo_url = request.profile_photo_url

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ProfileError("Username is already taken", status_code=409) from exc

        self.db.refresh(user)
        return user

    def _update_username(self, user: User, username: str | None) -> None:
        if username is None or username == user.username:
            return

        self._ensure_username_is_available(username, user.id)
        self._ensure_username_change_allowed(user)

        user.username = username
        user.username_changed_at = datetime.utcnow()

    def _ensure_username_is_available(self, username: str, user_id: int) -> None:
        existing_user = (
            self.db.query(User)
            .filter(User.username == username, User.id != user_id)
            .first()
        )
        if existing_user:
            raise ProfileError("Username is already taken", status_code=409)

    def _ensure_username_change_allowed(self, user: User) -> None:
        if user.username_changed_at is None:
            return

        next_allowed_at = user.username_changed_at + USERNAME_CHANGE_COOLDOWN
        if datetime.utcnow() < next_allowed_at:
            raise ProfileError(
                "Username can only be changed once every 14 days",
                status_code=429,
            )
