from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.config import get_settings
from app.schemas.settings import IntegrationSummary, SettingsRead

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/integrations", response_model=SettingsRead)
def get_integrations(_: object = Depends(require_admin)) -> SettingsRead:
    settings = get_settings()
    return SettingsRead(
        rundeck=IntegrationSummary(
            configured=bool(settings.rundeck_url and settings.rundeck_token),
            base_url=settings.rundeck_url,
        ),
        kuma=IntegrationSummary(
            configured=bool(settings.kuma_url),
            base_url=settings.kuma_url,
        ),
    )
