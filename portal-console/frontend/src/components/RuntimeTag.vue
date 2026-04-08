<script setup lang="ts">
import { computed } from "vue";

import type { RuntimeStatus } from "../types";

const props = defineProps<{
  status: RuntimeStatus;
}>();

const tagType = computed(() => {
  if (props.status === "active") return "success";
  if (props.status === "stopped") return "danger";
  return "info";
});

const label = computed(() => {
  if (props.status === "active") return "Active";
  if (props.status === "stopped") return "Stopped";
  return "Unknown";
});
</script>

<template>
  <el-tag :type="tagType" effect="plain" round>
    {{ label }}
  </el-tag>
</template>
