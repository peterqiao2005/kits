from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_db, require_admin
from app.models.enums import (
    OperationAction,
    OperationStatus,
    ProjectStatus,
    RuntimeStatus,
    RuntimeType,
)
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.project_link import ProjectLink
from app.models.server import Server
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    ProjectStatusRead,
    ProjectUpdate,
    StatusSyncRequest,
)
from app.schemas.project_link import (
    ProjectLinkCreate,
    ProjectLinkRead,
    ProjectLinkUpdate,
)
from app.schemas.server import ServerRead
from app.schemas.ssh_key import SSHKeySummaryRead
from app.services.command_templates import build_default_commands, ensure_nohup
from app.services.http_probe import check_http_status
from app.services.runtime_status import check_runtime_status
from app.services.ssh_runner import run_ssh_command

router = APIRouter(tags=["projects"])


def build_server_read(server: Server) -> ServerRead:
    return ServerRead(
        id=server.id,
        name=server.name,
        host=server.host,
        ssh_port=server.ssh_port,
        ssh_username=server.ssh_username,
        ssh_auth_type=server.ssh_auth_type,
        ssh_key_id=server.ssh_key_id,
        env_type=server.env_type,
        description=server.description,
        tags=server.tags or [],
        has_ssh_password=bool(server.ssh_password_encrypted),
        ssh_key=SSHKeySummaryRead.model_validate(server.ssh_key) if server.ssh_key else None,
        created_at=server.created_at,
        updated_at=server.updated_at,
        project_count=len(server.projects),
    )


def build_project_read(project: Project) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        tags=project.tags or [],
        repo_url=project.repo_url,
        server_id=project.server_id,
        deploy_path=project.deploy_path,
        runtime_type=project.runtime_type,
        start_note=project.start_note,
        stop_note=project.stop_note,
        access_note=project.access_note,
        runtime_service_name=project.runtime_service_name,
        start_cmd=project.start_cmd,
        stop_cmd=project.stop_cmd,
        restart_cmd=project.restart_cmd,
        rundeck_job_start_id=project.rundeck_job_start_id,
        rundeck_job_stop_id=project.rundeck_job_stop_id,
        rundeck_job_restart_id=project.rundeck_job_restart_id,
        kuma_monitor_id=project.kuma_monitor_id,
        is_favorite=project.is_favorite,
        current_status=project.current_status,
        last_checked_at=project.last_checked_at,
        http_status=project.http_status,
        http_checked_at=project.http_checked_at,
        runtime_status=project.runtime_status,
        runtime_checked_at=project.runtime_checked_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
        server=build_server_read(project.server),
        links=[
            ProjectLinkRead.model_validate(link)
            for link in sorted(project.links, key=lambda item: item.sort_order)
        ],
        can_start=bool(project.start_cmd),
        can_stop=bool(project.stop_cmd),
        can_restart=bool(project.restart_cmd),
    )


def _normalize_commands(project: Project) -> None:
    for field in ("start_cmd", "stop_cmd", "restart_cmd"):
        value = getattr(project, field)
        if isinstance(value, str) and not value.strip():
            setattr(project, field, None)


def _default_log_path(project: Project) -> str:
    safe_name = (project.runtime_service_name or project.name or "service").replace(" ", "_")
    return f"/tmp/portal-console-{safe_name}.log"


def apply_default_commands(project: Project, prefer_defaults: bool = False) -> None:
    defaults = build_default_commands(project)
    if prefer_defaults or project.start_cmd is None:
        project.start_cmd = defaults.start_cmd or project.start_cmd
    if prefer_defaults or project.stop_cmd is None:
        project.stop_cmd = defaults.stop_cmd or project.stop_cmd
    if prefer_defaults or project.restart_cmd is None:
        project.restart_cmd = defaults.restart_cmd or project.restart_cmd

    if project.runtime_type in {RuntimeType.CMD, RuntimeType.CUSTOM}:
        log_path = _default_log_path(project)
        project.start_cmd = ensure_nohup(project.start_cmd, log_path)
        project.restart_cmd = ensure_nohup(project.restart_cmd, log_path)


@router.get("/projects", response_model=list[ProjectListItem])
def list_projects(
    search: str | None = None,
    server_id: int | None = None,
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    runtime_type: RuntimeType | None = None,
    favorite_only: bool = False,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectListItem]:
    stmt = (
        select(Project)
        .options(
            selectinload(Project.server).selectinload(Server.projects),
            selectinload(Project.links),
        )
        .order_by(Project.name)
    )
    projects = db.scalars(stmt).all()

    def matches(project: Project) -> bool:
        if (
            search
            and search.lower()
            not in f"{project.name} {project.description or ''}".lower()
        ):
            return False
        if server_id and project.server_id != server_id:
            return False
        if status_filter and project.http_status != status_filter:
            return False
        if runtime_type and project.runtime_type != runtime_type:
            return False
        if favorite_only and not project.is_favorite:
            return False
        return True

    filtered = [project for project in projects if matches(project)]
    return [
        ProjectListItem(**build_project_read(project).model_dump())
        for project in filtered
    ]


@router.post(
    "/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED
)
def create_project(
    payload: ProjectCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectRead:
    server = db.get(Server, payload.server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Server not found."
        )

    data = payload.model_dump(exclude={"links"})
    project = Project(**data)
    _normalize_commands(project)
    apply_default_commands(project)
    project.links = [ProjectLink(**link.model_dump()) for link in payload.links]
    db.add(project)
    db.commit()
    db.refresh(project)
    db.refresh(server)
    return build_project_read(project)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.server).selectinload(Server.projects),
            selectinload(Project.links),
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    return build_project_read(project)


