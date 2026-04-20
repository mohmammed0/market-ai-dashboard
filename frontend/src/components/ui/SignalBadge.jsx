import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


export default function SignalBadge({ signal, size = "default" }) {
  const normalized = String(signal || "UNKNOWN").trim().toUpperCase();

  const toneClass = {
    BUY: "signal-badge--buy",
    LONG: "signal-badge--buy",
    BULLISH: "signal-badge--buy",
    SELL: "signal-badge--sell",
    SHORT: "signal-badge--sell",
    BEARISH: "signal-badge--sell",
    HOLD: "signal-badge--hold",
    WAIT: "signal-badge--hold",
    WATCH: "signal-badge--neutral",
    NEUTRAL: "signal-badge--neutral",
  }[normalized] || "signal-badge--neutral";

  return (
    <span className={clsx("signal-badge", toneClass, size === "sm" && "signal-badge--sm")}>
      {translateNode(normalized)}
    </span>
  );
}
