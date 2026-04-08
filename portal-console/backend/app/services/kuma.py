from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.enums import ProjectStatus

settings = get_settings()


class KumaClient:
    """
    Uptime Kuma does not expose a stable public management API for monitor status.
    This client is intentionally conservative: if no compatible endpoint is available,
    the portal keeps the project status as `unknown`.
    """

    def __init__(self) -> None:
        self.base_url = settings.kuma_url.rstrip("/") if settings.kuma_url else None

    def fetch_monitor_status(self, monitor_id: str | None) -> tuple[ProjectStatus, datetime | None, str]:
        if not self.base_url or not monitor_id:
            return ProjectStatus.UNKNOWN, None, "unconfigured"

        url = f"{self.base_url}/api/status-page/heartbeat/{monitor_id}"
        headers = {"Accept": "application/json"}
        if settings.kuma_token:
            headers["Authorization"] = f"Bearer {settings.kuma_token}"

        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return ProjectStatus.UNKNOWN, None, "kuma_unreachable"

        status_value = str(payload.get("status", "")).lower()
        if status_value in {ProjectStatus.ONLINE.value, ProjectStatus.OFFLINE.value, ProjectStatus.DEGRADED.value}:
            status = ProjectStatus(status_value)
        else:
            status = ProjectStatus.UNKNOWN
        return status, datetime.now(timezone.utc), "uptime_kuma"
