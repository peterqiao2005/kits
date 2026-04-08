from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class EnvironmentType(str, Enum):
    PUBLIC = "public"
    LAN = "lan"
    LOCAL = "local"


class ServerAuthType(str, Enum):
    PASSWORD = "password"
    SSH_KEY = "ssh_key"


class RuntimeType(str, Enum):
    DOCKER_COMPOSE = "docker_compose"
    DOCKER_CONTAINER = "docker_container"
    SYSTEMD_SERVICE = "systemd_service"
    SUPERVISORD = "supervisord"
    PM2_PROCESS = "pm2_process"
    PYTHON_SCRIPT = "python_script"
    SHELL_SCRIPT = "shell_script"
    CMD = "cmd"
    CUSTOM = "custom"


class ProjectStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class RuntimeStatus(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ProjectLinkType(str, Enum):
    WEB = "web"
    ADMIN = "admin"
    GITHUB = "github"
    DOCS = "docs"
    SSH = "ssh"
    MONITOR = "monitor"
    LOGS = "logs"


class OperationAction(str, Enum):
    START = "start"
    STOP = "stop"
    RESTART = "restart"


class OperationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [item.value for item in enum_class]
