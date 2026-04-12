import { useEffect, useState } from "react";

import {
  getPinnedSymbols,
  getRecentSymbols,
  isPinnedSymbol,
  pinSymbol,
  rememberSymbol,
  subscribeToSymbolLibrary,
  togglePinnedSymbol,
  unpinSymbol,
} from "./symbols";


export function useSymbolLibrary() {
  const [pinned, setPinned] = useState(() => getPinnedSymbols());
  const [recent, setRecent] = useState(() => getRecentSymbols());

  useEffect(() => {
    function refresh() {
      setPinned(getPinnedSymbols());
      setRecent(getRecentSymbols());
    }
    refresh();
    return subscribeToSymbolLibrary(refresh);
  }, []);

  return {
    pinned,
    recent,
    rememberSymbol,
    pinSymbol,
    unpinSymbol,
    togglePinnedSymbol,
    isPinnedSymbol,
  };
}
