import { apiFetch } from "../http.js";

// Each returns {user: {id, username, groups} | null}, except logout.
export const getMe = () => apiFetch("/api/auth/me/");

export const register = (username, password) =>
  apiFetch("/api/auth/register/", { method: "POST", body: { username, password } });

export const login = (username, password) =>
  apiFetch("/api/auth/login/", { method: "POST", body: { username, password } });

export const logout = () => apiFetch("/api/auth/logout/", { method: "POST" });
