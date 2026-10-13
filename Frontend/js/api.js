/* api.js — Centralized API fetch wrapper and endpoints config */

import { Auth } from './utils.js';

export const API_BASE = "http://127.0.0.1:5000/api";

/**
 * Standard fetch helper with Authorization header and automatic JSON serialization.
 */
export async function request(endpoint, options = {}) {
  const token = Auth.getToken();
  const headers = { ...(options.headers || {}) };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    body: options.body instanceof FormData ? options.body : (options.body ? JSON.stringify(options.body) : undefined),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw { status: res.status, message: data.error || data.message || "Request failed", data };
  }
  return data;
}

export const Api = {
  // Auth
  login: (creds) => request('/auth/login', { method: 'POST', body: creds }),
  register: (user) => request('/auth/register', { method: 'POST', body: user }),
  verifyOtp: (payload) => request('/auth/verify-otp', { method: 'POST', body: payload }),
  setup2FA: () => request('/auth/setup-2fa', { method: 'POST' }),
  confirm2FA: (token) => request('/auth/confirm-2fa', { method: 'POST', body: { token } }),
  logout: () => request('/auth/logout', { method: 'POST' }),

  // Detection
  startSession: (session_type) => request('/detection/start-session', { method: 'POST', body: { session_type } }),
  endSession: (id, payload) => request(`/detection/end-session/${id}`, { method: 'POST', body: payload }),
  sendFrame: (payload) => request('/detection/frame', { method: 'POST', body: payload }),
  uploadVideo: (formData) => request('/detection/upload', { method: 'POST', body: formData }),
  getSessions: () => request('/detection/sessions'),
  getSessionResults: (id) => request(`/detection/results/${id}`),

  // Signs
  getSigns: () => request('/signs'),
  getSign: (id) => request(`/signs/${id}`),

  // User
  getProfile: () => request('/user/profile'),
  updateProfile: (data) => request('/user/profile', { method: 'PATCH', body: data }),
  changePassword: (data) => request('/user/change-password', { method: 'POST', body: data }),
  getUserSessions: () => request('/user/sessions'),
  revokeUserSession: (id) => request(`/user/sessions/${id}`, { method: 'DELETE' }),

  // Admin
  getAdminDashboard: () => request('/admin/dashboard'),
  getUsers: (params) => request(`/admin/users?${new URLSearchParams(params || {})}`),
  updateUser: (id, data) => request(`/admin/users/${id}`, { method: 'PATCH', body: data }),
  deleteUser: (id) => request(`/admin/users/${id}`, { method: 'DELETE' }),
  unlockUser: (id) => request(`/admin/users/${id}/unlock`, { method: 'POST' }),
  revokeUserSessions: (id) => request(`/admin/users/${id}/revoke-sessions`, { method: 'POST' }),
  getLogs: (params) => request(`/admin/logs?${new URLSearchParams(params || {})}`),
};
