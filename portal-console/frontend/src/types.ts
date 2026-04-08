export type UserRole = "admin" | "viewer";
export type EnvironmentType = "public" | "lan" | "local";
export type ServerAuthType = "password" | "ssh_key";
export type RuntimeType =
  | "docker_compose"
  | "docker_container"
  | "systemd_service"
  | "supervisord"
  | "pm2_process"
  | "python_script"
  | "shell_script"
  | "cmd"
  | "custom";
export type ProjectStatus = "online" | "offline" | "degraded" | "unknown";
export type RuntimeStatus = "active" | "stopped" | "unknown";
export type LinkType = "web" | "admin" | "github" | "docs" | "ssh" | "monitor" | "logs";
export type OperationAction = "start" | "stop" | "restart";
export type OperationStatus = "pending" | "running" | "succeeded" | "failed";

export interface ActionResult {
  status: OperationStatus;
  message?: string;
  execution_id: string;
  log_id: number;
}

export interface User {
  id: number;
  username: string;
  role: UserRole;
}

export interface SSHKeySummary {
  id: number;
  name: string;
  original_filename: string;
}

export interface SSHKey extends SSHKeySummary {
  note?: string | null;
  created_at: string;
  updated_at: string;
  server_count: number;
}

export interface Server {
  id: number;
  name: string;
  host: string;
  ssh_port: number;
  ssh_username?: string | null;
  ssh_auth_type: ServerAuthType;
  ssh_key_id?: number | null;
  env_type: EnvironmentType;
  description?: string | null;
  tags: string[];
  has_ssh_password: boolean;
  ssh_key?: SSHKeySummary | null;
  created_at: string;
  updated_at: string;
  project_count: number;
}

export interface ServerPayload {
  name: string;
  host: string;
  ssh_port: number;
  ssh_username: string;
  ssh_auth_type: ServerAuthType;
  ssh_key_id?: number | null;
  ssh_password?: string;
  env_type: EnvironmentType;
  description?: string | null;
  tags?: string[];
}

export interface ProjectLink {
  id: number;
  project_id: number;
  link_type: LinkType;
  title: string;
  url: string;
  sort_order: number;
}

export interface Project {
  id: number;
  name: string;
  description?: string | null;
  tags: string[];
  repo_url?: string | null;
  server_id: number;
  deploy_path?: string | null;
  runtime_type: RuntimeType;
  start_note?: string | null;
  stop_note?: string | null;
  access_note?: string | null;
  runtime_service_name?: string | null;
  start_cmd?: string | null;
  stop_cmd?: string | null;
  restart_cmd?: string | null;
  rundeck_job_start_id?: string | null;
  rundeck_job_stop_id?: string | null;
  rundeck_job_restart_id?: string | null;
  kuma_monitor_id?: string | null;
  is_favorite: boolean;
  current_status: ProjectStatus;
  last_checked_at?: string | null;
  http_status: ProjectStatus;
  http_checked_at?: string | null;
  runtime_status: RuntimeStatus;
  runtime_checked_at?: string | null;
  created_at?: string;
  updated_at?: string;
  server: Server;
  links: ProjectLink[];
  can_start: boolean;
  can_stop: boolean;
  can_restart: boolean;
}

export interface ProjectPayload {
  name: string;
  description?: string | null;
  tags?: string[];
  repo_url?: string | null;
  server_id: number;
  deploy_path?: string | null;
  runtime_type: RuntimeType;
  start_note?: string | null;
  stop_note?: string | null;
  access_note?: string | null;
  runtime_service_name?: string | null;
  start_cmd?: string | null;
  stop_cmd?: string | null;
  restart_cmd?: string | null;
  kuma_monitor_id?: string | null;
  is_favorite?: boolean;
}

export interface OperationLog {
  id: number;
  project_id: number;
  project_name: string;
  user_id?: number | null;
  username?: string | null;
  action: OperationAction;
  status: OperationStatus;
  message?: string | null;
  external_execution_id?: string | null;
  created_at: string;
}

export interface IntegrationsSummary {
  rundeck: {
    configured: boolean;
    base_url?: string | null;
  };
  kuma: {
    configured: boolean;
    base_url?: string | null;
  };
}
