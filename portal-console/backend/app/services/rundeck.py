import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.enums import OperationStatus

settings = get_settings()


class RundeckNotConfiguredError(RuntimeError):
    pass


class RundeckClient:
    def __init__(self) -> None:
        if not settings.rundeck_url or not settings.rundeck_token:
            raise RundeckNotConfiguredError("Rundeck integration is not configured.")
        self.base_url = settings.rundeck_url.rstrip("/")
        self.api_version = settings.rundeck_api_version
        self.headers = {
            "Accept": "application/json",
            "X-Rundeck-Auth-Token": settings.rundeck_token,
        }

    def trigger_job(self, job_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/{self.api_version}/job/{job_id}/run"
        with httpx.Client(timeout=15.0, headers=self.headers) as client:
            response = client.post(url, json={})
            response.raise_for_status()
            return response.json()

    def fetch_execution(self, execution_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/{self.api_version}/execution/{execution_id}"
        with httpx.Client(timeout=15.0, headers=self.headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

    def poll_execution(self, execution_id: str) -> tuple[OperationStatus, str]:
        last_message = "Execution accepted by Rundeck."
        for _ in range(settings.rundeck_poll_attempts):
            payload = self.fetch_execution(execution_id)
            status = (payload.get("status") or "").lower()
            if status == "running":
                last_message = "Execution is running."
                time.sleep(settings.rundeck_poll_interval_seconds)
                continue
            if status == "succeeded":
                return OperationStatus.SUCCEEDED, payload.get("status", "succeeded")
            if status:
                return OperationStatus.FAILED, payload.get("status", status)
        return OperationStatus.RUNNING, last_message
