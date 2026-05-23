import pytest
from pydantic import ValidationError

from app.api.routes import auth as auth_routes
from app.models.user import User
from app.schemas.auth import SocialLoginRequest
from app.services.google_auth_service import GoogleIdentity


def test_google_social_login_uses_verified_token_payload(db_session, monkeypatch):
    def fake_verify_google_id_token(id_token: str) -> GoogleIdentity:
        assert id_token == "valid-id-token"
        return GoogleIdentity(
            provider_user_id="google-sub-123",
            email="verified@example.com",
            display_name="Verified User",
        )

    monkeypatch.setattr(
        auth_routes,
        "verify_google_id_token",
        fake_verify_google_id_token,
    )

    response = auth_routes.social_login(
        SocialLoginRequest(
            provider="google",
            id_token="valid-id-token",
            provider_user_id="spoofed-sub",
            email="spoofed@example.com",
            display_name="Spoofed User",
        ),
        db_session,
    )

    user = response["user"]
    assert response["token_type"] == "bearer"
    assert user.auth_provider == "google"
    assert user.provider_user_id == "google-sub-123"
    assert user.email == "verified@example.com"
    assert user.full_name == "Verified User"


def test_google_social_login_finds_existing_user_by_verified_sub(
    db_session,
    monkeypatch,
):
    existing_user = User(
        email="old@example.com",
        full_name="Old Name",
        auth_provider="google",
        provider_user_id="google-sub-123",
    )
    db_session.add(existing_user)
    db_session.commit()
    db_session.refresh(existing_user)

    monkeypatch.setattr(
        auth_routes,
        "verify_google_id_token",
        lambda _: GoogleIdentity(
            provider_user_id="google-sub-123",
            email="new@example.com",
            display_name="New Name",
        ),
    )

    response = auth_routes.social_login(
        SocialLoginRequest(provider="google", id_token="valid-id-token"),
        db_session,
    )

    assert response["user"].id == existing_user.id
    assert db_session.query(User).filter(User.auth_provider == "google").count() == 1


def test_google_social_login_requires_id_token():
    with pytest.raises(ValidationError):
        SocialLoginRequest(provider="google")
