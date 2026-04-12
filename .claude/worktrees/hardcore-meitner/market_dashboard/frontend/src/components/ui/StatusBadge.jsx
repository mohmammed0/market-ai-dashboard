import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


export default function StatusBadge({ label, tone = "default", className = "" }) {
  return <span className={clsx("status-badge", `status-${tone}`, className)}>{translateNode(label)}</span>;
}
