from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SSHKey(TimestampMixin, Base):
    __tablename__ = "ssh_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(1024), unique=True)

    servers = relationship("Server", back_populates="ssh_key")
