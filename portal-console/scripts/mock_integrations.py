#!/usr/bin/env python3
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count

EXECUTION_IDS = count(1000)
EXECUTIONS: dict[str, dict[str, str | int]] = {}
MONITOR_STATUS = {
    "demo-online": "online",
    "demo-offline": "offline",
    "demo-degraded": "degraded",
}


class MockHandler(BaseHTTPRequestHandler):
    server_version = "PortalConsoleMock/1.0"

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        job_match = re.fullmatch(r"/api/\d+/job/([^/]+)/run", self.path)
        if not job_match:
            self._send_json({"detail": "Not found"}, status=404)
            return

        job_id = job_match.group(1)
        execution_id = str(next(EXECUTION_IDS))
        EXECUTIONS[execution_id] = {
            "job_id": job_id,
            "polls": 0,
        }
        self._send_json(
            {
                "id": execution_id,
                "message": f"Mock Rundeck accepted job {job_id}.",
            }
        )

    def do_GET(self) -> None:
        execution_match = re.fullmatch(r"/api/\d+/execution/([^/]+)", self.path)
        if execution_match:
            execution_id = execution_match.group(1)
            execution = EXECUTIONS.get(execution_id)
            if execution is None:
                self._send_json({"detail": "Execution not found"}, status=404)
                return

            execution["polls"] = int(execution["polls"]) + 1
            status_value = "running" if execution["polls"] == 1 else "succeeded"
            self._send_json(
                {
                    "id": execution_id,
                    "jobId": execution["job_id"],
                    "status": status_value,
                }
            )
            return

        heartbeat_match = re.fullmatch(r"/api/status-page/heartbeat/([^/]+)", self.path)
        if heartbeat_match:
            monitor_id = heartbeat_match.group(1)
            self._send_json({"status": MONITOR_STATUS.get(monitor_id, "unknown")})
            return

        if self.path == "/health":
            self._send_json({"status": "ok"})
            return

        self._send_json({"detail": "Not found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 9000), MockHandler)
    print("mock integrations listening on http://0.0.0.0:9000")
    server.serve_forever()


if __name__ == "__main__":
    main()
