import PanelTitle from "./PanelTitle";


export default function SectionHeader({ title, description, action, badge }) {
  return <PanelTitle title={title} description={description} badge={badge} action={action} />;
}
