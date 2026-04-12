import PageHeader from "./ui/PageHeader";


export default function PageShell({ title, description, eyebrow, actions, children, className = "" }) {
  return (
    <section className={`page-shell${className ? ` ${className}` : ""}`}>
      <PageHeader title={title} description={description} eyebrow={eyebrow} actions={actions} />
      <div className="page-shell-body panel-grid">
        {children}
      </div>
    </section>
  );
}
