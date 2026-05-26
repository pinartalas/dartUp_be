import asyncio
from datetime import datetime, timedelta

import pytest

from app.api.routes import users as user_routes
from app.core.exceptions import ProfileError
from app.schemas.auth import ProfileUpdateRequest
from app.services import profile_photo_storage
from app.services.profile_photo_storage import LocalProfilePhotoStorage
from app.services.profile_service import ProfileService


class FakeUploadFile:
    def __init__(self, content: bytes, content_type: str):
        self.content = content
        self.content_type = content_type
        self.offset = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size == -1:
            size = len(self.content) - self.offset
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


class FakeRequest:
    def url_for(self, name: str, *, path: str) -> str:
        assert name == "uploads"
        return f"https://testserver/uploads/{path}"


def test_update_profile_sets_username(db_session, owner):
    service = ProfileService(db_session)

    updated_user = service.update_profile(
        owner,
        ProfileUpdateRequest(username=" Dart_Player "),
    )

    assert updated_user.username == "dart_player"
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


def test_update_profile_photo_allows_photo_change_during_username_cooldown(
    db_session,
    owner,
):
    owner.username = "current_name"
    owner.username_changed_at = datetime.utcnow()
    db_session.commit()

    service = ProfileService(db_session)

    profile_photo_url = service.update_profile_photo(
        owner,
        "https://example.com/new-avatar.png",
    )

    assert profile_photo_url == "https://example.com/new-avatar.png"
    assert owner.username == "current_name"
    assert owner.profile_photo_url == "https://example.com/new-avatar.png"


def test_profile_photo_storage_saves_supported_image(tmp_path):
    storage = LocalProfilePhotoStorage(upload_dir=tmp_path)
    file = FakeUploadFile(b"image-bytes", "image/png")

    filename = asyncio.run(storage.save(file))

    assert filename.startswith("avatar-")
    assert filename.endswith(".png")
    assert (tmp_path / filename).read_bytes() == b"image-bytes"
    assert file.closed is True


def test_profile_photo_storage_rejects_unsupported_type(tmp_path):
    storage = LocalProfilePhotoStorage(upload_dir=tmp_path)
    file = FakeUploadFile(b"not-an-image", "text/plain")

    with pytest.raises(ProfileError) as exc_info:
        asyncio.run(storage.save(file))

    assert exc_info.value.status_code == 415
    assert file.closed is True


def test_profile_photo_storage_rejects_empty_file(tmp_path):
    storage = LocalProfilePhotoStorage(upload_dir=tmp_path)
    file = FakeUploadFile(b"", "image/png")

    with pytest.raises(ProfileError) as exc_info:
        asyncio.run(storage.save(file))

    assert exc_info.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_profile_photo_storage_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_photo_storage, "PROFILE_PHOTO_MAX_BYTES", 5)
    storage = LocalProfilePhotoStorage(upload_dir=tmp_path)
    file = FakeUploadFile(b"too-large", "image/webp")

    with pytest.raises(ProfileError) as exc_info:
        asyncio.run(storage.save(file))

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_upload_my_profile_photo_updates_user_and_returns_public_url(
    db_session,
    owner,
    tmp_path,
    monkeypatch,
):
    class TestStorage(LocalProfilePhotoStorage):
        def __init__(self):
            super().__init__(upload_dir=tmp_path)

    monkeypatch.setattr(user_routes, "LocalProfilePhotoStorage", TestStorage)

    response = asyncio.run(
        user_routes.upload_my_profile_photo(
            FakeRequest(),
            FakeUploadFile(b"image-bytes", "image/jpeg"),
            db_session,
            owner,
        )
    )

    assert response["profile_photo_url"].startswith(
        "https://testserver/uploads/profile-photos/avatar-"
    )
    assert response["profile_photo_url"].endswith(".jpg")
    assert owner.profile_photo_url == response["profile_photo_url"]
