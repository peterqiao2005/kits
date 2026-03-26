#!/usr/bin/env python3
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data.json"

DEFAULT_DATA = [
    {
        "id": 1,
        "name": "OpenAI",
        "externalLink": "https://www.openai.com",
        "internalLink": "",
        "primary": "external",
        "forceExternal": False,
        "remark": "示例：外部链接",
    },
    {
        "id": 2,
        "name": "内部示例",
        "externalLink": "",
        "internalLink": "./index.html",
        "primary": "internal",
        "forceExternal": False,
        "remark": "示例：内部链接",
    },
]


def load_data():
    if DATA_PATH.exists():
        try:
            raw = DATA_PATH.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    save_data(DEFAULT_DATA)
    return list(DEFAULT_DATA)


def save_data(data):
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/data"):
            data = load_data()
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/data"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError("data must be list")
        except Exception:
            self.send_error(400, "Invalid JSON")
            return
        save_data(data)
        self.send_response(204)
        self.end_headers()


def run(port=8000):
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Serving on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
