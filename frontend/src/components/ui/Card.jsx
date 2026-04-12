import clsx from "clsx";


export function Card({ children, className, variant, ...props }) {
  return (
    <div
      className={clsx("card", variant && `card--${variant}`, className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, description, action, children }) {
  return (
    <div className="card-header">
      <div className="card-header-content">
        {title && <h3 className="card-title">{title}</h3>}
        {description && <p className="card-description">{description}</p>}
        {children}
      </div>
      {action && <div className="card-header-action">{action}</div>}
    </div>
  );
}

export function CardBody({ children, flush, className }) {
  return (
    <div className={clsx(flush ? "card-body-flush" : "card-body", className)}>
      {children}
    </div>
  );
}

export function CardFooter({ children }) {
  return <div className="card-footer">{children}</div>;
}

export default Card;
