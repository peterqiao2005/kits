from datetime import datetime

from pydantic import BaseModel

from app.models.enums import OperationAction, OperationStatus


class OperationLogRead(BaseModel):
    id: int
    project_id: int
    project_name: str
    user_id: int | None = None
    username: str | None = None
    action: OperationAction
    status: OperationStatus
    message: str | None = None
    external_execution_id: str | None = None
    created_at: datetime
