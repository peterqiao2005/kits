from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import RuntimeType
from app.models.project import Project

NOHUP_GUARDS = ("nohup", "setsid", "disown", "tmux", "screen", "systemd-run")


@dataclass
class DefaultCommands:
    start_cmd: str | None = None
    stop_cmd: str | None = None
    restart_cmd: str | None = None


def _safe_name(project: Project) -> str:
    return (project.runtime_service_name or project.name).strip() or "service"


def _script_target(project: Project) -> str:
    return project.deploy_path or _safe_name(project)


def build_default_commands(project: Project) -> DefaultCommands:
    service_name = _safe_name(project)
    deploy_path = project.deploy_path or "."

    if project.runtime_type == RuntimeType.SYSTEMD_SERVICE:
        return DefaultCommands(
            start_cmd=f"systemctl start {service_name}",
            stop_cmd=f"systemctl stop {service_name}",
            restart_cmd=f"systemctl restart {service_name}",
        )
    if project.runtime_type == RuntimeType.SUPERVISORD:
        return DefaultCommands(
            start_cmd=f"supervisorctl start {service_name}",
            stop_cmd=f"supervisorctl stop {service_name}",
            restart_cmd=f"supervisorctl restart {service_name}",
        )
    if project.runtime_type == RuntimeType.PM2_PROCESS:
        return DefaultCommands(
            start_cmd=f"pm2 start {service_name}",
            stop_cmd=f"pm2 stop {service_name}",
            restart_cmd=f"pm2 restart {service_name}",
        )
    if project.runtime_type == RuntimeType.DOCKER_CONTAINER:
        return DefaultCommands(
            start_cmd=f"docker start {service_name}",
            stop_cmd=f"docker stop {service_name}",
            restart_cmd=f"docker restart {service_name}",
        )
    if project.runtime_type == RuntimeType.DOCKER_COMPOSE:
        base = f"cd {deploy_path} && docker compose"
        return DefaultCommands(
            start_cmd=f"{base} up -d",
            stop_cmd=f"{base} down",
            restart_cmd=f"{base} restart",
        )
    if project.runtime_type == RuntimeType.PYTHON_SCRIPT:
        target = _script_target(project)
        return DefaultCommands(
            start_cmd=f"python3 {target}",
            stop_cmd=f"pkill -f \"{target}\"",
            restart_cmd=f"pkill -f \"{target}\" && python3 {target}",
        )
    if project.runtime_type == RuntimeType.SHELL_SCRIPT:
        target = _script_target(project)
        return DefaultCommands(
            start_cmd=f"bash {target}",
            stop_cmd=f"pkill -f \"{target}\"",
            restart_cmd=f"pkill -f \"{target}\" && bash {target}",
        )

    return DefaultCommands()


def needs_nohup(command: str) -> bool:
    lowered = command.lower()
    return not any(guard in lowered for guard in NOHUP_GUARDS)


def wrap_nohup(command: str, log_path: str) -> str:
    return f"nohup {command} > {log_path} 2>&1 < /dev/null &"


def ensure_nohup(command: str | None, log_path: str) -> str | None:
    if not command:
        return command
    if not needs_nohup(command):
        return command
    return wrap_nohup(command, log_path)
