import { useCallback, useEffect, useRef, useState } from "react";

export function useAsyncResource(loader, options = {}) {
  const { immediate = true, initialData = null } = options;
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState("");
  const cancelledRef = useRef(false);

  const reload = useCallback(async (...args) => {
    const controller = new AbortController();
    cancelledRef.current = false;

    setLoading(true);
    setError("");
    try {
      const payload = await loader(...args);
      if (cancelledRef.current) return;
      setData(payload);
      return payload;
    } catch (requestError) {
      if (cancelledRef.current) return;
      const message = requestError?.message || "Request failed.";
      setError(message);
      throw requestError;
    } finally {
      if (!cancelledRef.current) {
        setLoading(false);
      }
    }
  }, [loader]);

  useEffect(() => {
    if (!immediate) {
      return;
    }
    reload().catch(() => {});

    return () => {
      cancelledRef.current = true;
    };
  }, [immediate, reload]);

  return {
    data,
    setData,
    loading,
    error,
    setError,
    reload,
  };
}
