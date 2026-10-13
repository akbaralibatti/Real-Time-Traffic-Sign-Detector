/* history.js — Session history fetching and result breakdown helpers */

import { Api } from './api.js';

export async function fetchUserSessions() {
  const data = await Api.getSessions();
  return data.sessions || [];
}

export async function fetchSessionResults(sessionId) {
  const data = await Api.getSessionResults(sessionId);
  return data.detections || [];
}

export function filterSessionsByType(sessions, type) {
  if (!type || type === 'all') return sessions;
  return sessions.filter(s => s.session_type === type);
}
