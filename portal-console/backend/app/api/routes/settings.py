from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
import secrets

from app.api.deps import get_db, require_admin
from app.core.config import get_settings
from app.models.system_setting import SystemSetting
from app.schemas.settings import IntegrationSummary, SettingsRead, AgentSecretRead

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


@router.get("/agent-secret", response_model=AgentSecretRead)
def get_agent_secret(db: Session = Depends(get_db), _: object = Depends(require_admin)) -> AgentSecretRead:
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "windows_agent_secret"))
    if setting is None:
        new_secret = secrets.token_hex(16)
        setting = SystemSetting(key="windows_agent_secret", value=new_secret)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return AgentSecretRead(secret=setting.value)


@router.post("/agent-secret/generate", response_model=AgentSecretRead)
def generate_agent_secret(db: Session = Depends(get_db), _: object = Depends(require_admin)) -> AgentSecretRead:
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "windows_agent_secret"))
    new_secret = secrets.token_hex(16)
    if setting is None:
        setting = SystemSetting(key="windows_agent_secret", value=new_secret)
        db.add(setting)
    else:
        setting.value = new_secret
    db.commit()
    return AgentSecretRead(secret=new_secret)
