const rawApiBaseUrl = typeof import.meta.env.VITE_API_BASE_URL === "string"
  ? import.meta.env.VITE_API_BASE_URL.trim()
  : "";
const API_BASE = rawApiBaseUrl === "/" ? "" : rawApiBaseUrl.replace(/\/+$/, "");

export async function login(username, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "فشل تسجيل الدخول");
  }
  const data = await response.json();
  localStorage.setItem("market_ai_token", data.access_token);
  localStorage.setItem("market_ai_user", JSON.stringify({
    username: data.username,
    role: data.role,
  }));
  return data;
}

export async function checkAuthStatus() {
  const response = await fetch(`${API_BASE}/auth/status`);
  if (!response.ok) return { auth_enabled: false };
  return response.json();
}

export function logout() {
  localStorage.removeItem("market_ai_token");
  localStorage.removeItem("market_ai_user");
  window.location.href = "/";
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem("market_ai_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isAuthenticated() {  return !!localStorage.getItem("market_ai_token");}
