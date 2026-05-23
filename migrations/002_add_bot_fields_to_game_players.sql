-- Run manually on existing databases (create_all does not alter existing tables).
ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS is_bot BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE game_players
    ADD COLUMN IF NOT EXISTS bot_difficulty VARCHAR(20);
