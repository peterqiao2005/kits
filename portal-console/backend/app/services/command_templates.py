from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import RuntimeType, OSType
from app.models.project import Project
from app.models.server import Server

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


def build_default_commands(project: Project, server: Server) -> DefaultCommands:
    service_name = _safe_name(project)
    deploy_path = project.deploy_path or "."

    if server.os_type == OSType.WINDOWS:
        win_deploy_path = deploy_path.replace("/", "\\")
        if project.runtime_type == RuntimeType.SYSTEMD_SERVICE:
            return DefaultCommands(
                start_cmd=f"powershell -Command \"Start-Service -Name '{service_name}'\"",
                stop_cmd=f"powershell -Command \"Stop-Service -Name '{service_name}'\"",
                restart_cmd=f"powershell -Command \"Restart-Service -Name '{service_name}'\"",
            )
        if project.runtime_type == RuntimeType.SUPERVISORD:
            # supervisor doesn't run on Windows typically, but if chosen, map to PowerShell services
            return DefaultCommands(
                start_cmd=f"powershell -Command \"Start-Service -Name '{service_name}'\"",
                stop_cmd=f"powershell -Command \"Stop-Service -Name '{service_name}'\"",
                restart_cmd=f"powershell -Command \"Restart-Service -Name '{service_name}'\"",
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
            return DefaultCommands(
                start_cmd=f"cmd /c \"cd /d {win_deploy_path} && docker compose up -d\"",
                stop_cmd=f"cmd /c \"cd /d {win_deploy_path} && docker compose down\"",
                restart_cmd=f"cmd /c \"cd /d {win_deploy_path} && docker compose restart\"",
            )
        if project.runtime_type == RuntimeType.PYTHON_SCRIPT:
            target = _script_target(project).replace("/", "\\")
            escaped_target = target.replace('\\', '\\\\')
            safe_name_log = service_name.replace(" ", "_")
            log_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}.log"
            err_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}-err.log"
            start_args = f"-ArgumentList '{target}' -WindowStyle Hidden -RedirectStandardOutput '{log_path}' -RedirectStandardError '{err_path}'"
            return DefaultCommands(
                start_cmd=f"powershell -Command \"Start-Process python {start_args}\"",
                stop_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_target}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\"",
                restart_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_target}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; Start-Process python {start_args}\"",
            )
        if project.runtime_type == RuntimeType.SHELL_SCRIPT:
            target = _script_target(project).replace("/", "\\")
            escaped_target = target.replace('\\', '\\\\')
            safe_name_log = service_name.replace(" ", "_")
            log_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}.log"
            err_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}-err.log"
            if target.endswith(".ps1"):
                start_args = f"-ArgumentList '-File', '{target}' -WindowStyle Hidden -RedirectStandardOutput '{log_path}' -RedirectStandardError '{err_path}'"
                start_cmd = f"powershell -Command \"Start-Process powershell {start_args}\""
            else:
                start_args = f"-ArgumentList '/c', '{target}' -WindowStyle Hidden -RedirectStandardOutput '{log_path}' -RedirectStandardError '{err_path}'"
                start_cmd = f"powershell -Command \"Start-Process cmd {start_args}\""
            return DefaultCommands(
                start_cmd=start_cmd,
                stop_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_target}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\"",
                restart_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_target}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; {start_cmd[19:-1]}\"",
            )
        if project.runtime_type == RuntimeType.CMD:
            start_cmd = f"cmd /c \"cd /d {win_deploy_path} && start /b {service_name}.bat\""
            stop_cmd = f"taskkill /F /FI \"COMMANDLINE eq *{service_name}*\""
            return DefaultCommands(
                start_cmd=start_cmd,
                stop_cmd=stop_cmd,
                restart_cmd=f"{stop_cmd} & {start_cmd}",
            )
        if project.runtime_type == RuntimeType.POWERSHELL:
            script = f"{win_deploy_path}\\{service_name}.ps1"
            escaped_script = script.replace('\\', '\\\\')
            safe_name_log = service_name.replace(" ", "_")
            log_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}.log"
            err_path = f"C:\\Windows\\Temp\\portal-console-{safe_name_log}-err.log"
            start_args = f"-ArgumentList '-ExecutionPolicy', 'Bypass', '-File', '{script}' -WindowStyle Hidden -RedirectStandardOutput '{log_path}' -RedirectStandardError '{err_path}'"
            start_cmd = f"powershell -Command \"Start-Process powershell {start_args}\""
            return DefaultCommands(
                start_cmd=start_cmd,
                stop_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_script}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\"",
                restart_cmd=f"powershell -Command \"Get-CimInstance Win32_Process -Filter \\\"CommandLine like '%{escaped_script}%'\\\" | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; {start_cmd[19:-1]}\"",
            )
        return DefaultCommands()

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
    if project.runtime_type == RuntimeType.CMD:
        return DefaultCommands(
            start_cmd=f"cd {deploy_path} && ./{service_name}",
            stop_cmd=f"pkill -f \"{service_name}\"",
            restart_cmd=f"pkill -f \"{service_name}\" && cd {deploy_path} && ./{service_name}",
        )
    if project.runtime_type == RuntimeType.POWERSHELL:
        script = f"{deploy_path}/{service_name}.ps1"
        return DefaultCommands(
            start_cmd=f"pwsh -ExecutionPolicy Bypass -File {script}",
            stop_cmd=f"pkill -f \"{script}\"",
            restart_cmd=f"pkill -f \"{script}\" && pwsh -ExecutionPolicy Bypass -File {script}",
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
