import { createRouter, createWebHistory } from "vue-router";

import { sessionState } from "../lib/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { public: true, title: "Sign In" },
    },
    {
      path: "/",
      redirect: "/dashboard",
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("../views/DashboardView.vue"),
      meta: { title: "Dashboard" },
    },
    {
      path: "/services/:id",
      name: "service-detail",
      component: () => import("../views/ProjectDetailView.vue"),
      props: true,
      meta: { title: "Service Detail" },
    },
    {
      path: "/projects/:id",
      redirect: (to) => `/services/${to.params.id}`,
    },
    {
      path: "/servers",
      name: "servers",
      component: () => import("../views/ServersView.vue"),
      meta: { title: "Servers" },
    },
    {
      path: "/ssh-keys",
      name: "ssh-keys",
      component: () => import("../views/SshKeysView.vue"),
      meta: { title: "SSH Keys" },
    },
    {
      path: "/logs",
      name: "logs",
      component: () => import("../views/LogsView.vue"),
      meta: { title: "Logs" },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
      meta: { title: "Settings" },
    },
  ],
});

router.beforeEach((to) => {
  if (to.meta.public) {
    return true;
  }
  if (!sessionState.token) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  return true;
});

export default router;
