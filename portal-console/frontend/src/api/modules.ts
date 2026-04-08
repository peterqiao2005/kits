import apiClient from "./client";
import type {
  IntegrationsSummary,
  OperationAction,
  OperationLog,
  Project,
  ProjectPayload,
  ServerPayload,
  Server,
  SSHKey,
  User,
  ActionResult,
} from "../types";

export async function login(username: string, password: string) {
  const { data } = await apiClient.post<{ access_token: string; token_type: string }>("/auth/login", {
    username,
    password,
  });
  return data;
}

export async function getMe() {
  const { data } = await apiClient.get<User>("/auth/me");
  return data;
}

export async function getServers() {
  const { data } = await apiClient.get<Server[]>("/servers");
  return data;
}

export async function createServer(payload: ServerPayload) {
  const { data } = await apiClient.post<Server>("/servers", payload);
  return data;
}

export async function updateServer(serverId: number, payload: Partial<ServerPayload>) {
  const { data } = await apiClient.put<Server>(`/servers/${serverId}`, payload);
  return data;
}

export async function deleteServer(serverId: number) {
  await apiClient.delete(`/servers/${serverId}`);
}

export async function getSshKeys() {
  const { data } = await apiClient.get<SSHKey[]>("/ssh-keys");
  return data;
}

export async function createSshKey(payload: FormData) {
  const { data } = await apiClient.post<SSHKey>("/ssh-keys", payload);
  return data;
}

export async function updateSshKey(sshKeyId: number, payload: FormData) {
  const { data } = await apiClient.put<SSHKey>(`/ssh-keys/${sshKeyId}`, payload);
  return data;
}

export async function deleteSshKey(sshKeyId: number) {
  await apiClient.delete(`/ssh-keys/${sshKeyId}`);
}

export async function getProjects(params?: Record<string, string | number | boolean | undefined>) {
  const { data } = await apiClient.get<Project[]>("/projects", { params });
  return data;
}

export async function getProject(projectId: number) {
  const { data } = await apiClient.get<Project>(`/projects/${projectId}`);
  return data;
}

export async function createProject(payload: ProjectPayload) {
  const { data } = await apiClient.post<Project>("/projects", payload);
  return data;
}

export async function updateProject(projectId: number, payload: Partial<ProjectPayload>) {
  const { data } = await apiClient.put<Project>(`/projects/${projectId}`, payload);
  return data;
}

export async function deleteProject(projectId: number) {
  await apiClient.delete(`/projects/${projectId}`);
}

export async function syncProjectStatus(projectIds?: number[]) {
  const { data } = await apiClient.post("/projects/sync-status", {
    project_ids: projectIds?.length ? projectIds : undefined,
  });
  return data;
}

export async function runAction(projectId: number, action: OperationAction) {
  const { data } = await apiClient.post<ActionResult>(`/projects/${projectId}/${action}`);
  return data;
}

export async function getOperationLogs(projectId?: number) {
  const { data } = await apiClient.get<OperationLog[]>("/operation-logs", {
    params: projectId ? { project_id: projectId } : undefined,
  });
  return data;
}

export async function getIntegrations() {
  const { data } = await apiClient.get<IntegrationsSummary>("/settings/integrations");
  return data;
}
