<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import { deleteServer, getProjects, getServers, getSshKeys } from "../api/modules";
import ServerFormDrawer from "../components/ServerFormDrawer.vue";
import { sessionState } from "../lib/session";
import type { Project, Server, SSHKey } from "../types";

const router = useRouter();
const loading = ref(false);
const servers = ref<Server[]>([]);
const projects = ref<Project[]>([]);
const sshKeys = ref<SSHKey[]>([]);
const showForm = ref(false);
const editingServer = ref<Server | null>(null);

const canOperate = computed(() => sessionState.user?.role === "admin");

const serverCards = computed(() =>
  servers.value.map((server) => {
    const related = projects.value.filter((project) => project.server_id === server.id);
    return {
      ...server,
      online: related.filter((project) => project.http_status === "online").length,
      offline: related.filter((project) => project.http_status === "offline").length,
      services: related,
    };
  }),
);

async function loadData() {
  loading.value = true;
  try {
    const [serverData, projectData, sshKeyData] = await Promise.all([
      getServers(),
      getProjects(),
      getSshKeys().catch(() => []),
    ]);
    servers.value = serverData;
    projects.value = projectData;
    sshKeys.value = sshKeyData;
  } catch {
    ElMessage.error("Failed to load servers.");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingServer.value = null;
  showForm.value = true;
}

function openEdit(server: Server) {
  editingServer.value = server;
  showForm.value = true;
}

async function removeServer(server: Server) {
  try {
    await ElMessageBox.confirm(`Delete server "${server.name}"?`, "Delete Server", {
      type: "warning",
    });
    await deleteServer(server.id);
    ElMessage.success("Server deleted.");
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("Failed to delete server.");
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
            <p class="page-kicker">SSH Endpoints</p>
            <h3>Server inventory</h3>
          </div>
          <el-button v-if="canOperate" type="success" @click="openCreate">New server</el-button>
        </div>
      </template>
      <p class="muted-line">
        Each server stores the SSH endpoint used for service checks and remote control commands.
      </p>
    </el-card>

    <section class="server-grid" v-loading="loading">
      <el-card v-for="server in serverCards" :key="server.id" shadow="never" class="panel-card server-card">
        <template #header>
          <div class="card-header">
            <div>
              <h3>{{ server.name }}</h3>
              <p>{{ server.ssh_username || "?" }}@{{ server.host }}:{{ server.ssh_port }}</p>
            </div>
            <div class="action-row">
              <el-tag type="info" effect="plain">{{ server.env_type }}</el-tag>
              <el-button v-if="canOperate" link type="primary" @click="openEdit(server)">Edit</el-button>
              <el-button v-if="canOperate" link type="danger" @click="removeServer(server)">Delete</el-button>
            </div>
          </div>
        </template>
        <div class="server-stats">
          <div>
            <strong>{{ server.project_count }}</strong>
            <span>Services</span>
          </div>
          <div>
            <strong>{{ server.online }}</strong>
            <span>Online</span>
          </div>
          <div>
            <strong>{{ server.offline }}</strong>
            <span>Offline</span>
          </div>
        </div>
        <div class="detail-list compact-list">
          <div>
            <strong>Authentication</strong>
            <span>{{ server.ssh_auth_type === "password" ? "Password" : "SSH key" }}</span>
          </div>
          <div>
            <strong>Credential</strong>
            <span>
              {{
                server.ssh_auth_type === "password"
                  ? (server.has_ssh_password ? "Stored password" : "Password missing")
                  : (server.ssh_key?.name || "SSH key missing")
              }}
            </span>
          </div>
          <div>
            <strong>Description</strong>
            <span>{{ server.description || "No note" }}</span>
          </div>
        </div>
        <div class="tag-row">
          <el-tag v-for="tag in server.tags" :key="tag" effect="plain" round>{{ tag }}</el-tag>
        </div>
        <div class="server-projects">
          <el-link
            v-for="service in server.services"
            :key="service.id"
            href="#"
            @click.prevent="router.push(`/services/${service.id}`)"
          >
            {{ service.name }}
          </el-link>
        </div>
      </el-card>
    </section>
  </section>

  <ServerFormDrawer
    v-model="showForm"
    :server="editingServer"
    :ssh-keys="sshKeys"
    @saved="loadData"
  />
</template>
