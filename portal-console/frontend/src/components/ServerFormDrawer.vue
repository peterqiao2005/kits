<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { createServer, updateServer } from "../api/modules";
import type {
  EnvironmentType,
  Server,
  ServerAuthType,
  ServerPayload,
  SSHKey,
} from "../types";

const props = defineProps<{
  modelValue: boolean;
  server: Server | null;
  sshKeys: SSHKey[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

const drawerTitle = computed(() => (props.server ? "Edit server" : "New server"));

const form = reactive({
  name: "",
  host: "",
  ssh_port: 22,
  ssh_username: "root",
  ssh_auth_type: "ssh_key" as ServerAuthType,
  ssh_key_id: null as number | null,
  ssh_password: "",
  env_type: "public" as EnvironmentType,
  description: "",
  tagsText: "",
});

function toTags(text: string) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function hydrate(server: Server | null) {
  form.name = server?.name ?? "";
  form.host = server?.host ?? "";
  form.ssh_port = server?.ssh_port ?? 22;
  form.ssh_username = server?.ssh_username ?? "root";
  form.ssh_auth_type = server?.ssh_auth_type ?? "ssh_key";
  form.ssh_key_id = server?.ssh_key_id ?? null;
  form.ssh_password = "";
  form.env_type = server?.env_type ?? "public";
  form.description = server?.description ?? "";
  form.tagsText = server?.tags?.join(", ") ?? "";
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) hydrate(props.server);
  },
);

watch(
  () => props.server,
  (value) => {
    if (props.modelValue) hydrate(value);
  },
);

const submitting = ref(false);

async function submit() {
  if (!form.name.trim() || !form.host.trim()) {
    ElMessage.warning("Server name and host are required.");
    return;
  }
  if (!form.ssh_username.trim()) {
    ElMessage.warning("SSH username is required.");
    return;
  }
  if (form.ssh_auth_type === "password" && !props.server && !form.ssh_password.trim()) {
    ElMessage.warning("SSH password is required for password login.");
    return;
  }
  if (form.ssh_auth_type === "ssh_key" && !form.ssh_key_id) {
    ElMessage.warning("Select an SSH key.");
    return;
  }

  submitting.value = true;
  const payload: Partial<ServerPayload> = {
    name: form.name.trim(),
    host: form.host.trim(),
    ssh_port: Number(form.ssh_port) || 22,
    ssh_username: form.ssh_username.trim(),
    ssh_auth_type: form.ssh_auth_type,
    ssh_key_id: form.ssh_auth_type === "ssh_key" ? form.ssh_key_id : null,
    env_type: form.env_type,
    description: form.description.trim() || null,
    tags: toTags(form.tagsText),
  };
  if (form.ssh_auth_type === "password" && form.ssh_password.trim()) {
    payload.ssh_password = form.ssh_password.trim();
  }

  try {
    if (props.server) {
      await updateServer(props.server.id, payload);
      ElMessage.success("Server updated.");
    } else {
      await createServer(payload as ServerPayload);
      ElMessage.success("Server created.");
    }
    emit("saved");
    visible.value = false;
  } catch {
    ElMessage.error("Failed to save server.");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-drawer v-model="visible" size="520px" :title="drawerTitle" destroy-on-close>
    <el-form label-position="top" class="form-grid">
      <el-form-item label="Server name">
        <el-input v-model="form.name" placeholder="prod-app-01" />
      </el-form-item>
      <el-form-item label="Host">
        <el-input v-model="form.host" placeholder="192.168.1.10 or server.example.com" />
      </el-form-item>
      <el-form-item label="SSH port">
        <el-input-number v-model="form.ssh_port" :min="1" :max="65535" />
      </el-form-item>
      <el-form-item label="SSH username">
        <el-input v-model="form.ssh_username" placeholder="root / ubuntu / deploy" />
      </el-form-item>
      <el-form-item label="Authentication">
        <el-radio-group v-model="form.ssh_auth_type">
          <el-radio-button label="ssh_key">SSH key</el-radio-button>
          <el-radio-button label="password">Password</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.ssh_auth_type === 'ssh_key'" label="SSH key">
        <el-select v-model="form.ssh_key_id" placeholder="Select uploaded key">
          <el-option v-for="sshKey in sshKeys" :key="sshKey.id" :label="sshKey.name" :value="sshKey.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-else label="SSH password">
        <el-input
          v-model="form.ssh_password"
          type="password"
          show-password
          placeholder="Leave blank to keep current password when editing"
        />
      </el-form-item>
      <el-form-item label="Environment">
        <el-select v-model="form.env_type">
          <el-option label="public" value="public" />
          <el-option label="lan" value="lan" />
          <el-option label="local" value="local" />
        </el-select>
      </el-form-item>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Tags">
        <el-input v-model="form.tagsText" placeholder="prod, app, ubuntu" />
      </el-form-item>
    </el-form>

    <div class="drawer-actions">
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">Save</el-button>
    </div>
  </el-drawer>
</template>
