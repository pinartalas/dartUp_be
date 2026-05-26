from datetime import datetime, timedelta

import pytest

from app.core.exceptions import ProfileError
from app.schemas.auth import ProfileUpdateRequest
from app.services.profile_service import ProfileService


def test_update_profile_sets_username_and_photo(db_session, owner):
    service = ProfileService(db_session)

    updated_user = service.update_profile(
        owner,
        ProfileUpdateRequest(
            username=" Dart_Player ",
            profile_photo_url="https://example.com/avatar.png",
        ),
    )

    assert updated_user.username == "dart_player"
    assert updated_user.profile_photo_url == "https://example.com/avatar.png"
    assert updated_user.username_changed_at is not None


def test_update_profile_blocks_username_change_within_cooldown(
    db_session,
    owner,
):
    owner.username = "old_name"
    owner.username_changed_at = datetime.utcnow() - timedelta(days=13)
    db_session.commit()

    service = ProfileService(db_session)

    with pytest.raises(ProfileError) as exc_info:
        service.update_profile(owner, ProfileUpdateRequest(username="new_name"))

    assert exc_info.value.status_code == 429
    assert owner.username == "old_name"


def test_update_profile_allows_username_change_after_cooldown(
    db_session,
    owner,
):
    owner.username = "old_name"
    owner.username_changed_at = datetime.utcnow() - timedelta(days=14, minutes=1)
    db_session.commit()

    service = ProfileService(db_session)

    updated_user = service.update_profile(
        owner,
        ProfileUpdateRequest(username="new_name"),
    )

    assert updated_user.username == "new_name"


def test_update_profile_rejects_taken_username(db_session, owner, other_user):
    other_user.username = "taken_name"
    db_session.commit()

    service = ProfileService(db_session)

    with pytest.raises(ProfileError) as exc_info:
        service.update_profile(owner, ProfileUpdateRequest(username="taken_name"))

    assert exc_info.value.status_code == 409


def test_update_profile_allows_photo_change_during_username_cooldown(
    db_session,
    owner,
):
    owner.username = "current_name"
    owner.username_changed_at = datetime.utcnow()
    db_session.commit()

    service = ProfileService(db_session)

    updated_user = service.update_profile(
        owner,
        ProfileUpdateRequest(profile_photo_url="https://example.com/new-avatar.png"),
    )

    assert updated_user.username == "current_name"
    assert updated_user.profile_photo_url == "https://example.com/new-avatar.png"
