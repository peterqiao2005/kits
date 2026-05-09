#!/usr/bin/env python3
import argparse
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Register Todoist CF in GamePortal apps table.")
    parser.add_argument("--portal-db", default=r"D:\GitHub\games\portal\instance\portal.db")
    parser.add_argument("--slug", default="todoist-cf")
    parser.add_argument("--name", default="Todoist CF")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--sso-secret", required=True)
    parser.add_argument("--description", default="Cloudflare 版完成重复待办与多通道提醒")
    args = parser.parse_args()

    db_path = Path(args.portal_db)
    if not db_path.exists():
        raise SystemExit(f"portal db not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        upsert_app(conn, args)
        conn.commit()
        row = conn.execute(
            "SELECT slug, name, base_url, access_type, is_active FROM apps WHERE slug = ?",
            (args.slug,),
        ).fetchone()
        print(row)
    finally:
        conn.close()


def ensure_schema(conn):
    app_cols = {row[1] for row in conn.execute("PRAGMA table_info(apps)").fetchall()}
    if "access_type" not in app_cols:
        conn.execute("ALTER TABLE apps ADD COLUMN access_type VARCHAR(32) NOT NULL DEFAULT 'default_open'")
    if "image_path" not in app_cols:
        conn.execute("ALTER TABLE apps ADD COLUMN image_path VARCHAR(255)")

    perm_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_app_permissions)").fetchall()}
    if "status" not in perm_cols:
        conn.execute("ALTER TABLE user_app_permissions ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'granted'")


def upsert_app(conn, args):
    existing = conn.execute("SELECT id FROM apps WHERE slug = ?", (args.slug,)).fetchone()
    values = {
        "slug": args.slug,
        "name": args.name,
        "base_url": args.base_url.rstrip("/"),
        "sso_secret": args.sso_secret,
        "description": args.description,
        "is_active": 1,
        "access_type": "default_open",
    }
    if existing:
        assignments = ", ".join(f"{key} = ?" for key in values)
        conn.execute(f"UPDATE apps SET {assignments} WHERE slug = ?", [*values.values(), args.slug])
        return

    values["id"] = str(uuid.uuid4())
    values["created_at"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    keys = list(values)
    placeholders = ", ".join("?" for _ in keys)
    conn.execute(
        f"INSERT INTO apps ({', '.join(keys)}) VALUES ({placeholders})",
        [values[key] for key in keys],
    )


if __name__ == "__main__":
    main()
