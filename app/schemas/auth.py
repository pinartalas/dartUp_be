from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SocialLoginRequest(BaseModel):
    provider: str
    provider_user_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    id_token: Optional[str] = None

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> "SocialLoginRequest":
        if self.provider == "google":
            if not self.id_token:
                raise ValueError("google login requires id_token")
        elif not self.provider_user_id:
            raise ValueError("provider_user_id is required")

        return self


class UserResponse(BaseModel):
    id: int
    email: str | None = None
    full_name: str | None = None
    username: str | None = None
    profile_photo_url: str | None = None
    username_changed_at: datetime | None = None
    auth_provider: str
    provider_user_id: str

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    username: str | None = Field(
        None,
        min_length=3,
        max_length=30,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    profile_photo_url: str | None = Field(None, max_length=2048)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("username must not be empty")
        return normalized

    @field_validator("profile_photo_url", mode="before")
    @classmethod
    def normalize_profile_photo_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_update_fields(self) -> "ProfileUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one profile field is required")
        if "username" in self.model_fields_set and self.username is None:
            raise ValueError("username cannot be null")
        return self


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class LogoutResponse(BaseModel):
    message: str
