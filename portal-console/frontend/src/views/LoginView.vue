<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { getMe, login } from "../api/modules";
import { sessionState, setToken } from "../lib/session";

const route = useRoute();
const router = useRouter();

const form = ref({
  username: "admin",
  password: "admin123",
});
const loading = ref(false);

async function submit() {
  loading.value = true;
  try {
    const token = await login(form.value.username, form.value.password);
    setToken(token.access_token);
    sessionState.user = await getMe();
    router.push(String(route.query.redirect || "/dashboard"));
  } catch {
    ElMessage.error("Sign in failed. Check credentials or backend setup.");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-hero">
      <p class="page-kicker">Personal Infra Control</p>
      <h1>Bring projects, servers, health, and actions into one panel.</h1>
      <p>
        The portal stays focused on navigation and control. Rundeck owns remote execution, and
        Uptime Kuma remains the preferred health source.
      </p>
    </div>
    <el-card class="login-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>Sign in</span>
          <el-tag type="warning" effect="plain">Bootstrap admin</el-tag>
        </div>
      </template>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="Username">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-button type="primary" class="full-width" :loading="loading" @click="submit">
          Enter console
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>
