import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


export default function SignalBadge({ signal }) {
  const normalized = String(signal || "UNKNOWN").toUpperCase();

  return (
    <span
      className={clsx("signal-badge", {
        "signal-buy": normalized === "BUY",
        "signal-sell": normalized === "SELL",
        "signal-hold": normalized === "HOLD",
        "signal-unknown": !["BUY", "SELL", "HOLD"].includes(normalized),
      })}
    >
      {translateNode(normalized)}
    </span>
  );
}
