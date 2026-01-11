"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

const tabs = [
  { slug: "settings", label: "Настройки" },
  { slug: "sources", label: "Источники" },
  { slug: "telegram", label: "Telegram" },
  { slug: "channels", label: "Каналы" },
];

export function ProjectNav() {
  const params = useParams();
  const pathname = usePathname();
  const projectId = params?.id;

  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      {tabs.map((tab) => {
        const href = `/projects/${projectId}/${tab.slug}`;
        const active = pathname?.endsWith(tab.slug);
        return (
          <Link
            key={tab.slug}
            href={href}
            className="btn secondary"
            style={{ background: active ? "#0f172a" : "#1f2937" }}
          >
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}
