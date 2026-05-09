CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data (
  user_id TEXT PRIMARY KEY,
  tasks_json TEXT NOT NULL DEFAULT '[]',
  settings_json TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_reminders (
  user_id TEXT NOT NULL,
  reminder_key TEXT NOT NULL,
  sent_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, reminder_key)
);

CREATE INDEX IF NOT EXISTS idx_sent_reminders_sent_at ON sent_reminders(sent_at);
