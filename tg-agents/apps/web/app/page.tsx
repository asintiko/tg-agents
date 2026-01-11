"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGate } from "./components/AuthGate";
import { PageShell } from "./components/Nav";
import { ProjectsApi, Project } from "./lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await ProjectsApi.list();
      setProjects(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    setLoading(true);
    try {
      await ProjectsApi.create(name);
      setName("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageShell>
      <AuthGate>
        <div className="grid" style={{ gap: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <h2>Проекты</h2>
              <div className="muted">Управление телеграм-агентами</div>
            </div>
          </div>
          <div className="card">
            <div className="label">Название</div>
            <input
              className="input"
              placeholder="Название проекта"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button className="btn" onClick={create} disabled={loading} style={{ marginTop: 10 }}>
              {loading ? "Сохраняю..." : "Создать"}
            </button>
          </div>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Тематика</th>
                  <th>Создан</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td>
                      <Link href={`/projects/${p.id}/settings`}>{p.name}</Link>
                    </td>
                    <td>{p.niche}</td>
                    <td>{new Date(p.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
