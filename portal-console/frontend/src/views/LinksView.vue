<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Link, Search, Star, StarFilled } from "@element-plus/icons-vue";

import { getProjects } from "../api/modules";
import type { Project, ProjectLink } from "../types";

const projects = ref<Project[]>([]);
const loading = ref(false);

const searchKeyword = ref("");
const selectedTag = ref("");
const selectedProjectId = ref<number | null>(null);
const favoriteOnly = ref(false);

async function loadData() {
  loading.value = true;
  try {
    projects.value = await getProjects();
  } catch {
    ElMessage.error("Failed to load service links.");
  } finally {
    loading.value = false;
  }
}

// Extract all unique project tags for filtering
const allTags = computed(() => {
  const tagsSet = new Set<string>();
  projects.value.forEach((p) => {
    p.tags?.forEach((t) => tagsSet.add(t));
  });
  return Array.from(tagsSet).sort();
});

// Flat list of links decorated with project/server metadata
interface LinkItem extends ProjectLink {
  projectName: string;
  projectDescription?: string | null;
  serverName: string;
  serverHost: string;
  isFavorite: boolean;
  projectTags: string[];
}

const allLinks = computed<LinkItem[]>(() => {
  const items: LinkItem[] = [];
  projects.value.forEach((p) => {
    p.links.forEach((l) => {
      items.push({
        ...l,
        projectName: p.name,
        projectDescription: p.description,
        serverName: p.server.name,
        serverHost: p.server.host,
        isFavorite: p.is_favorite,
        projectTags: p.tags || [],
      });
    });
  });
  // Sort links by project name then link sort_order
  return items.sort((a, b) => {
    if (a.projectName !== b.projectName) {
      return a.projectName.localeCompare(b.projectName);
    }
    return a.sort_order - b.sort_order;
  });
});

const filteredLinks = computed(() => {
  return allLinks.value.filter((link) => {
    // 1. Search keyword
    if (searchKeyword.value.trim()) {
      const kw = searchKeyword.value.toLowerCase();
      const matchProjectName = link.projectName.toLowerCase().includes(kw);
      const matchTitle = link.title.toLowerCase().includes(kw);
      const matchUrl = link.url.toLowerCase().includes(kw);
      const matchDesc = link.projectDescription?.toLowerCase().includes(kw) || false;
      if (!matchProjectName && !matchTitle && !matchUrl && !matchDesc) {
        return false;
      }
    }
    // 2. Tag filter
    if (selectedTag.value && !link.projectTags.includes(selectedTag.value)) {
      return false;
    }
    // 3. Project filter
    if (selectedProjectId.value !== null && link.project_id !== selectedProjectId.value) {
      return false;
    }
    // 4. Favorites filter
    if (favoriteOnly.value && !link.isFavorite) {
      return false;
    }
    return true;
  });
});

function getLinkTypeType(type: string): "success" | "warning" | "info" | "primary" | "danger" {
  switch (type) {
    case "web":
      return "success";
    case "admin":
      return "danger";
    case "docs":
      return "info";
    case "github":
      return "warning";
    case "monitor":
      return "primary";
    default:
      return "info";
  }
}

onMounted(loadData);
</script>

<template>
  <div class="page-grid">
    <el-card shadow="never" class="panel-card">
      <div class="toolbar-row">
        <el-input
          v-model="searchKeyword"
          placeholder="Search by title, url, or service..."
          :prefix-icon="Search"
          clearable
        />
        <el-select v-model="selectedTag" placeholder="Filter by Tag" clearable>
          <el-option v-for="tag in allTags" :key="tag" :label="tag" :value="tag" />
        </el-select>
        <el-select v-model="selectedProjectId" placeholder="Filter by Service" clearable>
          <el-option
            v-for="p in projects"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
        <div class="fav-toggle-wrapper">
          <el-checkbox-button v-model="favoriteOnly" class="fav-checkbox-btn">
            <el-icon style="margin-right: 4px; vertical-align: middle;">
              <StarFilled v-if="favoriteOnly" style="color: var(--brand);" />
              <Star v-else />
            </el-icon>
            Favorites Only
          </el-checkbox-button>
        </div>
      </div>
    </el-card>

    <div v-loading="loading">
      <el-empty v-if="filteredLinks.length === 0" description="No entry links found matching your filters." />
      <div v-else class="link-card-grid">
        <div
          v-for="link in filteredLinks"
          :key="link.id"
          class="link-card-item panel-card"
        >
          <div class="link-card-header">
            <el-tag :type="getLinkTypeType(link.link_type)" size="small" effect="dark" round>
              {{ link.link_type.toUpperCase() }}
            </el-tag>
            <el-icon v-if="link.isFavorite" class="fav-star-icon">
              <StarFilled style="color: var(--brand);" />
            </el-icon>
          </div>

          <h4 class="link-title">{{ link.title }}</h4>
          
          <router-link :to="`/services/${link.project_id}`" class="link-project-meta">
            Service: <strong>{{ link.projectName }}</strong>
          </router-link>
          
          <div class="link-server-meta">
            Host: <span>{{ link.serverName }} ({{ link.serverHost }})</span>
          </div>

          <div class="link-tags-row">
            <el-tag
              v-for="tag in link.projectTags"
              :key="tag"
              size="small"
              type="info"
              effect="plain"
              round
            >
              {{ tag }}
            </el-tag>
          </div>

          <div class="link-action-footer">
            <el-button
              type="primary"
              :icon="Link"
              size="small"
              class="visit-btn"
              tag="a"
              :href="link.url"
              target="_blank"
            >
              Visit URL
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fav-toggle-wrapper {
  display: flex;
  align-items: center;
}

.fav-checkbox-btn :deep(.el-checkbox-button__inner) {
  border-radius: 12px !important;
  border: 1px solid var(--line) !important;
  background-color: var(--panel) !important;
  color: var(--text) !important;
  box-shadow: none !important;
  height: 40px;
  line-height: 20px;
}

.fav-checkbox-btn.is-checked :deep(.el-checkbox-button__inner) {
  border-color: var(--brand) !important;
  background-color: rgba(191, 95, 47, 0.08) !important;
  color: var(--brand) !important;
}

.link-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.link-card-item {
  display: flex;
  flex-direction: column;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  position: relative;
  overflow: hidden;
}

.link-card-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(58, 67, 58, 0.15);
  border-color: rgba(191, 95, 47, 0.3);
}

.link-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.fav-star-icon {
  font-size: 18px;
}

.link-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--text);
}

.link-project-meta {
  font-size: 13px;
  color: var(--muted);
  text-decoration: none;
  margin-bottom: 4px;
}

.link-project-meta:hover {
  color: var(--brand);
  text-decoration: underline;
}

.link-server-meta {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}

.link-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 16px;
}

.link-action-footer {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}

.visit-btn {
  width: 100%;
  border-radius: 10px;
  background-color: var(--brand) !important;
  border-color: var(--brand) !important;
  font-weight: bold;
}

.visit-btn:hover {
  background-color: var(--brand-deep) !important;
  border-color: var(--brand-deep) !important;
}
</style>
