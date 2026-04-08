from datetime import datetime

from pydantic import BaseModel


class SSHKeySummaryRead(BaseModel):
    id: int
    name: str
    original_filename: str

    model_config = {"from_attributes": True}


class SSHKeyRead(SSHKeySummaryRead):
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    server_count: int = 0

    model_config = {"from_attributes": True}
