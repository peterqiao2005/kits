from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProjectLinkType, enum_values


class ProjectLink(Base):
    __tablename__ = "project_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    link_type: Mapped[ProjectLinkType] = mapped_column(
        Enum(ProjectLinkType, values_callable=enum_values)
    )
    title: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(1024))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project = relationship("Project", back_populates="links")
