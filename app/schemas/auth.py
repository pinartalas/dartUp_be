from typing import Optional

from pydantic import BaseModel, model_validator


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
    auth_provider: str
    provider_user_id: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class LogoutResponse(BaseModel):
    message: str
