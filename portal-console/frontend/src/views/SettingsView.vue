<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { getIntegrations } from "../api/modules";
import type { IntegrationsSummary } from "../types";

const loading = ref(false);
const integrations = ref<IntegrationsSummary | null>(null);

async function loadData() {
  loading.value = true;
  try {
    integrations.value = await getIntegrations();
  } catch {
    ElMessage.warning("Only admins can view integration summaries.");
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <section class="settings-grid" v-loading="loading">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <span>Direct SSH</span>
          <el-tag type="success" effect="plain">Active</el-tag>
        </div>
      </template>
      <p>Services are started, stopped, and checked directly over SSH using the credentials configured on each server.</p>
      <p class="muted-line">Both password login and uploaded private-key login are supported.</p>
      <code>SSH_KEY_STORAGE_DIR / SSH_KEY_ENCRYPTION_SECRET</code>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <span>Uptime Kuma</span>
          <el-tag :type="integrations?.kuma.configured ? 'success' : 'info'" effect="plain">
            {{ integrations?.kuma.configured ? "Configured" : "Not configured" }}
          </el-tag>
        </div>
      </template>
      <p>HTTP health remains the preferred external signal when a monitor is bound to a service.</p>
      <p class="muted-line">Base URL: {{ integrations?.kuma.base_url || "Not set" }}</p>
      <code>KUMA_URL / KUMA_TOKEN</code>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <span>Permission model</span>
          <el-tag type="warning" effect="plain">RBAC</el-tag>
        </div>
      </template>
      <p>`admin` can manage services, servers, SSH keys, and links.</p>
      <p>`viewer` can inspect service status, links, and operation history.</p>
      <p class="muted-line">The bootstrap admin is created from backend environment variables on startup.</p>
    </el-card>
  </section>
</template>
