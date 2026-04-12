import { useState } from "react";
import Sidebar from "./shell/Sidebar";
import Header from "./shell/Header";


export default function AppShell({ navItems, children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-shell" dir="rtl">
      <Sidebar
        items={navItems}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="app-main">
        <Header
          navItems={navItems}
          onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
        />
        <main className="app-content">
          {children}
        </main>
      </div>
    </div>
  );
}
