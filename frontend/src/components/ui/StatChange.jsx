import clsx from "clsx";

import { translateNode } from "../../lib/i18n";


export default function StatChange({ value, tone = "neutral", prefix = "" }) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  return (
    <span className={clsx("stat-change", `stat-change-${tone}`)}>
      {translateNode(`${prefix}${value}`)}
    </span>
  );
}
