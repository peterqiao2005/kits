<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { getIntegrations, getAgentSecret, generateAgentSecret } from "../api/modules";
import type { IntegrationsSummary } from "../types";

const loading = ref(false);
const integrations = ref<IntegrationsSummary | null>(null);
const agentSecret = ref("");
const generating = ref(false);

async function loadAgentSecret() {
  try {
    const res = await getAgentSecret();
    agentSecret.value = res.secret;
  } catch {
    // Viewer role fails to fetch agent secret, ignore silently or warn
  }
}

async function onGenerateSecret() {
  generating.value = true;
  try {
    const res = await generateAgentSecret();
    agentSecret.value = res.secret;
    ElMessage.success("New Windows Agent JWT Secret generated successfully.");
  } catch {
    ElMessage.error("Failed to generate new secret.");
  } finally {
    generating.value = false;
  }
}

async function loadData() {
  loading.value = true;
  try {
    integrations.value = await getIntegrations();
    await loadAgentSecret();
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

    <el-card shadow="never" class="panel-card" v-if="agentSecret">
      <template #header>
        <div class="card-header">
          <span>Windows Helper Agent</span>
          <el-tag type="primary" effect="plain">Security</el-tag>
        </div>
      </template>
      <p>Configure and generate the JWT Secret used to authenticate the Windows Helper Agent running locally on dev machines.</p>
      <div style="display: flex; gap: 12px; align-items: center; margin: 16px 0; flex-wrap: wrap;">
        <el-input v-model="agentSecret" style="width: 320px;" readonly placeholder="Generating secret..." show-password />
        <el-button type="primary" :loading="generating" @click="onGenerateSecret">Generate New Secret</el-button>
      </div>
      <p class="muted-line">Copy this secret key to your Windows Agent <code>config.json</code> under the <code>"secret"</code> key.</p>
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
