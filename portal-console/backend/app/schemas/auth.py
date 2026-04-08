from pydantic import BaseModel

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    username: str
    role: UserRole

    model_config = {"from_attributes": True}
