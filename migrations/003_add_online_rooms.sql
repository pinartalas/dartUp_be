-- Run manually on existing databases (create_all does not alter existing tables).
CREATE TABLE IF NOT EXISTS online_rooms (
    id SERIAL PRIMARY KEY,
    room_uuid VARCHAR(36) NOT NULL UNIQUE,
    room_code VARCHAR(12) NOT NULL UNIQUE,
    host_user_id INTEGER NOT NULL REFERENCES users(id),
    guest_user_id INTEGER REFERENCES users(id),
    game_id INTEGER REFERENCES games(id),
    host_player_name VARCHAR NOT NULL,
    guest_player_name VARCHAR,
    game_type VARCHAR(20) NOT NULL,
    game_variant INTEGER,
    settings JSON NOT NULL DEFAULT '{}'::json,
    status VARCHAR(20) NOT NULL DEFAULT 'waiting',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_online_rooms_room_uuid ON online_rooms (room_uuid);
CREATE INDEX IF NOT EXISTS ix_online_rooms_room_code ON online_rooms (room_code);
CREATE INDEX IF NOT EXISTS ix_online_rooms_host_user_id ON online_rooms (host_user_id);
CREATE INDEX IF NOT EXISTS ix_online_rooms_guest_user_id ON online_rooms (guest_user_id);
CREATE INDEX IF NOT EXISTS ix_online_rooms_game_id ON online_rooms (game_id);
CREATE INDEX IF NOT EXISTS ix_online_rooms_status ON online_rooms (status);
CREATE INDEX IF NOT EXISTS ix_online_rooms_game_type ON online_rooms (game_type);
CREATE INDEX IF NOT EXISTS ix_online_rooms_status_created
    ON online_rooms (status, created_at);
