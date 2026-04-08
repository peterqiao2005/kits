#!/usr/bin/env python3
from app.api.routes.projects import create_project
from app.api.routes.servers import create_server
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.project_link import ProjectLink
from app.models.server import Server
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.schemas.project_link import ProjectLinkCreate
from app.schemas.server import ServerCreate
from sqlalchemy import delete, select


def main() -> None:
    db = SessionLocal()
    try:
        init_db(db, "admin", "admin123")
        admin = db.scalar(select(User).where(User.username == "admin"))
        if admin is None:
            raise RuntimeError("bootstrap admin was not created")

        db.execute(delete(OperationLog))
        db.execute(delete(ProjectLink))
        db.execute(delete(Project))
        db.execute(delete(Server))
        db.commit()

        server = create_server(
            ServerCreate(
                name="local-demo",
                host="127.0.0.1",
                env_type="local",
                description="Local validation host for portal-console.",
                tags=["demo", "local"],
            ),
            admin,
            db,
        )

        create_project(
            ProjectCreate(
                name="portal-online",
                description="Healthy demo project wired to mock Kuma and mock Rundeck.",
                tags=["demo", "online"],
                repo_url="https://example.com/portal-online",
                server_id=server.id,
                deploy_path="/srv/portal-online",
                runtime_type="docker_compose",
                start_note="docker compose up -d",
                stop_note="docker compose down",
                access_note="Available through the demo link.",
                rundeck_job_start_id="portal-online-start",
                rundeck_job_stop_id="portal-online-stop",
                rundeck_job_restart_id="portal-online-restart",
                kuma_monitor_id="demo-online",
                is_favorite=True,
                links=[
                    ProjectLinkCreate(
                        link_type="web",
                        title="Demo Web",
                        url="http://127.0.0.1:8080",
                        sort_order=1,
                    ),
                    ProjectLinkCreate(
                        link_type="docs",
                        title="Docs",
                        url="https://example.com/portal-online/docs",
                        sort_order=2,
                    ),
                ],
            ),
            admin,
            db,
        )

        create_project(
            ProjectCreate(
                name="portal-offline",
                description="Offline demo project to verify status rendering.",
                tags=["demo", "offline"],
                repo_url="https://example.com/portal-offline",
                server_id=server.id,
                deploy_path="/srv/portal-offline",
                runtime_type="systemd_service",
                start_note="systemctl start portal-offline",
                stop_note="systemctl stop portal-offline",
                access_note="This project is expected to show offline.",
                rundeck_job_start_id="portal-offline-start",
                rundeck_job_stop_id="portal-offline-stop",
                rundeck_job_restart_id="portal-offline-restart",
                kuma_monitor_id="demo-offline",
                is_favorite=False,
                links=[
                    ProjectLinkCreate(
                        link_type="admin",
                        title="Admin",
                        url="http://127.0.0.1:8080",
                        sort_order=1,
                    )
                ],
            ),
            admin,
            db,
        )

        create_project(
            ProjectCreate(
                name="portal-degraded",
                description="Degraded demo project for warning state coverage.",
                tags=["demo", "degraded"],
                repo_url="https://example.com/portal-degraded",
                server_id=server.id,
                deploy_path="/srv/portal-degraded",
                runtime_type="pm2_process",
                start_note="pm2 start ecosystem.config.js --only portal-degraded",
                stop_note="pm2 stop portal-degraded",
                access_note="Used to verify degraded state.",
                rundeck_job_start_id="portal-degraded-start",
                rundeck_job_stop_id="portal-degraded-stop",
                rundeck_job_restart_id="portal-degraded-restart",
                kuma_monitor_id="demo-degraded",
                is_favorite=True,
                links=[
                    ProjectLinkCreate(
                        link_type="monitor",
                        title="Monitor",
                        url="http://127.0.0.1:9000/api/status-page/heartbeat/demo-degraded",
                        sort_order=1,
                    )
                ],
            ),
            admin,
            db,
        )

        print("seeded demo data for portal-console")
    finally:
        db.close()


if __name__ == "__main__":
    main()
