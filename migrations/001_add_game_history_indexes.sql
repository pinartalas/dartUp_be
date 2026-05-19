-- Run manually on existing databases (create_all does not alter existing tables).
CREATE INDEX IF NOT EXISTS ix_games_finished_at ON games (finished_at);
CREATE INDEX IF NOT EXISTS ix_games_owner_status_finished
    ON games (owner_id, status, finished_at);
