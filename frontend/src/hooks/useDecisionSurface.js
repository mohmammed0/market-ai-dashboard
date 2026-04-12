import { useCallback, useEffect, useState } from "react";

import { fetchDecisionSurface } from "../lib/api";


export default function useDecisionSurface({
  symbol,
  startDate,
  endDate,
  includeDl = true,
  includeEnsemble = true,
  enabled = true,
}) {
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshDecision = useCallback(async (override = {}) => {
    const nextSymbol = String(override.symbol ?? symbol ?? "").trim().toUpperCase();
    const nextStartDate = override.startDate ?? startDate;
    const nextEndDate = override.endDate ?? endDate;
    if (!enabled || !nextSymbol) {
      setDecision(null);
      setError("");
      return null;
    }

    setLoading(true);
    setError("");
    try {
      const payload = await fetchDecisionSurface({
        symbol: nextSymbol,
        start_date: nextStartDate,
        end_date: nextEndDate,
        include_dl: includeDl,
        include_ensemble: includeEnsemble,
      });
      setDecision(payload);
      return payload;
    } catch (requestError) {
      setDecision(null);
      setError(requestError.message || "تعذر تحميل طبقة القرار.");
      throw requestError;
    } finally {
      setLoading(false);
    }
  }, [symbol, startDate, endDate, includeDl, includeEnsemble, enabled]);

  useEffect(() => {
    if (!enabled || !symbol) {
      setDecision(null);
      setError("");
      return;
    }
    refreshDecision().catch(() => {});
  }, [enabled, symbol, startDate, endDate, refreshDecision]);

  return {
    decision,
    loading,
    error,
    setDecision,
    refreshDecision,
  };
}
