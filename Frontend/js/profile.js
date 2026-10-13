/* profile.js — User account management, password updates, and session revocation */

import { Api } from './api.js';
import { showToast } from './utils.js';

export async function fetchCurrentProfile() {
  const data = await Api.getProfile();
  return data.user;
}

export async function updateCurrentProfile(payload) {
  const res = await Api.updateProfile(payload);
  showToast('Profile updated successfully!', 'success');
  return res;
}

export async function updatePassword(currentPassword, newPassword) {
  const res = await Api.changePassword({
    current_password: currentPassword,
    new_password: newPassword
  });
  showToast('Password changed successfully!', 'success');
  return res;
}

export async function fetchActiveSessions() {
  const data = await Api.getUserSessions();
  return data.sessions || [];
}

export async function revokeActiveSession(sessionId) {
  const res = await Api.revokeUserSession(sessionId);
  showToast('Session revoked successfully.', 'success');
  return res;
}
