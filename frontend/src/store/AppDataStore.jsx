import { createContext, useContext, useEffect, useState } from "react";

const AppDataContext = createContext(null);

export function AppDataProvider({ children }) {
  const [store, setStore] = useState({});

  function updateSection(key, patch) {
    setStore(prev => ({ ...prev, [key]: { ...(prev[key] || {}), ...patch } }));
  }

  async function fetchSection(key, url) {
    updateSection(key, { loading: true });
    try {
      const token = localStorage.getItem("market_ai_token");
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: AbortSignal.timeout(12000),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      updateSection(key, { data, loading: false, error: null, lastFetch: Date.now() });
    } catch (e) {
      updateSection(key, { loading: false, error: e.message });
    }
  }

  useEffect(() => {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;

    // Only use endpoints that are confirmed working (200 OK, fast response)
    const sections = [
      { key: "marketOverview",  url: "/api/market/overview",           interval: 60000  },
      { key: "newsFeed",        url: `/api/ai/news/feed?date=${dateStr}&limit=50`, interval: 60000 },
      { key: "paperPortfolio",  url: "/api/paper/portfolio",           interval: 30000  },
      { key: "paperOrders",     url: "/api/paper/orders",              interval: 30000  },
      { key: "paperTrades",     url: "/api/paper/trades",              interval: 60000  },
      { key: "paperSignals",    url: "/api/paper/signals",             interval: 60000  },
      { key: "aiStatus",        url: "/api/ai/status",                 interval: 120000 },
      { key: "brokerStatus",    url: "/api/broker/status",             interval: 60000  },
    ];

    const timers = [];
    sections.forEach(({ key, url, interval }) => {
      fetchSection(key, url);
      const t = setInterval(() => fetchSection(key, url), interval);
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
