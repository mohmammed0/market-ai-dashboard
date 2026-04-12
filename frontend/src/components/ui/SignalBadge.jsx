import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


export default function SignalBadge({ signal, size = "default" }) {
  const normalized = String(signal || "UNKNOWN").toUpperCase();

  const toneClass = {
    BUY: "signal-badge--buy",
    SELL: "signal-badge--sell",
    HOLD: "signal-badge--hold",
  }[normalized] || "signal-badge--neutral";

  return (
    <span className={clsx("signal-badge", toneClass, size === "sm" && "signal-badge--sm")}>
      {translateNode(normalized)}
    </span>
  );
}
