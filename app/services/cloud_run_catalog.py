from __future__ import annotations

import os
import re
from typing import Any

import httpx

from app.config import Settings

_RUN_API = "https://run.googleapis.com/v2"


def _display_name(service_id: str) -> str:
    return service_id.replace("-", " ").title()


def _parse_region(resource_name: str) -> str:
    match = re.search(r"/locations/([^/]+)/services/", resource_name)
    return match.group(1) if match else "—"


def list_cloud_run_services(settings: Settings) -> dict[str, Any]:
    """List Cloud Run services in the configured GCP project."""
    project_id = settings.google_cloud_project
    if not project_id:
        return {
            "project_id": None,
            "services": [],
            "error": "GOOGLE_CLOUD_PROJECT is not set",
            "current_service": os.environ.get("K_SERVICE"),
        }

    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        token = credentials.token
    except Exception as exc:
        return {
            "project_id": project_id,
            "services": [],
            "error": f"Could not obtain GCP credentials: {exc}",
            "current_service": os.environ.get("K_SERVICE"),
        }

    url = f"{_RUN_API}/projects/{project_id}/locations/-/services"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"pageSize": 100},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "project_id": project_id,
            "services": [],
            "error": f"Cloud Run API error: {exc.response.status_code} {exc.response.text[:200]}",
            "current_service": os.environ.get("K_SERVICE"),
        }
    except Exception as exc:
        return {
            "project_id": project_id,
            "services": [],
            "error": str(exc),
            "current_service": os.environ.get("K_SERVICE"),
        }

    services: list[dict[str, Any]] = []
    for item in payload.get("services", []):
        name = item.get("name", "")
        service_id = name.rsplit("/", 1)[-1] if name else "unknown"
        services.append(
            {
                "id": service_id,
                "name": _display_name(service_id),
                "region": _parse_region(name),
                "url": item.get("uri") or "",
                "is_current": service_id == os.environ.get("K_SERVICE"),
            }
        )

    services.sort(key=lambda s: (s["name"].lower(), s["region"]))

    return {
        "project_id": project_id,
        "services": services,
        "error": None,
        "current_service": os.environ.get("K_SERVICE"),
    }
