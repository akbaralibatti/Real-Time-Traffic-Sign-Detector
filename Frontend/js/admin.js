/* admin.js — Admin dashboard analytics, user moderation, and audit helpers */

import { Api } from './api.js';
import { showToast } from './utils.js';

export async function fetchAdminStats() {
  return await Api.getAdminDashboard();
}

export async function fetchUsersList(params = {}) {
  return await Api.getUsers(params);
}

export async function updateUserRole(userId, role) {
  const res = await Api.updateUser(userId, { role });
  showToast(`User role updated to ${role}.`, 'success');
  return res;
}

export async function unlockUserAccount(userId) {
  const res = await Api.unlockUser(userId);
  showToast('Account successfully unlocked.', 'success');
  return res;
}

export async function revokeAllSessionsForUser(userId) {
  const res = await Api.revokeUserSessions(userId);
  showToast('All sessions for user have been revoked.', 'success');
  return res;
}

export async function deleteUserAccount(userId) {
  const res = await Api.deleteUser(userId);
  showToast('User deleted successfully.', 'success');
  return res;
}

export async function fetchAuditLogs(filters = {}) {
  return await Api.getLogs(filters);
}