@router.put("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.server).selectinload(Server.projects),
            selectinload(Project.links),
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    updates = payload.model_dump(exclude_unset=True)
    if "server_id" in updates and db.get(Server, updates["server_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Server not found."
        )

    for field, value in updates.items():
        setattr(project, field, value)

    _normalize_commands(project)

    commands_provided = any(
        key in updates for key in ("start_cmd", "stop_cmd", "restart_cmd")
    )
    runtime_changed = any(
        key in updates for key in ("runtime_type", "runtime_service_name", "deploy_path")
    )
    if runtime_changed and not commands_provided:
        apply_default_commands(project, prefer_defaults=True)
    else:
        apply_default_commands(project)

    db.commit()
    db.refresh(project)
    return build_project_read(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    db.execute(delete(OperationLog).where(OperationLog.project_id == project_id))
    db.execute(delete(ProjectLink).where(ProjectLink.project_id == project_id))
    db.execute(delete(Project).where(Project.id == project_id))
    db.commit()


@router.get("/projects/{project_id}/status", response_model=ProjectStatusRead)
def get_project_status(
    project_id: int,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectStatusRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    return ProjectStatusRead(
        project_id=project.id,
        http_status=project.http_status,
        http_checked_at=project.http_checked_at,
        http_source="cached",
        runtime_status=project.runtime_status,
        runtime_checked_at=project.runtime_checked_at,
        runtime_source="cached",
    )


@router.post("/projects/sync-status", response_model=list[ProjectStatusRead])
def sync_project_status(
    payload: StatusSyncRequest | None = None,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectStatusRead]:
    stmt = select(Project)
    if payload and payload.project_ids:
        stmt = stmt.where(Project.id.in_(payload.project_ids))
    projects = db.scalars(
        stmt.options(selectinload(Project.links), selectinload(Project.server))
    ).all()

    statuses: list[ProjectStatusRead] = []
    for project in projects:
        http_status, http_checked_at, http_source = check_http_status(project)
        runtime_status, runtime_checked_at, runtime_source = check_runtime_status(
            project, project.server
        )

        project.http_status = http_status
        project.http_checked_at = http_checked_at or datetime.now(timezone.utc)
        project.runtime_status = runtime_status
        project.runtime_checked_at = runtime_checked_at or datetime.now(timezone.utc)
        project.current_status = project.http_status
        project.last_checked_at = project.http_checked_at
        statuses.append(
            ProjectStatusRead(
                project_id=project.id,
                http_status=project.http_status,
                http_checked_at=project.http_checked_at,
                http_source=http_source,
                runtime_status=project.runtime_status,
                runtime_checked_at=project.runtime_checked_at,
                runtime_source=runtime_source,
            )
        )
    db.commit()
    return statuses


def get_action_command(project: Project, action: OperationAction) -> str | None:
    if action == OperationAction.START:
        return project.start_cmd
    if action == OperationAction.STOP:
        return project.stop_cmd
    return project.restart_cmd


def run_project_action(
    project: Project, user: User, action: OperationAction, db: Session
) -> OperationLog:
    command = get_action_command(project, action)
    if not command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{action.value} command is not configured.",
        )

    log = OperationLog(
        project_id=project.id,
        user_id=user.id,
        action=action,
        status=OperationStatus.PENDING,
        message="Queued for execution.",
    )
    db.add(log)
    db.flush()

    try:
        result = run_ssh_command(project.server, command)
        output = result.stdout or result.stderr
        log.message = (output[:400] if output else "Command executed.")
        log.status = (
            OperationStatus.SUCCEEDED if result.exit_code == 0 else OperationStatus.FAILED
        )
    except Exception as exc:
        log.status = OperationStatus.FAILED
        log.message = str(exc)

    db.commit()
    db.refresh(log)
    return log


@router.post("/projects/{project_id}/start")
def start_project(
    project_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    log = run_project_action(project, current_user, OperationAction.START, db)
    return {
        "status": log.status.value,
        "message": log.message or "",
        "execution_id": log.external_execution_id or "",
        "log_id": log.id,
    }


@router.post("/projects/{project_id}/stop")
def stop_project(
    project_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    log = run_project_action(project, current_user, OperationAction.STOP, db)
    return {
        "status": log.status.value,
        "message": log.message or "",
        "execution_id": log.external_execution_id or "",
        "log_id": log.id,
    }


@router.post("/projects/{project_id}/restart")
def restart_project(
    project_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    log = run_project_action(project, current_user, OperationAction.RESTART, db)
    return {
        "status": log.status.value,
        "message": log.message or "",
        "execution_id": log.external_execution_id or "",
        "log_id": log.id,
    }


@router.post(
    "/projects/{project_id}/links",
    response_model=ProjectLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project_link(
    project_id: int,
    payload: ProjectLinkCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectLinkRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    link = ProjectLink(project_id=project_id, **payload.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return ProjectLinkRead.model_validate(link)


@router.put("/project-links/{link_id}", response_model=ProjectLinkRead)
def update_project_link(
    link_id: int,
    payload: ProjectLinkUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProjectLinkRead:
    link = db.get(ProjectLink, link_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Link not found."
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(link, field, value)
    db.commit()
    db.refresh(link)
    return ProjectLinkRead.model_validate(link)


@router.delete("/project-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_link(
    link_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    link = db.get(ProjectLink, link_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Link not found."
        )
    db.delete(link)
    db.commit()
