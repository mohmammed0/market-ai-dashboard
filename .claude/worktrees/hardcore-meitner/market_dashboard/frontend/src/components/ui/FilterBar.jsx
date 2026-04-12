import PanelTitle from "./PanelTitle";


export default function FilterBar({ title, description, children, action }) {
  return (
    <div className="panel filter-bar">
      <PanelTitle title={title} description={description} action={action} />
      <div className="filter-bar-body">{children}</div>
    </div>
  );
}
