import clsx from "clsx";
import { Link } from "react-router-dom";
import { translateNode } from "../../lib/i18n";


export default function ActionButton({
  children,
  variant = "secondary",
  size = "sm",
  to,
  leading,
  trailing,
  className,
  ...props
}) {
  const content = (
    <>
      {leading && <span>{leading}</span>}
      <span>{translateNode(children)}</span>
      {trailing && <span>{trailing}</span>}
    </>
  );

  const cls = clsx("btn", `btn-${variant}`, size === "sm" && "btn-sm", size === "xs" && "btn-xs", className);

  if (to) {
    return <Link to={to} className={cls} {...props}>{content}</Link>;
  }

  return <button className={cls} type="button" {...props}>{content}</button>;
}
