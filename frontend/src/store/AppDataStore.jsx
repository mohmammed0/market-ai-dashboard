import { createContext, useContext, useEffect, useState } from "react";

import { getJson } from "../api/client";

const AppDataContext = createContext(null);

export function AppDataProvider({ children }) {
  const [store, setStore] = useState({});

  function updateSection(key, patch) {
    setStore(prev => ({ ...prev, [key]: { ...(prev[key] || {}), ...patch } }));
  }

  async function fetchSection(key, url, options = {}) {
    updateSection(key, { loading: true });
    try {
      const data = await getJson(url, {
        cacheTtlMs: options.cacheTtlMs ?? 0,
        forceFresh: options.forceFresh ?? false,
      });
      updateSection(key, { data, loading: false, error: null, lastFetch: Date.now() });
    } catch (e) {
      updateSection(key, { loading: false, error: e.message });
    }
  }

  useEffect(() => {
    const sections = [
      { key: "dashboardLite",   url: "/api/dashboard/lite",            interval: 45000, cacheTtlMs: 5000 },
      { key: "portfolioSnapshot", url: "/api/portfolio/snapshot",      interval: 30000, cacheTtlMs: 5000 },
      { key: "paperSignals",    url: "/api/paper/signals",             interval: 60000, cacheTtlMs: 5000 },
      { key: "aiStatus",        url: "/api/ai/status",                 interval: 120000, cacheTtlMs: 15000 },
    ];

    const timers = [];
    sections.forEach(({ key, url, interval, cacheTtlMs }) => {
      fetchSection(key, url, { cacheTtlMs, forceFresh: true });
      const t = setInterval(() => fetchSection(key, url, { cacheTtlMs }), interval);
      timers.push(t);
    });

    return () => timers.forEach(clearInterval);
  }, []);

  return (
    <AppDataContext.Provider value={{ store, fetchSection }}>
      {children}
    </AppDataContext.Provider>
  );
}

export function useAppData(key) {
  const ctx = useContext(AppDataContext);
  if (!ctx) return { loading: true, data: null, error: null };
  return ctx.store[key] || { loading: true, data: null, error: null };
}

export function useAppStore() {
  return useContext(AppDataContext);
}
