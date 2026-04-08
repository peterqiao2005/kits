from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EnvironmentType, ServerAuthType, enum_values
from app.models.mixins import TimestampMixin


class Server(TimestampMixin, Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    host: Mapped[str] = mapped_column(String(255))
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ssh_auth_type: Mapped[ServerAuthType] = mapped_column(
        Enum(ServerAuthType, values_callable=enum_values),
        default=ServerAuthType.SSH_KEY,
    )
    ssh_password_encrypted: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ssh_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("ssh_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    env_type: Mapped[EnvironmentType] = mapped_column(
        Enum(EnvironmentType, values_callable=enum_values)
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    ssh_key = relationship("SSHKey", back_populates="servers")
    projects = relationship(
        "Project",
        back_populates="server",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
