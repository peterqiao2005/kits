import { reactive } from "vue";

import type { User } from "../types";

const TOKEN_KEY = "portal-console-token";

export const sessionState = reactive<{
  token: string;
  user: User | null;
}>({
  token: localStorage.getItem(TOKEN_KEY) ?? "",
  user: null,
});

export function setToken(token: string) {
  sessionState.token = token;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearSession() {
  sessionState.token = "";
  sessionState.user = null;
  localStorage.removeItem(TOKEN_KEY);
}
