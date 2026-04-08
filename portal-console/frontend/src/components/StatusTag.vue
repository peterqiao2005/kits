<script setup lang="ts">
import { computed } from "vue";

import type { ProjectStatus } from "../types";

const props = defineProps<{
  status: ProjectStatus;
}>();

const tagType = computed(() => {
  if (props.status === "online") return "success";
  if (props.status === "offline") return "danger";
  if (props.status === "degraded") return "warning";
  return "info";
});

const label = computed(() => {
  if (props.status === "online") return "Online";
  if (props.status === "offline") return "Offline";
  if (props.status === "degraded") return "Degraded";
  return "Unknown";
});
</script>

<template>
  <el-tag :type="tagType" effect="dark" round>
    {{ label }}
  </el-tag>
</template>
