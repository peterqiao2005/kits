from datetime import datetime

from app.models.enums import EnvironmentType, ServerAuthType
from app.schemas.ssh_key import SSHKeySummaryRead
from pydantic import BaseModel, Field


class ServerBase(BaseModel):
    name: str
    host: str
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_auth_type: ServerAuthType = ServerAuthType.SSH_KEY
    ssh_key_id: int | None = None
    env_type: EnvironmentType
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class ServerCreate(ServerBase):
    ssh_password: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_auth_type: ServerAuthType | None = None
    ssh_key_id: int | None = None
    ssh_password: str | None = None
    env_type: EnvironmentType | None = None
    description: str | None = None
    tags: list[str] | None = None


class ServerRead(ServerBase):
    id: int
    has_ssh_password: bool = False
    ssh_key: SSHKeySummaryRead | None = None
    created_at: datetime
    updated_at: datetime
    project_count: int = 0

    model_config = {"from_attributes": True}
