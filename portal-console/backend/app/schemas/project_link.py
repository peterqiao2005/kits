from pydantic import BaseModel, HttpUrl

from app.models.enums import ProjectLinkType


class ProjectLinkBase(BaseModel):
    link_type: ProjectLinkType
    title: str
    url: HttpUrl | str
    sort_order: int = 0


class ProjectLinkCreate(ProjectLinkBase):
    pass


class ProjectLinkUpdate(BaseModel):
    link_type: ProjectLinkType | None = None
    title: str | None = None
    url: HttpUrl | str | None = None
    sort_order: int | None = None


class ProjectLinkRead(ProjectLinkBase):
    id: int
    project_id: int

    model_config = {"from_attributes": True}
