import re
import unicodedata

from sqlalchemy.orm import Session

from app.models.user import User


USERNAME_MAX_LENGTH = 30
USERNAME_MIN_LENGTH = 3
DEFAULT_USERNAME_BASE = "dart_player"
NON_USERNAME_CHARS = re.compile(r"[^a-z0-9_]+")
REPEATED_UNDERSCORES = re.compile(r"_+")


def generate_default_username(
    db: Session,
    *,
    display_name: str | None,
    email: str | None,
) -> str:
    base = (
        _normalize_username_seed(display_name)
        or _normalize_username_seed(_email_local_part(email))
        or DEFAULT_USERNAME_BASE
    )
    return _unique_username(db, base)


def _normalize_username_seed(value: str | None) -> str:
    if value is None:
        return ""

    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    normalized = NON_USERNAME_CHARS.sub("_", normalized)
    normalized = REPEATED_UNDERSCORES.sub("_", normalized).strip("_")
    if len(normalized) < USERNAME_MIN_LENGTH:
        return ""
    return normalized[:USERNAME_MAX_LENGTH]


def _email_local_part(email: str | None) -> str | None:
    if email is None:
        return None
    return email.split("@", 1)[0]


def _unique_username(db: Session, base: str) -> str:
    candidate = base[:USERNAME_MAX_LENGTH]
    if _is_username_available(db, candidate):
        return candidate

    for number in range(2, 10000):
        suffix = f"_{number}"
        truncated_base = base[: USERNAME_MAX_LENGTH - len(suffix)]
        candidate = f"{truncated_base}{suffix}"
        if _is_username_available(db, candidate):
            return candidate

    raise RuntimeError("Could not generate a unique username")


def _is_username_available(db: Session, username: str) -> bool:
    return db.query(User.id).filter(User.username == username).first() is None
