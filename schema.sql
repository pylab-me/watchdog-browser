CREATE TABLE IF NOT EXISTS cookie_refresh_tasks (
  id BIGSERIAL PRIMARY KEY,
  site_url TEXT NOT NULL,
  reload_url TEXT,
  state_scope_url TEXT,
  storage_state BYTEA,
  session_storage BYTEA,
  next_poll_at TIMESTAMPTZ NOT NULL,
  refresh_interval_seconds INTEGER NOT NULL DEFAULT 86400,
  retry_interval_seconds INTEGER NOT NULL DEFAULT 900,
  headless BOOLEAN NOT NULL DEFAULT TRUE,
  browser_channel TEXT NOT NULL DEFAULT 'chrome',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  wait_until TEXT NOT NULL DEFAULT 'networkidle',
  settle_time_ms INTEGER NOT NULL DEFAULT 3000,
  remark TEXT NOT NULL DEFAULT '',
  last_refreshed_at TIMESTAMPTZ,
  last_error TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cookie_refresh_tasks_next_poll_at
ON cookie_refresh_tasks (enabled, next_poll_at);
