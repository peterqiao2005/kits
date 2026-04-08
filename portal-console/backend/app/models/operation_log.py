from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OperationAction, OperationStatus, enum_values


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[OperationAction] = mapped_column(
        Enum(OperationAction, values_callable=enum_values)
    )
    status: Mapped[OperationStatus] = mapped_column(
        Enum(OperationStatus, values_callable=enum_values),
        default=OperationStatus.PENDING,
    )
    message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    external_execution_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project = relationship("Project", back_populates="operation_logs")
    user = relationship("User", back_populates="operation_logs")
