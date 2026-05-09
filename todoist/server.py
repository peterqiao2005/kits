#!/usr/bin/env python3
"""Local reminder server for the completion-repeat todo app."""

from __future__ import annotations

import base64
import email.message
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, time as dt_time
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "state.json"
CONFIG_FILE = ROOT / "config"
PORT = 8765
SESSION_COOKIE_NAME = "todoist_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
USED_JTIS: dict[str, int] = {}
DEFAULT_SETTINGS = {
    "browserEnabled": False,
    "serverEnabled": False,
    "wecomWebhook": "",
    "feishuWebhook": "",
    "feishuSecret": "",
    "genericWebhook": "",
    "smtpHost": "",
    "smtpPort": "",
    "smtpUser": "",
    "smtpPassword": "",
    "mailFrom": "",
    "mailTo": "",
}


def read_config() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {}
    values: dict[str, str] = {}
    for line in CONFIG_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


CONFIG = read_config()
PORTAL_SSO_SECRET = os.environ.get("PORTAL_SSO_SECRET") or CONFIG.get("PORTAL_SSO_SECRET") or "fallback-secret"
SESSION_SECRET = os.environ.get("TODOIST_SESSION_SECRET") or CONFIG.get("TODOIST_SESSION_SECRET") or PORTAL_SSO_SECRET


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def load_state() -> dict[str, Any]:
    ensure_data_dir()
    if not STATE_FILE.exists():
        return {"tasks": [], "settings": {}, "sent": []}
    try:
        return normalize_state(json.loads(STATE_FILE.read_text(encoding="utf-8-sig")))
    except json.JSONDecodeError:
        return {"tasks": [], "settings": {}, "sent": []}


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    state.setdefault("tasks", [])
    state["settings"] = normalize_settings(state.get("settings"))
    state.setdefault("sent", [])
    state.setdefault("users", {})
    for user_key, scope in list(state["users"].items()):
        if not isinstance(scope, dict):
            state["users"][user_key] = {"tasks": [], "settings": DEFAULT_SETTINGS.copy(), "sent": []}
            continue
        scope.setdefault("tasks", [])
        scope["settings"] = normalize_settings(scope.get("settings"))
        scope.setdefault("sent", [])
    return state


