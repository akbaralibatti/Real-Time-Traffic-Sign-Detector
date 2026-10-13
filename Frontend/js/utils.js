/* utils.js — Shared utilities: token storage, toasts, helpers */

const API_BASE = (window.TRAFFICVISION_API_BASE || "http://127.0.0.1:5000/api").replace(/\/$/, "");

// ── Token storage ────────────────────────────────────────────────────────────
export const Auth = {
  setToken: (t)    => sessionStorage.setItem("tvision_token", t),
  getToken: ()     => sessionStorage.getItem("tvision_token"),
  removeToken: ()  => sessionStorage.removeItem("tvision_token"),
  setUser:  (u)    => sessionStorage.setItem("tvision_user", JSON.stringify(u)),
  getUser:  ()     => { try { return JSON.parse(sessionStorage.getItem("tvision_user")); } catch { return null; } },
  removeUser: ()   => sessionStorage.removeItem("tvision_user"),
  isLoggedIn: ()   => !!sessionStorage.getItem("tvision_token"),
  isAdmin:    ()   => { const u = Auth.getUser(); return u && u.role === "admin"; },
  clear:      ()   => { Auth.removeToken(); Auth.removeUser(); sessionStorage.removeItem("tvision_challenge_token"); sessionStorage.removeItem("tvision_pending_uid"); },
};

// ── API fetch wrapper ────────────────────────────────────────────────────────
export async function apiFetch(path, options = {}) {
  const token = Auth.getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body instanceof FormData ? options.body : (options.body ? JSON.stringify(options.body) : undefined),
  });

  // Remove Content-Type for FormData
  if (options.body instanceof FormData) delete headers["Content-Type"];

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw { status: res.status, message: data.error || "Request failed", data };
  return data;
}

// ── Toast notifications ───────────────────────────────────────────────────────
function ensureContainer() {
  let c = document.getElementById("toast-container");
  if (!c) { c = document.createElement("div"); c.id = "toast-container"; document.body.appendChild(c); }
  return c;
}

export function showToast(msg, type = "info", duration = 3500) {
  const icons = { success: "✓", error: "✕", info: "ℹ", warning: "⚠" };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span style="font-size:1rem;font-weight:700">${icons[type]||"•"}</span><span>${msg}</span>`;
  ensureContainer().prepend(toast);
  setTimeout(() => { toast.style.opacity="0"; toast.style.transform="translateX(30px)";
    setTimeout(() => toast.remove(), 300); }, duration);
}

// ── Auth guards ───────────────────────────────────────────────────────────────
export function requireLogin() {
  if (!Auth.isLoggedIn()) { window.location.href = "/index.html"; return false; }
  return true;
}
export function requireAdmin() {
  if (!requireLogin()) return false;
  if (!Auth.isAdmin()) { window.location.href = "/dashboard.html"; return false; }
  return true;
}
export function redirectIfLoggedIn() {
  if (Auth.isLoggedIn()) window.location.href = "/dashboard.html";
}

// ── Misc helpers ──────────────────────────────────────────────────────────────
// Format database timestamps in Indian Standard Time (IST).
export function formatDate(d) {
  if (!d) return "—";

  let value = String(d).trim();

  // MySQL DATETIME values may arrive without a timezone suffix.
  // Treat those values as UTC, as indicated by the current log offset.
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)) {
    value = value.replace(" ", "T") + "Z";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "Invalid date";

  return date.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true
  });
}

export function formatConfidence(c) {
  return `${(c * 100).toFixed(1)}%`;
}

export function initAvatarInitials(el, name) {
  if (!el || !name) return;
  el.textContent = name.slice(0, 2).toUpperCase();
}

// ── Set up sidebar active link ────────────────────────────────────────────────
export function highlightNav() {
  const path = window.location.pathname.split("/").pop();
  document.querySelectorAll(".nav-item").forEach(a => {
    if (a.getAttribute("href") === path) a.classList.add("active");
  });
}

// ── Populate sidebar user info ────────────────────────────────────────────────
export function populateSidebarUser() {
  const user = Auth.getUser();
  if (!user) return;
  const el = document.getElementById("sidebar-username");
  const av = document.getElementById("sidebar-avatar");
  if (el) el.textContent = user.username;
  if (av) initAvatarInitials(av, user.username);
}
