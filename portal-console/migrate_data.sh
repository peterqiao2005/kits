#!/usr/bin/env bash
# Migrate real user data from old Postgres (portal-console-backup) into the
# new SQLite database, then optionally push to the remote host via sync_data.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="$SCRIPT_DIR/backend/data/portal_console.db"
PUSH=false

usage() {
  cat <<EOF
Usage: $0 [--push] [--help]

  --push   After migrating locally, run sync_data.sh to push to remote host.
  --help   Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

if [ ! -f "$DB" ]; then
  echo "ERROR: SQLite database not found at $DB"
  exit 1
fi

echo "=== Migrating user data from Postgres → SQLite ==="
echo "Target: $DB"
echo ""

sqlite3 "$DB" <<'SQL'
-- ── SSH Keys ─────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO ssh_keys (id, name, note, original_filename, stored_filename)
VALUES
  (5,  'peterqiao0612',    NULL, 'peterqiao0612',    '9d175b2923bf41be91c4a2253f9b68f1.key'),
  (10, 'peter_sn51_private', NULL, 'peter_sn51_private', 'a9f019b23ab24e17be622e112a99bb24.key');

-- ── Servers ──────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO servers
  (id, name, host, os_type, ssh_port, ssh_username, ssh_auth_type,
   ssh_password_encrypted, ssh_key_id, env_type, description, tags)
VALUES
  (47, 'test-windows-server', '192.168.1.100',   'windows', 8008,  NULL, 'ssh_key', NULL, NULL, 'public', 'A Windows Server test', '["win","test"]'),
  (48, 'test-win-api',        '192.168.1.111',   'windows', 8008,  NULL, 'ssh_key', NULL, NULL, 'public', 'test-desc',             '["win"]'),
  (50, 'i9-105',              '192.168.100.105', 'windows', 18008, NULL, 'ssh_key', NULL, NULL, 'public', NULL,                    '[]');

-- ── Projects ─────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO projects
  (id, name, description, tags, deploy_path, runtime_type,
   start_cmd, stop_cmd, restart_cmd,
   is_favorite, current_status, http_status, runtime_status, server_id)
VALUES
  (89, 'novel_creator_console', NULL, '[]', NULL, 'cmd',
   'wsl -u root -- bash -c "nohup npm --prefix /root/novels_creator run dev > /dev/null 2>&1 &"',
   'wsl -u root -- pkill -f "novels_creator"',
   'wsl -u root -- bash -c "pkill -f ''novels_creator''; nohup npm --prefix /root/novels_creator run dev > /dev/null 2>&1 &"',
   1, 'unknown', 'unknown', 'unknown', 50);

-- ── Project Links ─────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO project_links (id, project_id, link_type, title, url, sort_order)
VALUES
  (83, 89, 'web', 'Novel Creator', 'http://localhost:3000/', 1);
SQL

echo "Migration complete. Verifying row counts:"
sqlite3 "$DB" "
SELECT 'servers'       AS tbl, COUNT(*) AS total, SUM(CASE WHEN id IN (47,48,50) THEN 1 ELSE 0 END) AS migrated FROM servers
UNION ALL
SELECT 'ssh_keys',     COUNT(*), SUM(CASE WHEN id IN (5,10)  THEN 1 ELSE 0 END) FROM ssh_keys
UNION ALL
SELECT 'projects',     COUNT(*), SUM(CASE WHEN id IN (89)    THEN 1 ELSE 0 END) FROM projects
UNION ALL
SELECT 'project_links',COUNT(*), SUM(CASE WHEN id IN (83)    THEN 1 ELSE 0 END) FROM project_links;
"

if [ "$PUSH" = true ]; then
  echo ""
  echo "=== Pushing data to remote host ==="
  bash "$SCRIPT_DIR/sync_data.sh"
fi
