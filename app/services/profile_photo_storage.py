import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import PROFILE_PHOTO_MAX_BYTES, PROFILE_PHOTO_UPLOAD_DIR
from app.core.exceptions import ProfileError


ALLOWED_PROFILE_PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
UPLOAD_CHUNK_SIZE = 1024 * 1024


class LocalProfilePhotoStorage:
    def __init__(self, upload_dir: Path = PROFILE_PHOTO_UPLOAD_DIR):
        self.upload_dir = upload_dir

    async def save(self, file: UploadFile) -> str:
        destination: Path | None = None

        try:
            file_extension = ALLOWED_PROFILE_PHOTO_TYPES.get(file.content_type or "")
            if file_extension is None:
                raise ProfileError("Unsupported profile photo type", status_code=415)

            self.upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f"avatar-{uuid.uuid4().hex}{file_extension}"
            destination = self.upload_dir / filename

            bytes_written = 0
            with destination.open("wb") as output:
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    bytes_written += len(chunk)
                    if bytes_written > PROFILE_PHOTO_MAX_BYTES:
                        raise ProfileError(
                            "Profile photo must be 5MB or smaller",
                            status_code=413,
                        )
                    output.write(chunk)
            if bytes_written == 0:
                raise ProfileError("Profile photo must not be empty", status_code=400)
        except Exception:
            if destination is not None:
                destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

        return filename
