from __future__ import annotations

from datetime import datetime, timezone

from app.models.enums import RuntimeStatus, RuntimeType
from app.models.project import Project
from app.models.server import Server
from app.services.ssh_runner import run_ssh_command

def _parse_tokens(output: str, active_tokens: tuple[str, ...], stop_tokens: tuple[str, ...]) -> RuntimeStatus:
    lowered = output.lower()
    if any(token in lowered for token in active_tokens):
        return RuntimeStatus.ACTIVE
    if any(token in lowered for token in stop_tokens):
        return RuntimeStatus.STOPPED
    return RuntimeStatus.UNKNOWN


def check_runtime_status(project: Project, server: Server) -> tuple[RuntimeStatus, datetime | None, str]:
    if project.runtime_type in {RuntimeType.CMD, RuntimeType.CUSTOM}:
        return RuntimeStatus.UNKNOWN, None, "cmd_ignored"

    if not server.host:
        return RuntimeStatus.UNKNOWN, None, "missing_host"

    service_name = project.runtime_service_name or project.name
    deploy_path = project.deploy_path or "."
    target = project.deploy_path or service_name

    command = ""
    parser = None

    if project.runtime_type == RuntimeType.SYSTEMD_SERVICE:
        command = f"systemctl is-active {service_name}"
        parser = lambda out: _parse_tokens(out, ("active",), ("inactive", "failed"))
    elif project.runtime_type == RuntimeType.SUPERVISORD:
        command = f"supervisorctl status {service_name}"
        parser = lambda out: _parse_tokens(out, ("running",), ("stopped", "fatal", "exited", "backoff"))
    elif project.runtime_type == RuntimeType.PM2_PROCESS:
        command = f"pm2 describe {service_name}"
        parser = lambda out: _parse_tokens(out, ("online",), ("stopped", "errored", "stopping"))
    elif project.runtime_type == RuntimeType.DOCKER_CONTAINER:
        command = f"docker inspect -f '{{{{.State.Running}}}}' {service_name}"
        parser = lambda out: RuntimeStatus.ACTIVE if out.strip().lower() == "true" else RuntimeStatus.STOPPED
    elif project.runtime_type == RuntimeType.DOCKER_COMPOSE:
        command = f"cd {deploy_path} && docker compose ps --status running --services"

        def parse_compose(out: str) -> RuntimeStatus:
            services = [line.strip() for line in out.splitlines() if line.strip()]
            if not services:
                return RuntimeStatus.STOPPED
            if project.runtime_service_name:
                return RuntimeStatus.ACTIVE if project.runtime_service_name in services else RuntimeStatus.STOPPED
            return RuntimeStatus.ACTIVE

        parser = parse_compose
    elif project.runtime_type == RuntimeType.PYTHON_SCRIPT:
        command = f"pgrep -f \"{target}\""
        parser = lambda out: RuntimeStatus.ACTIVE if out.strip() else RuntimeStatus.STOPPED
    elif project.runtime_type == RuntimeType.SHELL_SCRIPT:
        command = f"pgrep -f \"{target}\""
        parser = lambda out: RuntimeStatus.ACTIVE if out.strip() else RuntimeStatus.STOPPED
    else:
        return RuntimeStatus.UNKNOWN, None, "unsupported_type"

    result = run_ssh_command(server, command)
    if project.runtime_type in {RuntimeType.PYTHON_SCRIPT, RuntimeType.SHELL_SCRIPT}:
        if result.stderr.startswith("missing_") or result.stderr.startswith("ssh_"):
            return RuntimeStatus.UNKNOWN, datetime.now(timezone.utc), result.stderr
        status = RuntimeStatus.ACTIVE if result.exit_code == 0 else RuntimeStatus.STOPPED
        return status, datetime.now(timezone.utc), "ssh_runtime"

    if result.stderr.startswith("missing_") or result.stderr.startswith("ssh_"):
        return RuntimeStatus.UNKNOWN, datetime.now(timezone.utc), result.stderr

    status = parser(result.stdout or result.stderr)
    return status, datetime.now(timezone.utc), "ssh_runtime"
