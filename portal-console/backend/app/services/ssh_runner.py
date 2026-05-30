from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import httpx
from jose import jwt
import paramiko
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.enums import ServerAuthType, OSType
from app.models.server import Server
from app.models.system_setting import SystemSetting
from app.services.secrets import decrypt_secret
from app.services.ssh_key_store import resolve_private_key_path

settings = get_settings()

def get_agent_secret() -> str:
    with SessionLocal() as db:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "windows_agent_secret"))
        if setting is None:
            return settings.SECRET_KEY
        return setting.value

def generate_agent_token() -> str:
    payload = {
        "iss": "portal-console",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=2)).timestamp()),
    }
    secret = get_agent_secret()
    return jwt.encode(payload, secret, algorithm="HS256")


@dataclass
class SshResult:
    exit_code: int
    stdout: str
    stderr: str


def run_ssh_command(
    server: Server,
    command: str,
    timeout_seconds: float = 15.0,
) -> SshResult:
    if server.os_type == OSType.WINDOWS:
        port = server.ssh_port if server.ssh_port != 22 else 8008
        try:
            token = generate_agent_token()
            url = f"http://{server.host}:{port}/execute"
            
            run_as_admin = False
            admin_triggers = ["start-service", "stop-service", "restart-service", "net start", "net stop", "sc config"]
            lowered_cmd = command.lower()
            if any(trigger in lowered_cmd for trigger in admin_triggers):
                run_as_admin = True
                
            shell = "powershell"
            if "cmd /c" in command or "cmd.exe /c" in command:
                shell = "cmd"
                
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "command": command,
                "shell": shell,
                "run_as_admin": run_as_admin
            }
            
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
                
            if response.status_code == 200:
                res_data = response.json()
                return SshResult(
                    exit_code=res_data.get("exit_code", 0),
                    stdout=res_data.get("stdout", ""),
                    stderr=res_data.get("stderr", "")
                )
            else:
                return SshResult(
                    exit_code=1,
                    stdout="",
                    stderr=f"Windows Agent returned HTTP {response.status_code}: {response.text}"
                )
        except Exception as e:
            return SshResult(
                exit_code=255,
                stdout="",
                stderr=f"Failed to connect to Windows Agent at {server.host}:{port}: {e}"
            )

    if not server.host:
        return SshResult(exit_code=1, stdout="", stderr="missing_host")
    if not server.ssh_username:
        return SshResult(exit_code=1, stdout="", stderr="missing_ssh_username")

    connect_kwargs = {
        "hostname": server.host,
        "port": server.ssh_port or 22,
        "username": server.ssh_username,
        "timeout": 8,
        "banner_timeout": 8,
        "auth_timeout": 8,
        "look_for_keys": False,
        "allow_agent": False,
    }
    try:
        if server.ssh_auth_type == ServerAuthType.PASSWORD:
            if not server.ssh_password_encrypted:
                return SshResult(exit_code=1, stdout="", stderr="missing_ssh_password")
            connect_kwargs["password"] = decrypt_secret(server.ssh_password_encrypted)
        else:
            if server.ssh_key is None:
                return SshResult(exit_code=1, stdout="", stderr="missing_ssh_key")
            connect_kwargs["key_filename"] = resolve_private_key_path(
                server.ssh_key.stored_filename
            )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**connect_kwargs)
        _, stdout, stderr = client.exec_command(command, timeout=timeout_seconds)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        client.close()
        return SshResult(exit_code=exit_code, stdout=output, stderr=error)
    except paramiko.AuthenticationException:
        return SshResult(exit_code=255, stdout="", stderr="ssh_auth_failed")
    except paramiko.SSHException as exc:
        return SshResult(exit_code=255, stdout="", stderr=f"ssh_error:{exc}")
    except FileNotFoundError:
        return SshResult(
            exit_code=255,
            stdout="",
            stderr="ssh_key_file_missing: Re-upload the selected SSH key.",
        )
    except TimeoutError:
        return SshResult(exit_code=124, stdout="", stderr="ssh_timeout")
    except Exception as exc:
        return SshResult(exit_code=255, stdout="", stderr=str(exc))
