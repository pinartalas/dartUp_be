-- Run manually on existing databases (create_all does not alter existing tables).
ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS presence_state VARCHAR(20) NOT NULL DEFAULT 'online';

ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS disconnected_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS left_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS leave_reason VARCHAR(30);

CREATE INDEX IF NOT EXISTS ix_game_players_presence_state
    ON game_players (presence_state);
