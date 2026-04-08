<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { deleteProject, getOperationLogs, getProject, getServers, runAction } from "../api/modules";
import ActionButtons from "../components/ActionButtons.vue";
import ProjectFormDrawer from "../components/ProjectFormDrawer.vue";
import RuntimeTag from "../components/RuntimeTag.vue";
import StatusTag from "../components/StatusTag.vue";
import { sessionState } from "../lib/session";
import type { OperationLog, Project, Server } from "../types";

const route = useRoute();
const router = useRouter();
const project = ref<Project | null>(null);
const logs = ref<OperationLog[]>([]);
const servers = ref<Server[]>([]);
const loading = ref(false);
const loadingAction = ref("");
const deleting = ref(false);
const showForm = ref(false);

const projectId = computed(() => Number(route.params.id));
const canOperate = computed(() => sessionState.user?.role === "admin");

async function loadData() {
  loading.value = true;
  try {
    const [projectData, logData, serverData] = await Promise.all([
      getProject(projectId.value),
      getOperationLogs(projectId.value),
      getServers(),
    ]);
    project.value = projectData;
    logs.value = logData;
    servers.value = serverData;
  } catch {
    ElMessage.error("Failed to load service detail.");
  } finally {
    loading.value = false;
  }
}

async function onAction(action: "start" | "stop" | "restart") {
  if (!project.value) return;
  loadingAction.value = action;
  try {
    const result = await runAction(project.value.id, action);
    if (result.status === "succeeded") {
      ElMessage.success("Action completed over SSH.");
    } else {
      ElMessage.error(result.message || "Action failed.");
    }
    await loadData();
  } catch {
    ElMessage.error("Action failed.");
  } finally {
    loadingAction.value = "";
  }
}

function openEdit() {
  showForm.value = true;
}

async function onDelete() {
  if (!project.value) return;

  try {
    await ElMessageBox.confirm(
      `Delete service "${project.value.name}"? This cannot be undone.`,
      "Delete service",
      {
        type: "warning",
        confirmButtonText: "Delete",
        cancelButtonText: "Cancel",
      },
    );
  } catch {
    return;
  }

  deleting.value = true;
  try {
    await deleteProject(project.value.id);
    ElMessage.success("Service deleted.");
    await router.push("/dashboard");
  } catch {
    ElMessage.error("Failed to delete service.");
  } finally {
    deleting.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div v-if="project" v-loading="loading" class="detail-grid">
    <el-card shadow="never" class="panel-card hero-card">
      <div class="detail-hero">
        <div>
          <p class="page-kicker">{{ project.runtime_type }}</p>
          <h3>{{ project.name }}</h3>
          <p>{{ project.description || "No service summary" }}</p>
        </div>
        <div class="detail-status">
          <div class="status-stack">
            <StatusTag :status="project.http_status" />
            <small>HTTP</small>
          </div>
          <div class="status-stack">
            <RuntimeTag :status="project.runtime_status" />
            <small>Runtime</small>
          </div>
          <span>{{ project.server.name }} / {{ project.server.host }}</span>
        </div>
      </div>
      <div class="tag-row">
        <el-tag v-for="tag in project.tags" :key="tag" effect="plain" round>{{ tag }}</el-tag>
      </div>
      <ActionButtons
        :can-start="project.can_start && canOperate"
        :can-stop="project.can_stop && canOperate"
        :can-restart="project.can_restart && canOperate"
        :loading-action="loadingAction"
        @action="onAction"
      />
      <div class="detail-actions">
        <el-button v-if="canOperate" type="primary" plain @click="openEdit">Edit service</el-button>
        <el-button
          v-if="canOperate"
          type="danger"
          plain
          :loading="deleting"
          @click="onDelete"
        >
          Delete service
        </el-button>
      </div>
    </el-card>

    <div class="detail-columns">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="card-header">
            <span>Access and deploy</span>
            <el-tag type="info" effect="plain">Links</el-tag>
          </div>
        </template>
        <div class="detail-list">
          <div>
            <strong>Repository</strong>
            <a v-if="project.repo_url" :href="project.repo_url" target="_blank">{{ project.repo_url }}</a>
            <span v-else>Not configured</span>
          </div>
          <div>
            <strong>Deploy path</strong>
            <span>{{ project.deploy_path || "Not configured" }}</span>
          </div>
          <div>
            <strong>Access note</strong>
            <span>{{ project.access_note || "Not configured" }}</span>
          </div>
        </div>
        <div class="link-cloud">
          <el-link v-for="link in project.links" :key="link.id" :href="link.url" target="_blank" type="primary">
            {{ link.title }}
          </el-link>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="card-header">
            <span>Runbook</span>
            <el-tag type="warning" effect="plain">Control</el-tag>
          </div>
        </template>
        <div class="detail-list">
          <div>
            <strong>Start note</strong>
            <span>{{ project.start_note || "Not configured" }}</span>
          </div>
          <div>
            <strong>Stop note</strong>
            <span>{{ project.stop_note || "Not configured" }}</span>
          </div>
          <div>
            <strong>Kuma monitor</strong>
            <span>{{ project.kuma_monitor_id || "Not bound" }}</span>
          </div>
          <div>
            <strong>Runtime service</strong>
            <span>{{ project.runtime_service_name || "Not set" }}</span>
          </div>
          <div>
            <strong>Start command</strong>
            <span>{{ project.start_cmd || "Not configured" }}</span>
          </div>
          <div>
            <strong>Stop command</strong>
            <span>{{ project.stop_cmd || "Not configured" }}</span>
          </div>
          <div>
            <strong>Restart command</strong>
            <span>{{ project.restart_cmd || "Not configured" }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <span>Recent actions</span>
          <el-tag type="success" effect="plain">{{ logs.length }} items</el-tag>
        </div>
      </template>
      <el-table :data="logs" row-key="id">
        <el-table-column prop="created_at" label="Time" min-width="180" />
        <el-table-column prop="action" label="Action" width="120" />
        <el-table-column prop="status" label="Status" width="120" />
        <el-table-column prop="username" label="Actor" width="120" />
        <el-table-column prop="external_execution_id" label="Execution ID" width="180" />
        <el-table-column prop="message" label="Message" min-width="240" />
      </el-table>
    </el-card>
  </div>

  <ProjectFormDrawer
    v-model="showForm"
    :project="project"
    :servers="servers"
    @saved="loadData"
  />
</template>
