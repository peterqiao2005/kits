<script setup lang="ts">
import { computed, onMounted } from "vue";
import { Key, Monitor, Setting, Tickets, UserFilled } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { getMe } from "./api/modules";
import { clearSession, sessionState } from "./lib/session";

const route = useRoute();
const router = useRouter();

const isPublicRoute = computed(() => route.meta.public === true);
const pageTitle = computed(() => (route.meta.title as string) || String(route.name || ""));

const menuItems = [
  { index: "/dashboard", label: "Dashboard", icon: Monitor },
  { index: "/servers", label: "Servers", icon: Tickets },
  { index: "/ssh-keys", label: "SSH Keys", icon: Key },
  { index: "/logs", label: "Logs", icon: UserFilled },
  { index: "/settings", label: "Settings", icon: Setting },
];

async function bootstrapUser() {
  if (!sessionState.token) return;
  try {
    sessionState.user = await getMe();
  } catch {
    clearSession();
    router.push("/login");
  }
}

function logout() {
  clearSession();
  router.push("/login");
}

onMounted(bootstrapUser);
</script>

<template>
  <router-view v-if="isPublicRoute" />
  <el-container v-else class="shell">
    <el-aside width="260px" class="shell-sidebar">
      <div class="brand-block">
        <p class="brand-kicker">Control Layer</p>
        <h1>Portal Console</h1>
        <p>A personal control surface for service links, SSH access, health, and actions.</p>
      </div>
      <el-menu :default-active="route.path" router class="shell-menu">
        <el-menu-item v-for="item in menuItems" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
      <div class="shell-user">
        <div>
          <strong>{{ sessionState.user?.username ?? "Guest" }}</strong>
          <p>{{ sessionState.user?.role ?? "viewer" }}</p>
        </div>
        <el-button text @click="logout">Sign out</el-button>
      </div>
    </el-aside>
    <el-container>
      <el-header class="shell-header">
        <div>
          <p class="page-kicker">Service Portal</p>
          <h2>{{ pageTitle }}</h2>
        </div>
        <el-tag type="info" effect="plain">FastAPI + Vue 3</el-tag>
      </el-header>
      <el-main class="shell-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
