from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import GOOGLE_CLIENT_IDS


@dataclass(frozen=True)
class GoogleIdentity:
    provider_user_id: str
    email: str | None
    display_name: str | None


class GoogleAuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def verify_google_id_token(id_token: str) -> GoogleIdentity:
    if not GOOGLE_CLIENT_IDS:
        raise GoogleAuthError("Google client IDs are not configured", status_code=500)

    last_error: Exception | None = None
    payload: dict | None = None
    request = google_requests.Request()

    for client_id in GOOGLE_CLIENT_IDS:
        try:
            payload = google_id_token.verify_oauth2_token(
                id_token,
                request,
                client_id,
            )
            break
        except ValueError as exc:
            last_error = exc

    if payload is None:
        raise GoogleAuthError("Invalid Google id_token") from last_error

    provider_user_id = payload.get("sub")
    if not provider_user_id:
        raise GoogleAuthError("Google id_token is missing subject")

    return GoogleIdentity(
        provider_user_id=provider_user_id,
        email=payload.get("email"),
        display_name=payload.get("name"),
    )
