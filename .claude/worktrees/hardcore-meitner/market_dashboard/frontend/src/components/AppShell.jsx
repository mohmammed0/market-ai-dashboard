import SidebarNav from "./ui/SidebarNav";
import TopHeader from "./ui/TopHeader";


export default function AppShell({ navItems, children }) {
  return (
    <div className="app-shell" dir="rtl">
      <SidebarNav items={navItems} />
      <div className="app-main">
        <div className="app-main-shell">
          <TopHeader navItems={navItems} />
          <main className="content">
            <div className="content-shell">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
