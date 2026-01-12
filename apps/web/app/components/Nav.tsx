import React from "react";
import Link from "next/link";

const navItems = [{ href: "/", label: "Проекты" }];

export function Sidebar() {
  return (
    <nav className="sidebar">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>tg-agents</div>
      <div className="grid">
        {navItems.map((item) => (
          <Link key={item.href + item.label} href={item.href} className="btn secondary">
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <main>
      <div className="shell">
        <Sidebar />
        <div className="content">{children}</div>
      </div>
    </main>
  );
}
