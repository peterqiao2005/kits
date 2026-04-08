from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.models.enums import ProjectLinkType, ProjectStatus
from app.models.project import Project


def _select_access_url(project: Project) -> str | None:
    if not project.links:
        return None
    preferred = [ProjectLinkType.WEB, ProjectLinkType.ADMIN]
    for link_type in preferred:
        for link in project.links:
            if link.link_type == link_type and link.url:
                return link.url
    return project.links[0].url if project.links else None


def check_http_status(project: Project) -> tuple[ProjectStatus, datetime | None, str]:
    url = _select_access_url(project)
    if not url:
        return ProjectStatus.UNKNOWN, None, "no_link"

    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            response = client.head(url)
            if response.status_code >= 400:
                response = client.get(url)
    except Exception:
        return ProjectStatus.OFFLINE, datetime.now(timezone.utc), "url_probe_error"

    if response.status_code >= 500:
        status = ProjectStatus.DEGRADED
    else:
        status = ProjectStatus.ONLINE
    return status, datetime.now(timezone.utc), "url_probe"
