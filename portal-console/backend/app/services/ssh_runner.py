from __future__ import annotations

from dataclasses import dataclass

import paramiko

from app.models.enums import ServerAuthType
from app.models.server import Server
from app.services.secrets import decrypt_secret
from app.services.ssh_key_store import resolve_private_key_path


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
