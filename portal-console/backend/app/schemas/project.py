from datetime import datetime

from app.models.enums import ProjectStatus, RuntimeStatus, RuntimeType
from app.schemas.project_link import ProjectLinkCreate, ProjectLinkRead
from app.schemas.server import ServerRead
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    repo_url: str | None = None
    server_id: int
    deploy_path: str | None = None
    runtime_type: RuntimeType
    start_note: str | None = None
    stop_note: str | None = None
    access_note: str | None = None
    runtime_service_name: str | None = None
    start_cmd: str | None = None
    stop_cmd: str | None = None
    restart_cmd: str | None = None
    rundeck_job_start_id: str | None = None
    rundeck_job_stop_id: str | None = None
    rundeck_job_restart_id: str | None = None
    kuma_monitor_id: str | None = None
    is_favorite: bool = False


class ProjectCreate(ProjectBase):
    links: list[ProjectLinkCreate] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    repo_url: str | None = None
    server_id: int | None = None
    deploy_path: str | None = None
    runtime_type: RuntimeType | None = None
    start_note: str | None = None
    stop_note: str | None = None
    access_note: str | None = None
    runtime_service_name: str | None = None
    start_cmd: str | None = None
    stop_cmd: str | None = None
    restart_cmd: str | None = None
    rundeck_job_start_id: str | None = None
    rundeck_job_stop_id: str | None = None
    rundeck_job_restart_id: str | None = None
    kuma_monitor_id: str | None = None
    is_favorite: bool | None = None


class ProjectRead(ProjectBase):
    id: int
    current_status: ProjectStatus
    last_checked_at: datetime | None = None
    http_status: ProjectStatus
    http_checked_at: datetime | None = None
    runtime_status: RuntimeStatus
    runtime_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    server: ServerRead
    links: list[ProjectLinkRead] = Field(default_factory=list)
    can_start: bool = False
    can_stop: bool = False
    can_restart: bool = False

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    tags: list[str]
    runtime_type: RuntimeType
    repo_url: str | None = None
    is_favorite: bool
    current_status: ProjectStatus
    last_checked_at: datetime | None = None
    http_status: ProjectStatus
    http_checked_at: datetime | None = None
    runtime_status: RuntimeStatus
    runtime_checked_at: datetime | None = None
    server: ServerRead
    links: list[ProjectLinkRead]
    can_start: bool
    can_stop: bool
    can_restart: bool


class ProjectStatusRead(BaseModel):
    project_id: int
    http_status: ProjectStatus
    http_checked_at: datetime | None = None
    http_source: str
    runtime_status: RuntimeStatus
    runtime_checked_at: datetime | None = None
    runtime_source: str


class StatusSyncRequest(BaseModel):
    project_ids: list[int] | None = None
