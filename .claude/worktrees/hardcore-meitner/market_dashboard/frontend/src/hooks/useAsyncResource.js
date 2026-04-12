import { useCallback, useEffect, useState } from "react";

export function useAsyncResource(loader, options = {}) {
  const { immediate = true, initialData = null } = options;
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState("");

  const reload = useCallback(async (...args) => {
    setLoading(true);
    setError("");
    try {
      const payload = await loader(...args);
      setData(payload);
      return payload;
    } catch (requestError) {
      const message = requestError?.message || "Request failed.";
      setError(message);
      throw requestError;
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    if (!immediate) {
      return;
    }
    reload().catch(() => {});
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
