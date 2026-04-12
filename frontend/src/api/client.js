const rawApiBaseUrl = typeof import.meta.env.VITE_API_BASE_URL === "string"
  ? import.meta.env.VITE_API_BASE_URL.trim()
  : "";
const API_BASE_URL = rawApiBaseUrl === "/" ? "" : rawApiBaseUrl.replace(/\/+$/, "");
const RESPONSE_CACHE = new Map();
const INFLIGHT_REQUESTS = new Map();
const MAX_CACHE_ENTRIES = 250;

export function getApiBaseUrl() {
  if (API_BASE_URL) {
    return API_BASE_URL;
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "same-origin";
}

function requestCacheKey(path, method = "GET") {
  return `${String(method || "GET").toUpperCase()}:${path}`;
}

function readCache(cacheKey) {
  const cached = RESPONSE_CACHE.get(cacheKey);
  if (!cached) {
    return null;
  }
  if (cached.expiresAt <= Date.now()) {
    RESPONSE_CACHE.delete(cacheKey);
    return null;
  }
  return cached.value;
}

function pruneCache() {
  const now = Date.now();
  for (const [key, entry] of RESPONSE_CACHE.entries()) {
    if (!entry || entry.expiresAt <= now) {
      RESPONSE_CACHE.delete(key);
    }
  }
  while (RESPONSE_CACHE.size > MAX_CACHE_ENTRIES) {
    const oldestKey = RESPONSE_CACHE.keys().next().value;
    if (!oldestKey) {
      break;
    }
    RESPONSE_CACHE.delete(oldestKey);
  }
}

async function requestJson(path, options = {}) {
  const {
    method = "GET",
    payload,
    cacheTtlMs = 0,
    forceFresh = false,
    signal,
  } = options;
  const normalizedMethod = String(method || "GET").toUpperCase();
  const cacheKey = requestCacheKey(path, normalizedMethod);
  pruneCache();
  if (normalizedMethod === "GET" && !forceFresh && cacheTtlMs > 0) {
    const cached = readCache(cacheKey);
    if (cached !== null) {
      return cached;
    }
  }

  const canUseInflight = normalizedMethod === "GET" && !forceFresh && !signal;
  if (canUseInflight && INFLIGHT_REQUESTS.has(cacheKey)) {
    return INFLIGHT_REQUESTS.get(cacheKey);
  }

  const token = localStorage.getItem("market_ai_token");
  const headers = {
    ...(payload !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const requestPromise = fetch(`${API_BASE_URL}${path}`, {
    method: normalizedMethod,
    headers: Object.keys(headers).length > 0 ? headers : undefined,
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal,
  }).then(async (response) => {
    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error("Backend returned a non-JSON response.");
    }

    if (response.status === 401) {
      localStorage.removeItem("market_ai_token");
      localStorage.removeItem("market_ai_user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new Error("جلستك انتهت. سجّل دخول مرة ثانية.");
    }

    if (!response.ok) {
      const message = data?.detail || data?.error || `Request failed with status ${response.status}`;
      throw new Error(message);
    }

    if (data?.error) {
      throw new Error(data.error);
    }

    if (normalizedMethod === "GET" && cacheTtlMs > 0) {
      RESPONSE_CACHE.set(cacheKey, {
        expiresAt: Date.now() + cacheTtlMs,
        value: data,
      });
      pruneCache();
    }

    return data;
  }).finally(() => {
    if (canUseInflight) {
      INFLIGHT_REQUESTS.delete(cacheKey);
    }
  });

  if (canUseInflight) {
    INFLIGHT_REQUESTS.set(cacheKey, requestPromise);
  }

  return requestPromise;
}

export async function getJson(path, options = {}) {
  return requestJson(path, { ...options, method: "GET" });
}

export async function postJson(path, payload, options = {}) {
  return requestJson(path, { ...options, method: "POST", payload });
}

export async function putJson(path, payload, options = {}) {
  return requestJson(path, { ...options, method: "PUT", payload });
}

export async function deleteJson(path, options = {}) {
  return requestJson(path, { ...options, method: "DELETE" });
}

export function invalidateJsonCache(prefix = "") {
  const normalizedPrefix = String(prefix || "");
  for (const key of RESPONSE_CACHE.keys()) {
    if (!normalizedPrefix || key.includes(normalizedPrefix)) {
      RESPONSE_CACHE.delete(key);
    }
  }
}
