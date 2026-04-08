<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Link } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

import { getProjects, getServers, runAction, syncProjectStatus } from "../api/modules";
import ActionButtons from "../components/ActionButtons.vue";
import ProjectFormDrawer from "../components/ProjectFormDrawer.vue";
import RuntimeTag from "../components/RuntimeTag.vue";
import StatusTag from "../components/StatusTag.vue";
import { sessionState } from "../lib/session";
import type { Project, ProjectStatus, Server } from "../types";

const router = useRouter();
const loading = ref(false);
const syncing = ref(false);
const loadingActionByProject = ref<Record<number, string>>({});
const projects = ref<Project[]>([]);
const servers = ref<Server[]>([]);
const showForm = ref(false);
const editingProject = ref<Project | null>(null);

const filters = ref({
  search: "",
  status: "" as ProjectStatus | "",
  serverId: "" as number | "",
  favoriteOnly: false,
});

const filteredProjects = computed(() =>
  projects.value.filter((project) => {
    if (filters.value.search) {
      const keyword = filters.value.search.toLowerCase();
      const haystack = `${project.name} ${project.description ?? ""} ${project.tags.join(" ")}`.toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    if (filters.value.status && project.http_status !== filters.value.status) return false;
    if (filters.value.serverId && project.server_id !== filters.value.serverId) return false;
    if (filters.value.favoriteOnly && !project.is_favorite) return false;
    return true;
  }),
);

const stats = computed(() => ({
  total: projects.value.length,
  online: projects.value.filter((item) => item.http_status === "online").length,
  offline: projects.value.filter((item) => item.http_status === "offline").length,
  actionable: projects.value.filter((item) => item.can_start || item.can_stop || item.can_restart).length,
}));

const canOperate = computed(() => sessionState.user?.role === "admin");

function openCreate() {
  editingProject.value = null;
  showForm.value = true;
}

async function handleSaved() {
  await loadData();
}

async function loadData() {
  loading.value = true;
  try {
    const [projectData, serverData] = await Promise.all([getProjects(), getServers()]);
    projects.value = projectData;
    servers.value = serverData;
  } catch {
    ElMessage.error("Failed to load services.");
  } finally {
    loading.value = false;
  }
}

async function syncStatuses() {
  syncing.value = true;
  try {
    await syncProjectStatus(projects.value.map((item) => item.id));
    await loadData();
    ElMessage.success("Status sync completed.");
  } catch {
    ElMessage.warning("Status sync failed. Cached state is still shown.");
  } finally {
    syncing.value = false;
  }
}

async function onAction(project: Project, action: "start" | "stop" | "restart") {
  loadingActionByProject.value[project.id] = action;
  try {
    const result = await runAction(project.id, action);
    if (result.status === "succeeded") {
      ElMessage.success(`Service ${project.name} ${action} succeeded.`);
      await loadData();
    } else {
      ElMessage.error(result.message || `Service ${project.name} ${action} failed.`);
    }
  } catch {
    ElMessage.error(`Service ${project.name} ${action} failed.`);
  } finally {
    delete loadingActionByProject.value[project.id];
  }
}

onMounted(loadData);
</script>

<template>
  <section class="page-grid">
    <div class="metrics-row">
      <el-card shadow="never" class="metric-card">
        <p>Total services</p>
        <strong>{{ stats.total }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <p>Online</p>
        <strong>{{ stats.online }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <p>Offline</p>
        <strong>{{ stats.offline }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <p>Actionable</p>
        <strong>{{ stats.actionable }}</strong>
      </el-card>
    </div>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="card-header">
          <div>
            <p class="page-kicker">Dashboard</p>
            <h3>Service overview</h3>
          </div>
          <div class="action-row">
            <el-button type="primary" :loading="syncing" @click="syncStatuses">Sync status</el-button>
            <el-button v-if="canOperate" type="success" @click="openCreate">New service</el-button>
          </div>
        </div>
      </template>

      <div class="toolbar-row">
        <el-input v-model="filters.search" placeholder="Search service name, description, or tag" clearable />
        <el-select v-model="filters.status" placeholder="All statuses" clearable>
          <el-option label="Online" value="online" />
          <el-option label="Offline" value="offline" />
          <el-option label="Degraded" value="degraded" />
          <el-option label="Unknown" value="unknown" />
        </el-select>
        <el-select v-model="filters.serverId" placeholder="All servers" clearable>
          <el-option v-for="server in servers" :key="server.id" :label="server.name" :value="server.id" />
        </el-select>
        <el-switch v-model="filters.favoriteOnly" active-text="Favorites only" />
      </div>

      <el-table :data="filteredProjects" v-loading="loading" row-key="id" class="dashboard-table">
        <el-table-column label="Service" min-width="260">
          <template #default="{ row }">
            <div class="project-title" @click="router.push(`/services/${row.id}`)">
              <strong>{{ row.name }}</strong>
              <p>{{ row.description || "No description" }}</p>
              <div class="tag-row">
                <el-tag v-for="tag in row.tags" :key="tag" effect="plain" round>{{ tag }}</el-tag>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="HTTP" width="120">
          <template #default="{ row }">
            <StatusTag :status="row.http_status" />
          </template>
        </el-table-column>
        <el-table-column label="Runtime" width="120">
          <template #default="{ row }">
            <RuntimeTag :status="row.runtime_status" />
          </template>
        </el-table-column>
        <el-table-column label="Server" width="180">
          <template #default="{ row }">
            <strong>{{ row.server.name }}</strong>
            <p>{{ row.server.ssh_username || "?" }}@{{ row.server.host }}:{{ row.server.ssh_port }}</p>
          </template>
        </el-table-column>
        <el-table-column label="Links" min-width="260">
          <template #default="{ row }">
            <div class="link-grid">
              <el-link v-for="link in row.links.slice(0, 4)" :key="link.id" :href="link.url" target="_blank" type="primary">
                <el-icon><Link /></el-icon>
                {{ link.title }}
              </el-link>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="260">
          <template #default="{ row }">
            <div class="table-actions">
              <ActionButtons
                :can-start="row.can_start && canOperate"
                :can-stop="row.can_stop && canOperate"
                :can-restart="row.can_restart && canOperate"
                :loading-action="loadingActionByProject[row.id]"
                @action="onAction(row, $event)"
              />
              <div class="action-row">
                <el-button link type="primary" @click="router.push(`/services/${row.id}`)">Details</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>

  <ProjectFormDrawer
    v-model="showForm"
    :project="editingProject"
    :servers="servers"
    @saved="handleSaved"
  />
</template>
