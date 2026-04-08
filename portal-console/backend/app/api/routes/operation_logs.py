from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.enums import OperationAction, OperationStatus
from app.models.operation_log import OperationLog
from app.schemas.operation_log import OperationLogRead

router = APIRouter(prefix="/operation-logs", tags=["operation-logs"])


@router.get("", response_model=list[OperationLogRead])
def list_operation_logs(
    project_id: int | None = None,
    action: OperationAction | None = None,
    status_filter: OperationStatus | None = Query(default=None, alias="status"),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OperationLogRead]:
    stmt = (
        select(OperationLog)
        .options(joinedload(OperationLog.project), joinedload(OperationLog.user))
        .order_by(OperationLog.created_at.desc())
    )
    logs = db.scalars(stmt).all()
    result: list[OperationLogRead] = []
    for log in logs:
        if project_id and log.project_id != project_id:
            continue
        if action and log.action != action:
            continue
        if status_filter and log.status != status_filter:
            continue
        result.append(
            OperationLogRead(
                id=log.id,
                project_id=log.project_id,
                project_name=log.project.name,
                user_id=log.user_id,
                username=log.user.username if log.user else None,
                action=log.action,
                status=log.status,
                message=log.message,
                external_execution_id=log.external_execution_id,
                created_at=log.created_at,
            )
        )
    return result