def normalize_settings(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        settings = {}
    return {**DEFAULT_SETTINGS, **settings}


def save_state(state: dict[str, Any]) -> None:
    ensure_data_dir()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def user_state(state: dict[str, Any], user_key: str) -> dict[str, Any]:
    if user_key == "global":
        return state
    users = state.setdefault("users", {})
    return users.setdefault(user_key, {"tasks": [], "settings": DEFAULT_SETTINGS.copy(), "sent": []})


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def sign_text(value: str, secret: str = SESSION_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_portal_token(token: str) -> tuple[dict[str, Any] | None, str | None]:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        return None, "Invalid token format"

    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(PORTAL_SSO_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = base64url_decode(parts[2])
    except (ValueError, TypeError):
        return None, "Invalid token signature"
    if len(actual) != len(expected) or not hmac.compare_digest(actual, expected):
        return None, "Invalid token signature"

    try:
        payload = json.loads(base64url_decode(parts[1]).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None, "Invalid token payload"

    now = int(time.time())
    if payload.get("iss") != "portal":
        return None, "Invalid issuer"
    if int(payload.get("exp") or 0) < now:
        return None, "Token expired"

    cleanup_used_jtis(now)
    jti = str(payload.get("jti") or "").strip()
    if not jti:
        return None, "Missing token id"
    if jti in USED_JTIS:
        return None, "Token already used"
    USED_JTIS[jti] = int(payload.get("exp") or now + 300)
    return payload, None


def cleanup_used_jtis(now: int) -> None:
    for jti, expires_at in list(USED_JTIS.items()):
        if expires_at < now:
            del USED_JTIS[jti]


def create_session_cookie(payload: dict[str, Any]) -> str:
    now = int(time.time())
    session_payload = {
        "sub": str(payload.get("sub") or "").strip(),
        "email": str(payload.get("email") or "").strip(),
        "loginMethod": "portal",
        "iat": now,
        "exp": now + SESSION_MAX_AGE_SECONDS,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = base64url_encode(json.dumps(session_payload, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{sign_text(encoded)}"


def read_cookie(header: str, name: str) -> str:
    jar = cookies.SimpleCookie()
    try:
        jar.load(header or "")
    except cookies.CookieError:
        return ""
    morsel = jar.get(name)
    return morsel.value if morsel else ""


def read_session(handler: SimpleHTTPRequestHandler) -> dict[str, Any] | None:
    raw = read_cookie(handler.headers.get("Cookie", ""), SESSION_COOKIE_NAME)
    if "." not in raw:
        return None
    encoded, signature = raw.rsplit(".", 1)
    if not hmac.compare_digest(signature, sign_text(encoded)):
        return None
    try:
        payload = json.loads(base64url_decode(encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    if not str(payload.get("sub") or "").strip():
        return None
    return payload


def request_user_key(handler: SimpleHTTPRequestHandler) -> str:
    session = read_session(handler)
    return f"portal:{session['sub']}" if session else "global"


def request_user_context(handler: SimpleHTTPRequestHandler) -> tuple[str, dict[str, Any] | None]:
    session = read_session(handler)
    return (f"portal:{session['sub']}", session) if session else ("global", None)


def json_response(handler: SimpleHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def post_json(url: str, payload: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
        return {"status": response.status, "body": text}


def task_due_at(task: dict[str, Any]) -> datetime | None:
    due_date = task.get("dueDate")
    if not due_date:
        return None
    try:
        date_part = datetime.strptime(due_date, "%Y-%m-%d").date()
        due_time = task.get("dueTime") or "09:00"
        hour, minute = [int(part) for part in due_time.split(":", 1)]
        return datetime.combine(date_part, dt_time(hour=hour, minute=minute))
    except (TypeError, ValueError):
        return None


def task_key(task: dict[str, Any]) -> str:
    return f"{task.get('id')}:{task.get('dueDate', '')}:{task.get('dueTime', '')}"


def message_for_task(task: dict[str, Any]) -> str:
    due = " ".join(part for part in [task.get("dueDate"), task.get("dueTime")] if part)
    return f"待办提醒：{task.get('title', '未命名任务')}\n到期时间：{due or '未设置'}"


def normalize_wecom_url(value: str) -> str:
    if value.startswith("http"):
        return value
    return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={value}"


def send_wecom(settings: dict[str, Any], text: str) -> list[str]:
    url = (settings.get("wecomWebhook") or "").strip()
    if not url:
        return []
    post_json(normalize_wecom_url(url), {"msgtype": "text", "text": {"content": text}})
    return ["wecom"]


def feishu_payload(settings: dict[str, Any], text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
    secret = (settings.get("feishuSecret") or "").strip()
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        sign = base64.b64encode(hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    return payload


def send_feishu(settings: dict[str, Any], text: str) -> list[str]:
    url = (settings.get("feishuWebhook") or "").strip()
    if not url:
        return []
    post_json(url, feishu_payload(settings, text))
    return ["feishu"]


def send_generic_webhook(settings: dict[str, Any], text: str, task: dict[str, Any] | None = None) -> list[str]:
    url = (settings.get("genericWebhook") or "").strip()
    if not url:
        return []
    post_json(url, {"text": text, "task": task or {}})
    return ["webhook"]


def send_email(settings: dict[str, Any], text: str) -> list[str]:
    host = (settings.get("smtpHost") or "").strip()
    mail_to = (settings.get("mailTo") or "").strip()
    if not host or not mail_to:
        return []

    port = int(settings.get("smtpPort") or 465)
    username = (settings.get("smtpUser") or "").strip()
    password = settings.get("smtpPassword") or ""
    mail_from = (settings.get("mailFrom") or username or mail_to).strip()

    message = email.message.EmailMessage()
    message["Subject"] = "待办提醒"
    message["From"] = mail_from
    message["To"] = mail_to
    message.set_content(text)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    return ["email"]


def send_all_with_errors(
    settings: dict[str, Any], text: str, task: dict[str, Any] | None = None
) -> tuple[list[str], list[str]]:
    sent: list[str] = []
    errors: list[str] = []
    for sender in (send_wecom, send_feishu, send_email):
        try:
            sent.extend(sender(settings, text))
        except (OSError, smtplib.SMTPException, urllib.error.URLError) as exc:
            errors.append(f"{sender.__name__}: {exc}")
    try:
        sent.extend(send_generic_webhook(settings, text, task))
    except (OSError, urllib.error.URLError) as exc:
        errors.append(f"send_generic_webhook: {exc}")
    if errors:
        print("notification errors:", "; ".join(errors))
    return sent, errors


def send_all(settings: dict[str, Any], text: str, task: dict[str, Any] | None = None) -> list[str]:
    sent, _errors = send_all_with_errors(settings, text, task)
    return sent


def scheduler() -> None:
    while True:
        state = load_state()
        changed = False
        for user_key, scope in iter_state_scopes(state):
            settings = normalize_settings(scope.get("settings"))
            if not settings.get("serverEnabled"):
                continue
            sent_keys = set(scope.get("sent") or [])
            now = datetime.now()
            for task in scope.get("tasks") or []:
                if task.get("completed"):
                    continue
                due_at = task_due_at(task)
                key = task_key(task)
                if due_at and due_at <= now and key not in sent_keys:
                    channels = send_all(settings, message_for_task(task), task)
                    if channels:
                        sent_keys.add(key)
                        changed = True
                        print(f"sent {','.join(channels)} reminder for {user_key}:{task.get('title')}")
            scope["sent"] = list(sent_keys)[-1000:]
        if changed:
            save_state(state)
        time.sleep(30)


def iter_state_scopes(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    scopes = [("global", state)]
    for user_key, scope in (state.get("users") or {}).items():
        if isinstance(scope, dict):
            scopes.append((user_key, scope))
    return scopes


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/sso/portal":
            params = urllib.parse.parse_qs(parsed.query)
            token = (params.get("token") or [""])[0]
            payload, error = verify_portal_token(token)
            if error:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(error.encode("utf-8"))
                return
            cookie_value = create_session_cookie(payload or {})
            self.send_response(302)
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}={cookie_value}; Path=/; Max-Age={SESSION_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax",
            )
            self.send_header("Location", "/")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            json_response(self, {"ok": False, "error": "invalid json"}, 400)
            return

        if self.path == "/api/ping":
            json_response(self, {"ok": True})
            return

        if self.path == "/api/session":
            session = read_session(self)
            if not session:
                json_response(self, {"authenticated": False})
                return
            json_response(
                self,
                {
                    "authenticated": True,
                    "userId": session.get("sub"),
                    "email": session.get("email") or "",
                    "loginMethod": "portal",
                    "dataUserId": f"portal:{session.get('sub')}",
                },
            )
            return

        if self.path == "/api/load":
            state = load_state()
            user_key, session = request_user_context(self)
            scope = user_state(state, user_key)
            json_response(
                self,
                {
                    "ok": True,
                    "tasks": scope.get("tasks") or [],
                    "settings": normalize_settings(scope.get("settings")),
                    "session": session,
                    "dataUserId": user_key,
                },
            )
            return

        if self.path == "/api/sync":
            state = load_state()
            user_key, _session = request_user_context(self)
            scope = user_state(state, user_key)
            scope["tasks"] = payload.get("tasks") or []
            scope["settings"] = normalize_settings(payload.get("settings"))
            save_state(state)
            json_response(self, {"ok": True, "dataUserId": user_key})
            return

        if self.path == "/api/test-notification":
            state = load_state()
            user_key, _session = request_user_context(self)
            scope = user_state(state, user_key)
            settings = normalize_settings(payload.get("settings") or scope.get("settings"))
            channels, errors = send_all_with_errors(settings, "待办测试提醒：通知通道已连接。", None)
            json_response(self, {"ok": not errors, "channels": channels, "errors": errors, "dataUserId": user_key})
            return

        if self.path == "/api/logout":
            self.send_response(204)
            self.send_header("Set-Cookie", f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            self.end_headers()
            return

        json_response(self, {"ok": False, "error": "not found"}, 404)


def main() -> None:
    threading.Thread(target=scheduler, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Todo reminder server: http://127.0.0.1:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
