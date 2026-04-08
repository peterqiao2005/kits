<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { createProject, updateProject } from "../api/modules";
import type { Project, ProjectPayload, RuntimeType, Server } from "../types";

const props = defineProps<{
  modelValue: boolean;
  project: Project | null;
  servers: Server[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

const isNew = computed(() => !props.project);
const drawerTitle = computed(() => (props.project ? "Edit service" : "New service"));

const dirty = reactive({
  start: false,
  stop: false,
  restart: false,
});

const form = reactive({
  name: "",
  description: "",
  tagsText: "",
  repo_url: "",
  server_id: 0,
  deploy_path: "",
  runtime_type: "systemd_service" as RuntimeType,
  runtime_service_name: "",
  start_note: "",
  stop_note: "",
  access_note: "",
  start_cmd: "",
  stop_cmd: "",
  restart_cmd: "",
  kuma_monitor_id: "",
  is_favorite: false,
});

const runtimeOptions: Array<{ label: string; value: RuntimeType }> = [
  { label: "systemd_service", value: "systemd_service" },
  { label: "supervisord", value: "supervisord" },
  { label: "pm2_process", value: "pm2_process" },
  { label: "docker_container", value: "docker_container" },
  { label: "docker_compose", value: "docker_compose" },
  { label: "python_script", value: "python_script" },
  { label: "shell_script", value: "shell_script" },
  { label: "cmd", value: "cmd" },
  { label: "custom", value: "custom" },
];

const guardTokens = ["nohup", "setsid", "disown", "tmux", "screen", "systemd-run"];

function resetDirty() {
  dirty.start = false;
  dirty.stop = false;
  dirty.restart = false;
}

function safeName() {
  const name = form.runtime_service_name || form.name || "service";
  return name.trim() || "service";
}

function scriptTarget() {
  return form.deploy_path || safeName();
}

function defaultCommands() {
  const service = safeName();
  const deployPath = form.deploy_path || ".";
  if (form.runtime_type === "systemd_service") {
    return {
      start_cmd: `systemctl start ${service}`,
      stop_cmd: `systemctl stop ${service}`,
      restart_cmd: `systemctl restart ${service}`,
    };
  }
  if (form.runtime_type === "supervisord") {
    return {
      start_cmd: `supervisorctl start ${service}`,
      stop_cmd: `supervisorctl stop ${service}`,
      restart_cmd: `supervisorctl restart ${service}`,
    };
  }
  if (form.runtime_type === "pm2_process") {
    return {
      start_cmd: `pm2 start ${service}`,
      stop_cmd: `pm2 stop ${service}`,
      restart_cmd: `pm2 restart ${service}`,
    };
  }
  if (form.runtime_type === "docker_container") {
    return {
      start_cmd: `docker start ${service}`,
      stop_cmd: `docker stop ${service}`,
      restart_cmd: `docker restart ${service}`,
    };
  }
  if (form.runtime_type === "docker_compose") {
    return {
      start_cmd: `cd ${deployPath} && docker compose up -d`,
      stop_cmd: `cd ${deployPath} && docker compose down`,
      restart_cmd: `cd ${deployPath} && docker compose restart`,
    };
  }
  if (form.runtime_type === "python_script") {
    const target = scriptTarget();
    return {
      start_cmd: `python3 ${target}`,
      stop_cmd: `pkill -f "${target}"`,
      restart_cmd: `pkill -f "${target}" && python3 ${target}`,
    };
  }
  if (form.runtime_type === "shell_script") {
    const target = scriptTarget();
    return {
      start_cmd: `bash ${target}`,
      stop_cmd: `pkill -f "${target}"`,
      restart_cmd: `pkill -f "${target}" && bash ${target}`,
    };
  }
  return {
    start_cmd: "",
    stop_cmd: "",
    restart_cmd: "",
  };
}

function applyDefaults(force = false) {
  const defaults = defaultCommands();
  const allowAuto = isNew.value;
  if (force || (allowAuto && !dirty.start)) form.start_cmd = defaults.start_cmd || form.start_cmd;
  if (force || (allowAuto && !dirty.stop)) form.stop_cmd = defaults.stop_cmd || form.stop_cmd;
  if (force || (allowAuto && !dirty.restart)) form.restart_cmd = defaults.restart_cmd || form.restart_cmd;
}

function toTags(text: string) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function shouldWrap(command: string) {
  const lowered = command.toLowerCase();
  return !guardTokens.some((token) => lowered.includes(token));
}

function wrapNohup(command: string) {
  const logPath = `/tmp/portal-console-${safeName().replace(/ /g, "_")}.log`;
  return `nohup ${command} > ${logPath} 2>&1 < /dev/null &`;
}

function normalizeCommand(command: string) {
  const trimmed = command.trim();
  if (!trimmed) return "";
  if (form.runtime_type === "cmd" || form.runtime_type === "custom") {
    return shouldWrap(trimmed) ? wrapNohup(trimmed) : trimmed;
  }
  return trimmed;
}

function hydrateForm(project: Project | null) {
  form.name = project?.name ?? "";
  form.description = project?.description ?? "";
  form.tagsText = project?.tags?.join(", ") ?? "";
  form.repo_url = project?.repo_url ?? "";
  form.server_id = project?.server_id ?? (props.servers[0]?.id ?? 0);
  form.deploy_path = project?.deploy_path ?? "";
  form.runtime_type = project?.runtime_type ?? "systemd_service";
  form.runtime_service_name = project?.runtime_service_name ?? "";
  form.start_note = project?.start_note ?? "";
  form.stop_note = project?.stop_note ?? "";
  form.access_note = project?.access_note ?? "";
  form.start_cmd = project?.start_cmd ?? "";
  form.stop_cmd = project?.stop_cmd ?? "";
  form.restart_cmd = project?.restart_cmd ?? "";
  form.kuma_monitor_id = project?.kuma_monitor_id ?? "";
  form.is_favorite = project?.is_favorite ?? false;
  resetDirty();
  applyDefaults();
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) hydrateForm(props.project);
  },
);

