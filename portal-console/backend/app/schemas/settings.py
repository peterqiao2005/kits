from pydantic import BaseModel


class IntegrationSummary(BaseModel):
    configured: bool
    base_url: str | None = None


class SettingsRead(BaseModel):
    rundeck: IntegrationSummary
    kuma: IntegrationSummary
