import SectionCard from "./SectionCard";


export default function FilterBar({ title, description, children, action }) {
  return (
    <SectionCard title={title} description={description} action={action}>
      {children}
    </SectionCard>
  );
}
