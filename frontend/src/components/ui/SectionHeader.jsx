import { isValidElement } from "react";

import StatusBadge from "./StatusBadge";
import { translateNode } from "../../lib/i18n";


export default function SectionHeader({
  title,
  description,
  eyebrow,
  badge,
  action,
  size = "section",
  align = "start",
  titleAs: TitleTag = "h3",
}) {
  const badgeNode = badge
    ? isValidElement(badge)
      ? badge
      : <StatusBadge label={badge} tone="neutral" />
    : null;

  return (
    <div className={`panel-title panel-title-${size} panel-title-${align}`}>
      <div className="panel-title-copy">
        {eyebrow ? <div className="panel-title-eyebrow">{translateNode(eyebrow)}</div> : null}
        <div className="panel-title-row">
          <TitleTag>{translateNode(title)}</TitleTag>
          {badgeNode}
        </div>
        {description ? <p>{translateNode(description)}</p> : null}
      </div>
      {action ? <div className="panel-title-action">{action}</div> : null}
    </div>
  );
}
