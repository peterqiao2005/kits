import axios from "axios";

import { clearSession, sessionState } from "../lib/session";

const apiClient = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

apiClient.interceptors.request.use((config) => {
  if (sessionState.token) {
    config.headers.Authorization = `Bearer ${sessionState.token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearSession();
    }
    return Promise.reject(error);
  },
);

export default apiClient;
