from typing import Optional

from pydantic import BaseModel


class SocialLoginRequest(BaseModel):
    provider: str
    provider_user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None


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
