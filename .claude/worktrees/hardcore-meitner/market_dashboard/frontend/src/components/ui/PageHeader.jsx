import PanelTitle from "./PanelTitle";


export default function PageHeader({ title, description, eyebrow = "منصة Market AI", actions }) {
  return (
    <header className="page-header">
      <PanelTitle
        title={title}
        description={description}
        eyebrow={eyebrow}
        size="page"
        titleAs="h2"
      />
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  );
}
