import { memo } from "react";
import clsx from "clsx";
import { translateNode } from "../../lib/i18n";

const TONE_MAP = {
  accent: "positive",
  positive: "positive",
  success: "positive",
  negative: "negative",
  error: "negative",
  danger: "negative",
  warning: "warning",
  info: "info",
  subtle: "neutral",
  neutral: "neutral",
  default: "neutral",
};

function StatusBadge({ label, tone = "neutral", dot = true, className }) {
  const mappedTone = TONE_MAP[tone] || "neutral";

  return (
    <span className={clsx("status-badge", `status-badge--${mappedTone}`, className)}>
      {dot && <span className={`status-dot status-dot--${mappedTone}`} />}
      <span>{translateNode(label)}</span>
    </span>
  );
}

export default memo(StatusBadge);
