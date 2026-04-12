import PanelTitle from "./PanelTitle";


export default function SectionCard({
  title,
  description,
  eyebrow,
  badge,
  action,
  children,
  footer,
  className = "",
  tone = "default",
}) {
  return (
    <section className={`panel result-panel section-card section-card-${tone}${className ? ` ${className}` : ""}`}>
      {title || description || action || badge || eyebrow ? (
        <PanelTitle
          title={title}
          description={description}
          eyebrow={eyebrow}
          badge={badge}
          action={action}
        />
      ) : null}
      <div className="section-card-body">
        {children}
      </div>
      {footer ? <div className="section-card-footer">{footer}</div> : null}
    </section>
  );
}
