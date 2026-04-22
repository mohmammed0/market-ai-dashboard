import { createContext, useContext, useEffect, useRef, useState } from "react";

import { getJson } from "../api/client";

const AppDataContext = createContext(null);

export function AppDataProvider({ children }) {
  const [store, setStore] = useState({});
  const inflight = useRef(new Map());
  const controllers = useRef(new Map());
  const isMounted = useRef(true);

  function updateSection(key, patch) {
    setStore(prev => ({ ...prev, [key]: { ...(prev[key] || {}), ...patch } }));
  }

  async function fetchSection(key, url, options = {}) {
    if (inflight.current.has(key)) {
      return inflight.current.get(key);
    }

    const controller = new AbortController();
    controllers.current.set(key, controller);
    updateSection(key, { loading: true });

    const request = getJson(url, {
      cacheTtlMs: options.cacheTtlMs ?? 0,
      forceFresh: options.forceFresh ?? false,
      signal: controller.signal,
    })
      .then(data => {
        if (!isMounted.current || controller.signal.aborted) {
          return null;
        }
        updateSection(key, { data, loading: false, error: null, lastFetch: Date.now() });
        return data;
      })
      .catch(error => {
        if (!isMounted.current || controller.signal.aborted) {
          return null;
        }
        updateSection(key, { loading: false, error: error?.message || "حدث خطأ غير متوقع" });
        return null;
      })
      .finally(() => {
        inflight.current.delete(key);
        controllers.current.delete(key);
      });

    inflight.current.set(key, request);
    return request;
  }

  useEffect(() => {
    isMounted.current = true;
    const sections = [
      { key: "dashboardLite",   url: "/api/dashboard/lite",            interval: 45000, cacheTtlMs: 5000 },
      { key: "portfolioSnapshot", url: "/api/portfolio/snapshot",      interval: 30000, cacheTtlMs: 5000 },
      { key: "tradingSignals",  url: "/api/trading/signals",           interval: 45000, cacheTtlMs: 5000 },
      { key: "aiStatus",        url: "/api/ai/status",                 interval: 120000, cacheTtlMs: 15000 },
      { key: "pipelineLive",    url: "/api/live/pipeline?limit_events=50&limit_cycles=10", interval: 5000, cacheTtlMs: 0 },
    ];

    const timers = [];
    sections.forEach(({ key, url, interval, cacheTtlMs }) => {
      fetchSection(key, url, { cacheTtlMs, forceFresh: true });
      const t = setInterval(() => fetchSection(key, url, { cacheTtlMs }), interval);
      timers.push(t);
    });

    return () => {
      isMounted.current = false;
      timers.forEach(clearInterval);
      for (const controller of controllers.current.values()) {
        controller.abort();
      }
      controllers.current.clear();
      inflight.current.clear();
    };
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
