import clsx from "clsx";
import { Link } from "react-router-dom";

import { translateNode } from "../../lib/i18n";


export default function ActionButton({
  children,
  variant = "secondary",
  size = "md",
  to,
  leading,
  trailing,
  className,
  ...props
}) {
  const content = (
    <>
      {leading ? <span className="action-button-icon">{leading}</span> : null}
      <span>{translateNode(children)}</span>
      {trailing ? <span className="action-button-icon">{trailing}</span> : null}
    </>
  );

  const sharedClassName = clsx("action-button", `action-button-${variant}`, `action-button-${size}`, className);

  if (to) {
    return (
      <Link to={to} className={sharedClassName} {...props}>
        {content}
      </Link>
    );
  }

  return (
    <button className={sharedClassName} type="button" {...props}>
      {content}
    </button>
  );
}
