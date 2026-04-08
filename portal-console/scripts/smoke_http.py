import os
import uuid
from pathlib import Path

import httpx

BASE_URL = os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.environ.get("PORTAL_USERNAME", "admin")
PASSWORD = os.environ.get("PORTAL_PASSWORD", "admin123")


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    key_id = None
    server_id = None
    service_id = None
    uploaded_key_path = None

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        key_name = f"smoke-key-{suffix}"
        server_name = f"smoke-server-{suffix}"
        service_name = f"smoke-service-{suffix}"

        try:
            uploaded_key_path = Path(f"/tmp/{key_name}.pem")
            uploaded_key_path.write_text("invalid-test-key", encoding="utf-8")

            create_key = client.post(
                "/api/ssh-keys",
                data={
                    "name": key_name,
                    "description": "temporary smoke test key",
                },
                files={
                    "key_file": (
                        uploaded_key_path.name,
                        uploaded_key_path.read_bytes(),
                        "application/octet-stream",
                    )
                },
            )
            create_key.raise_for_status()
            key = create_key.json()
            key_id = key["id"]
            stored_path = Path("/root/portal-console/backend") / key["file_path"]
            assert stored_path.exists(), stored_path
            assert stored_path.suffix == ".enc", stored_path
            assert b"invalid-test-key" not in stored_path.read_bytes(), stored_path

            create_server = client.post(
                "/api/servers",
                json={
                    "name": server_name,
                    "host": "127.0.0.1",
                    "ssh_port": 22,
                    "ssh_user": "root",
                    "description": "temporary smoke test server",
                    "ssh_key_id": key_id,
                },
            )
            create_server.raise_for_status()
            server = create_server.json()
            server_id = server["id"]

            create_service = client.post(
                "/api/services",
                json={
                    "server_id": server_id,
                    "name": service_name,
                    "description": "temporary smoke test service",
                    "service_type": "web",
                    "internal_url": "http://127.0.0.1:65535",
                    "external_url": "http://127.0.0.1:65535",
                    "primary_url": "external",
                    "force_external": False,
                    "start_cmd": "echo start",
                    "stop_cmd": "echo stop",
                    "restart_cmd": "echo restart",
                },
            )
            create_service.raise_for_status()
            service = create_service.json()
            service_id = service["id"]

            sync_status = client.post(
                "/api/services/sync-status",
                json={"service_ids": [service_id]},
            )
            sync_status.raise_for_status()
            statuses = sync_status.json()

            restart = client.post(f"/api/services/{service_id}/restart")
            restart.raise_for_status()
            restart_payload = restart.json()

            logs = client.get(
                "/api/operation-logs",
                params={"service_id": service_id},
            )
            logs.raise_for_status()
            log_rows = logs.json()

            print(
                {
                    "base_url": BASE_URL,
                    "login_user": USERNAME,
                    "stored_key_path": key["file_path"],
                    "service_status": statuses[0]["status"],
                    "restart_status": restart_payload["status"],
                    "restart_message": restart_payload["message"],
                    "log_count": len(log_rows),
                }
            )
        finally:
            if uploaded_key_path is not None:
                uploaded_key_path.unlink(missing_ok=True)
            if service_id is not None:
                client.delete(f"/api/services/{service_id}")
            if server_id is not None:
                client.delete(f"/api/servers/{server_id}")
            if key_id is not None:
                client.delete(f"/api/ssh-keys/{key_id}")
            if "stored_path" in locals():
                assert not stored_path.exists(), stored_path


if __name__ == "__main__":
    main()
