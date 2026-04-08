<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { deleteSshKey, getSshKeys } from "../api/modules";
import SshKeyFormDrawer from "../components/SshKeyFormDrawer.vue";
import { sessionState } from "../lib/session";
import type { SSHKey } from "../types";

const loading = ref(false);
const sshKeys = ref<SSHKey[]>([]);
const showForm = ref(false);
const editingSshKey = ref<SSHKey | null>(null);

const canOperate = computed(() => sessionState.user?.role === "admin");

async function loadData() {
  loading.value = true;
  try {
    sshKeys.value = await getSshKeys();
  } catch {
    ElMessage.error("Failed to load SSH keys.");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingSshKey.value = null;
  showForm.value = true;
}

function openEdit(sshKey: SSHKey) {
  editingSshKey.value = sshKey;
  showForm.value = true;
}

async function removeSshKey(sshKey: SSHKey) {
  try {
    await ElMessageBox.confirm(
      `Delete SSH key "${sshKey.name}"?`,
      "Delete SSH Key",
      { type: "warning" },
    );
    await deleteSshKey(sshKey.id);
    ElMessage.success("SSH key deleted.");
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("Failed to delete SSH key.");
    }
  }
}

onMounted(loadData);
</script>

<template>
  <section class="page-grid">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <div>
            <p class="page-kicker">Credential Vault</p>
            <h3>SSH key inventory</h3>
          </div>
          <el-button v-if="canOperate" type="success" @click="openCreate">New SSH key</el-button>
        </div>
      </template>

      <el-table :data="sshKeys" v-loading="loading" row-key="id">
        <el-table-column label="Name" min-width="220">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <p>{{ row.note || "No note" }}</p>
          </template>
        </el-table-column>
        <el-table-column prop="original_filename" label="File" min-width="220" />
        <el-table-column prop="server_count" label="Servers" width="110" />
        <el-table-column prop="updated_at" label="Updated" min-width="180" />
        <el-table-column v-if="canOperate" label="Actions" width="180">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">Edit</el-button>
              <el-button link type="danger" @click="removeSshKey(row)">Delete</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>

  <SshKeyFormDrawer
    v-model="showForm"
    :ssh-key="editingSshKey"
    @saved="loadData"
  />
</template>
