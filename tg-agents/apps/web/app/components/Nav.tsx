import Link from "next/link";

export function Sidebar() {
  return (
    <nav className="sidebar">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>tg-agents</div>
      <div className="grid">
        <Link href="/projects" className="btn secondary">
          Проекты
        </Link>
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
