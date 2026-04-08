import os
from pathlib import Path

from app.api.routes.operation_logs import list_operation_logs
from app.api.routes.servers import create_server
from app.api.routes.services import (
    create_service,
    list_services,
    restart_service,
    sync_service_status,
)
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.ssh_key import SshKey
from app.models.user import User
from app.schemas.server import ServerCreate
from app.schemas.service import ServiceCreate, StatusSyncRequest
from app.schemas.ssh_key import build_ssh_key_read
from app.services.auth import authenticate_user
from sqlalchemy import select


def get_admin(db) -> User:
    username = os.environ.get("FIRST_SUPERUSER", "admin")
    password = os.environ.get("FIRST_SUPERUSER_PASSWORD", "admin123")
    init_db(db, username, password)

    user = authenticate_user(db, username, password)
    assert user is not None, "Admin authentication failed."
    return user


def main() -> None:
    missing_key_path = Path("/tmp/portal-console-missing-key.pem")
    if missing_key_path.exists():
        missing_key_path.unlink()

    with SessionLocal() as db:
        admin = get_admin(db)

        key_record = SshKey(
            name="missing-key",
            file_path=str(missing_key_path),
            description="missing on purpose",
        )
        db.add(key_record)
        db.commit()
        db.refresh(key_record)
        key = build_ssh_key_read(key_record)

        server = create_server(
            payload=ServerCreate(
                name="demo-server",
                host="127.0.0.1",
                ssh_port=22,
                ssh_user="root",
                description="local test server",
                ssh_key_id=key.id,
            ),
            _=admin,
            db=db,
        )

        service = create_service(
            payload=ServiceCreate(
                server_id=server.id,
                name="demo-service",
                description="smoke test service",
                service_type="web",
                internal_url="http://127.0.0.1:65535",
                external_url="http://127.0.0.1:65535",
                primary_url="external",
                force_external=False,
                start_cmd="echo start",
                stop_cmd="echo stop",
                restart_cmd="echo restart",
            ),
            _=admin,
            db=db,
        )

        services = list_services(
            search=None,
            server_id=None,
            status_filter=None,
            _=admin,
            db=db,
        )
        assert len(services) == 1, services

        statuses = sync_service_status(
            payload=StatusSyncRequest(service_ids=[service.id]),
            _=admin,
            db=db,
        )
        assert len(statuses) == 1, statuses
        assert statuses[0].status.value == "offline", statuses

        restart = restart_service(
            service_id=service.id,
            current_user=admin,
            db=db,
        )
        assert restart["status"] == "failed", restart
        assert "Update the key path and try again" in restart["message"], restart

        logs = list_operation_logs(
            service_id=service.id,
            action=None,
            status_filter=None,
            _=admin,
            db=db,
        )
        assert len(logs) == 1, logs

        created_user = db.scalar(select(User).where(User.username == admin.username))
        assert created_user is not None

        print(
            {
                "admin": admin.username,
                "key_available": key.is_available,
                "server": server.name,
                "service": service.name,
                "service_status": statuses[0].status.value,
                "restart_status": restart["status"],
                "restart_message": restart["message"],
                "log_count": len(logs),
            }
        )


if __name__ == "__main__":
    main()
