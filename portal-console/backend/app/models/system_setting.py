from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text(), nullable=True)
