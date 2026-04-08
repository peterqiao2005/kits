from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProjectStatus, RuntimeStatus, RuntimeType, enum_values
from app.models.mixins import TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    deploy_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_type: Mapped[RuntimeType] = mapped_column(
        Enum(RuntimeType, values_callable=enum_values)
    )
    start_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    stop_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    access_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    runtime_service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_cmd: Mapped[str | None] = mapped_column(Text(), nullable=True)
    stop_cmd: Mapped[str | None] = mapped_column(Text(), nullable=True)
    restart_cmd: Mapped[str | None] = mapped_column(Text(), nullable=True)
    rundeck_job_start_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rundeck_job_stop_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rundeck_job_restart_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kuma_monitor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    current_status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, values_callable=enum_values),
        default=ProjectStatus.UNKNOWN,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, values_callable=enum_values),
        default=ProjectStatus.UNKNOWN,
    )
    http_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_status: Mapped[RuntimeStatus] = mapped_column(
        Enum(RuntimeStatus, values_callable=enum_values),
        default=RuntimeStatus.UNKNOWN,
    )
    runtime_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))

    server = relationship("Server", back_populates="projects")
    links = relationship("ProjectLink", back_populates="project", cascade="all, delete-orphan")
    operation_logs = relationship(
        "OperationLog",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
