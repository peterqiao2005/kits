<script setup lang="ts">
import { Loading } from "@element-plus/icons-vue";

defineProps<{
  canStart: boolean;
  canStop: boolean;
  canRestart: boolean;
  loadingAction?: string;
}>();

const emit = defineEmits<{
  action: [action: "start" | "stop" | "restart"];
}>();
</script>

<template>
  <div class="action-row">
    <el-button
      type="success"
      plain
      size="small"
      :disabled="!canStart"
      :loading="loadingAction === 'start'"
      @click="emit('action', 'start')"
    >
      <el-icon v-if="loadingAction === 'start'"><Loading /></el-icon>
      Start
    </el-button>
    <el-button
      type="warning"
      plain
      size="small"
      :disabled="!canStop"
      :loading="loadingAction === 'stop'"
      @click="emit('action', 'stop')"
    >
      Stop
    </el-button>
    <el-button
      type="primary"
      plain
      size="small"
      :disabled="!canRestart"
      :loading="loadingAction === 'restart'"
      @click="emit('action', 'restart')"
    >
      Restart
    </el-button>
  </div>
</template>
