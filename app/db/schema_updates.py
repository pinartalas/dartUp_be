from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


USER_PROFILE_COLUMNS = {
    "username": "VARCHAR(30)",
    "profile_photo_url": "VARCHAR(2048)",
    "username_changed_at": "TIMESTAMP",
}

GAME_PLAYER_PRESENCE_COLUMNS = {
    "presence_state": "VARCHAR(20) NOT NULL DEFAULT 'online'",
    "last_seen_at": "TIMESTAMP",
    "disconnected_at": "TIMESTAMP",
    "left_at": "TIMESTAMP",
    "leave_reason": "VARCHAR(30)",
}


def ensure_user_profile_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("users")
    }

    with engine.begin() as connection:
        for column_name, column_type in USER_PROFILE_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                )

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username "
                "ON users (username)"
            )
        )


def ensure_game_player_presence_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("game_players"):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("game_players")
    }

    with engine.begin() as connection:
        for column_name, column_type in GAME_PLAYER_PRESENCE_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE game_players "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_game_players_presence_state "
                "ON game_players (presence_state)"
            )
        )
