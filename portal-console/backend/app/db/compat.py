from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import (
    EnvironmentType,
    OperationAction,
    OperationStatus,
    ProjectLinkType,
    ProjectStatus,
    ServerAuthType,
    RuntimeStatus,
    RuntimeType,
    UserRole,
)


def _escape_literal(value: str) -> str:
    return value.replace("'", "''")


def _ensure_enum_type(session: Session, type_name: str, values: list[str]) -> None:
    escaped_values = ", ".join(f"'{_escape_literal(value)}'" for value in values)
    session.execute(
        text(
            "DO $$ BEGIN "
            f"CREATE TYPE {type_name} AS ENUM ({escaped_values}); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
    )
    existing_values = {
        row[0]
        for row in session.execute(
            text(
                "SELECT e.enumlabel "
                "FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :type_name"
            ),
            {"type_name": type_name},
        ).all()
    }
    for value in values:
        if value not in existing_values:
            session.execute(
                text(
                    f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{_escape_literal(value)}'"
                )
            )


def _ensure_column(session: Session, table: str, column: str, definition: str) -> None:
    session.execute(
        text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {definition}')
    )


def _has_column(session: Session, table: str, column: str) -> bool:
    return (
        session.execute(
            text(
                "SELECT 1 "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = :table_name "
                "AND column_name = :column_name"
            ),
            {"table_name": table, "column_name": column},
        ).scalar()
        is not None
    )


def _drop_not_null(session: Session, table: str, column: str) -> None:
    session.execute(
        text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL')
    )


def _normalize_enum_column(
    session: Session, table: str, column: str, type_name: str, enum_class: type
) -> None:
    for item in enum_class:
        if item.name == item.value:
            continue
        session.execute(
            text(
                f'UPDATE "{table}" '
                f'SET "{column}" = CAST(:new_value AS {type_name}) '
                f'WHERE "{column}"::text = :old_value'
            ),
            {"new_value": item.value, "old_value": item.name},
        )


def ensure_schema(session: Session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return

    _ensure_enum_type(session, "environmenttype", [item.value for item in EnvironmentType])
    _ensure_enum_type(session, "serverauthtype", [item.value for item in ServerAuthType])
    _ensure_enum_type(session, "userrole", [item.value for item in UserRole])
    _ensure_enum_type(session, "runtimetype", [item.value for item in RuntimeType])
    _ensure_enum_type(session, "projectlinktype", [item.value for item in ProjectLinkType])
    _ensure_enum_type(session, "operationaction", [item.value for item in OperationAction])
    _ensure_enum_type(session, "operationstatus", [item.value for item in OperationStatus])
    _ensure_enum_type(session, "projectstatus", [item.value for item in ProjectStatus])
    _ensure_enum_type(session, "runtimestatus", [item.value for item in RuntimeStatus])
    session.commit()

    _ensure_column(session, "projects", "runtime_service_name", "VARCHAR(255)")
    _ensure_column(session, "projects", "start_cmd", "TEXT")
    _ensure_column(session, "projects", "stop_cmd", "TEXT")
    _ensure_column(session, "projects", "restart_cmd", "TEXT")
    _ensure_column(
        session,
        "projects",
        "current_status",
        "projectstatus NOT NULL DEFAULT 'unknown'",
    )
    _ensure_column(session, "projects", "last_checked_at", "TIMESTAMPTZ")
    _ensure_column(
        session,
        "projects",
        "http_status",
        "projectstatus NOT NULL DEFAULT 'unknown'",
    )
    _ensure_column(session, "projects", "http_checked_at", "TIMESTAMPTZ")
    _ensure_column(
        session,
        "projects",
        "runtime_status",
        "runtimestatus NOT NULL DEFAULT 'unknown'",
    )
    _ensure_column(session, "projects", "runtime_checked_at", "TIMESTAMPTZ")
    _ensure_column(session, "servers", "ssh_port", "INTEGER NOT NULL DEFAULT 22")
    _ensure_column(session, "servers", "ssh_username", "VARCHAR(128)")
    _ensure_column(
        session,
        "servers",
        "ssh_auth_type",
        "serverauthtype NOT NULL DEFAULT 'ssh_key'",
    )
    _ensure_column(session, "servers", "ssh_password_encrypted", "TEXT")
    _ensure_column(session, "servers", "ssh_key_id", "INTEGER")
    _ensure_column(session, "ssh_keys", "note", "TEXT")
    _ensure_column(session, "ssh_keys", "original_filename", "VARCHAR(255)")
    _ensure_column(session, "ssh_keys", "stored_filename", "VARCHAR(1024)")
    session.commit()

    if _has_column(session, "ssh_keys", "description"):
        session.execute(
            text(
                'UPDATE "ssh_keys" '
                'SET "note" = COALESCE("note", "description") '
                'WHERE "description" IS NOT NULL'
            )
        )
    if _has_column(session, "ssh_keys", "file_path"):
        _drop_not_null(session, "ssh_keys", "file_path")
        session.execute(
            text(
                'UPDATE "ssh_keys" '
                'SET "stored_filename" = COALESCE("stored_filename", "file_path"), '
                '"original_filename" = COALESCE("original_filename", "file_path") '
                'WHERE "file_path" IS NOT NULL'
            )
        )
    session.commit()

    _normalize_enum_column(session, "users", "role", "userrole", UserRole)
    _normalize_enum_column(session, "servers", "env_type", "environmenttype", EnvironmentType)
    _normalize_enum_column(session, "servers", "ssh_auth_type", "serverauthtype", ServerAuthType)
    _normalize_enum_column(session, "projects", "runtime_type", "runtimetype", RuntimeType)
    _normalize_enum_column(
        session, "projects", "current_status", "projectstatus", ProjectStatus
    )
    _normalize_enum_column(session, "projects", "http_status", "projectstatus", ProjectStatus)
    _normalize_enum_column(
        session, "projects", "runtime_status", "runtimestatus", RuntimeStatus
    )
    _normalize_enum_column(
        session, "project_links", "link_type", "projectlinktype", ProjectLinkType
    )
    _normalize_enum_column(
        session, "operation_logs", "action", "operationaction", OperationAction
    )
    _normalize_enum_column(
        session, "operation_logs", "status", "operationstatus", OperationStatus
    )
