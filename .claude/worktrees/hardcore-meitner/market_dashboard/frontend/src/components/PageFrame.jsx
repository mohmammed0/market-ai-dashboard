import PageShell from "./PageShell";


export default function PageFrame({ title, description, eyebrow, children, headerActions }) {
  return (
    <PageShell title={title} description={description} eyebrow={eyebrow} actions={headerActions}>
      {children}
    </PageShell>
  );
}
