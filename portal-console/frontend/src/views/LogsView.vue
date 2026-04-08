<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { getOperationLogs } from "../api/modules";
import type { OperationLog } from "../types";

const loading = ref(false);
const logs = ref<OperationLog[]>([]);

async function loadData() {
  loading.value = true;
  try {
    logs.value = await getOperationLogs();
  } catch {
    ElMessage.error("Failed to load operation logs.");
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <el-card shadow="never" class="panel-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <div>
          <p class="page-kicker">Execution Trail</p>
          <h3>Operation logs</h3>
        </div>
        <el-tag type="info" effect="plain">{{ logs.length }} items</el-tag>
      </div>
    </template>
    <el-table :data="logs" row-key="id">
      <el-table-column prop="created_at" label="Time" min-width="180" />
      <el-table-column prop="project_name" label="Service" min-width="180" />
      <el-table-column prop="action" label="Action" width="120" />
      <el-table-column prop="status" label="Status" width="120" />
      <el-table-column prop="username" label="Actor" width="120" />
      <el-table-column prop="external_execution_id" label="Execution ID" width="180" />
      <el-table-column prop="message" label="Message" min-width="280" />
    </el-table>
  </el-card>
</template>