watch(
  () => props.project,
  (value) => {
    if (props.modelValue) hydrateForm(value);
  },
);

watch(
  () => props.servers,
  (value) => {
    if (!form.server_id && value.length) form.server_id = value[0].id;
  },
  { deep: true },
);

watch(
  () => [form.runtime_type, form.runtime_service_name, form.deploy_path, form.name],
  () => applyDefaults(),
);

const submitting = ref(false);

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning("Service name is required.");
    return;
  }
  if (!form.server_id) {
    ElMessage.warning("Server is required.");
    return;
  }

  submitting.value = true;
  const payload: ProjectPayload = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    tags: toTags(form.tagsText),
    repo_url: form.repo_url.trim() || null,
    server_id: form.server_id,
    deploy_path: form.deploy_path.trim() || null,
    runtime_type: form.runtime_type,
    runtime_service_name: form.runtime_service_name.trim() || null,
    start_note: form.start_note.trim() || null,
    stop_note: form.stop_note.trim() || null,
    access_note: form.access_note.trim() || null,
    start_cmd: normalizeCommand(form.start_cmd),
    stop_cmd: form.stop_cmd.trim() || null,
    restart_cmd: normalizeCommand(form.restart_cmd),
    kuma_monitor_id: form.kuma_monitor_id.trim() || null,
    is_favorite: form.is_favorite,
  };

  try {
    if (props.project) {
      await updateProject(props.project.id, payload);
      ElMessage.success("Service updated.");
    } else {
      await createProject(payload);
      ElMessage.success("Service created.");
    }
    emit("saved");
    visible.value = false;
  } catch {
    ElMessage.error("Failed to save service.");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-drawer v-model="visible" size="560px" :title="drawerTitle" destroy-on-close>
    <el-form label-position="top" class="form-grid">
      <el-form-item label="Service name">
        <el-input v-model="form.name" placeholder="Unique service name" />
      </el-form-item>
      <el-form-item label="Server">
        <el-select v-model="form.server_id" placeholder="Select server">
          <el-option v-for="server in servers" :key="server.id" :label="server.name" :value="server.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Tags">
        <el-input v-model="form.tagsText" placeholder="api, prod, internal" />
      </el-form-item>
      <el-form-item label="Repository">
        <el-input v-model="form.repo_url" placeholder="https://github.com/..." />
      </el-form-item>
      <el-form-item label="Deploy path">
        <el-input v-model="form.deploy_path" placeholder="/opt/app or script path" />
      </el-form-item>
      <el-form-item label="Runtime type">
        <el-select v-model="form.runtime_type">
          <el-option v-for="item in runtimeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="Runtime service name">
        <el-input v-model="form.runtime_service_name" placeholder="systemd / pm2 / docker target name" />
      </el-form-item>
      <el-form-item label="Start note">
        <el-input v-model="form.start_note" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Stop note">
        <el-input v-model="form.stop_note" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Access note">
        <el-input v-model="form.access_note" type="textarea" :rows="2" />
      </el-form-item>

      <el-divider>Commands</el-divider>
      <p class="muted-line">
        For `cmd` and `custom`, start and restart are wrapped with `nohup` unless you already added your own guard.
      </p>

      <el-form-item label="Start command">
        <el-input v-model="form.start_cmd" type="textarea" :rows="2" @input="dirty.start = true" />
      </el-form-item>
      <el-form-item label="Stop command">
        <el-input v-model="form.stop_cmd" type="textarea" :rows="2" @input="dirty.stop = true" />
      </el-form-item>
      <el-form-item label="Restart command">
        <el-input v-model="form.restart_cmd" type="textarea" :rows="2" @input="dirty.restart = true" />
      </el-form-item>

      <el-form-item label="Kuma monitor id">
        <el-input v-model="form.kuma_monitor_id" placeholder="Optional" />
      </el-form-item>
      <el-form-item label="Favorite">
        <el-switch v-model="form.is_favorite" />
      </el-form-item>
    </el-form>

    <div class="drawer-actions">
      <el-button @click="applyDefaults(true)">Reset commands</el-button>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">Save</el-button>
    </div>
  </el-drawer>
</template>
