<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { createSshKey, updateSshKey } from "../api/modules";
import type { SSHKey } from "../types";

const props = defineProps<{
  modelValue: boolean;
  sshKey: SSHKey | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

const drawerTitle = computed(() => (props.sshKey ? "Edit SSH key" : "New SSH key"));
const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);

const form = reactive({
  name: "",
  note: "",
});

function hydrate(sshKey: SSHKey | null) {
  form.name = sshKey?.name ?? "";
  form.note = sshKey?.note ?? "";
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) hydrate(props.sshKey);
  },
);

watch(
  () => props.sshKey,
  (value) => {
    if (props.modelValue) hydrate(value);
  },
);

function pickFile() {
  fileInput.value?.click();
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement;
  selectedFile.value = target.files?.[0] ?? null;
}

const submitting = ref(false);

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning("SSH key name is required.");
    return;
  }
  if (!props.sshKey && !selectedFile.value) {
    ElMessage.warning("Upload a private key file.");
    return;
  }

  submitting.value = true;
  const payload = new FormData();
  payload.append("name", form.name.trim());
  if (form.note.trim()) payload.append("note", form.note.trim());
  if (selectedFile.value) payload.append("private_key", selectedFile.value);

  try {
    if (props.sshKey) {
      await updateSshKey(props.sshKey.id, payload);
      ElMessage.success("SSH key updated.");
    } else {
      await createSshKey(payload);
      ElMessage.success("SSH key created.");
    }
    emit("saved");
    visible.value = false;
  } catch {
    ElMessage.error("Failed to save SSH key.");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-drawer v-model="visible" size="520px" :title="drawerTitle" destroy-on-close>
    <el-form label-position="top" class="form-grid">
      <el-form-item label="Name">
        <el-input v-model="form.name" placeholder="prod-root-key" />
      </el-form-item>
      <el-form-item label="Private key file">
        <div class="file-picker">
          <input ref="fileInput" class="native-file-input" type="file" @change="onFileChange" />
          <el-button @click="pickFile">Choose file</el-button>
          <span>{{ selectedFile?.name || props.sshKey?.original_filename || "No file selected" }}</span>
        </div>
        <p class="muted-line">Stored under `backend/data/ssh_keys` inside portal-console.</p>
      </el-form-item>
      <el-form-item label="Note">
        <el-input v-model="form.note" type="textarea" :rows="3" placeholder="What this key is for" />
      </el-form-item>
    </el-form>

    <div class="drawer-actions">
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">Save</el-button>
    </div>
  </el-drawer>
</template>
