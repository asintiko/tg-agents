"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { FeedSource, SourcesApi } from "../../../lib/api";

export default function SourcesPage() {
  const projectId = Number(useParams()?.id);
  const [sources, setSources] = useState<FeedSource[]>([]);
  const [form, setForm] = useState({ name: "", url: "", weight: 10, enabled: true });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await SourcesApi.list(projectId);
      setSources(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) load();
  }, [projectId, load]);

  const create = async () => {
    if (!form.name || !form.url) return;
    setLoading(true);
    try {
      await SourcesApi.create(projectId, form);
      setForm({ name: "", url: "", weight: 10, enabled: true });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggle = async (source: FeedSource) => {
    await SourcesApi.update(source.id, { ...source, enabled: !source.enabled });
    await load();
  };

  const remove = async (id: number) => {
    await SourcesApi.remove(id);
    await load();
  };

  const pullNow = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await SourcesApi.pullProject(projectId);
      await load();
      alert(`Загружено записей: ${res.inserted}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <div className="grid" style={{ gap: 12 }}>
          <h2>Источники новостей</h2>
          <div className="muted">
            RSS — бесплатная лента новостей (XML), платные API не используются. Воркер проверяет ленты каждые 5 минут. Кнопка ниже запускает проверку сразу.
          </div>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="btn" onClick={pullNow} disabled={loading}>
              Проверить RSS сейчас
            </button>
            <div className="muted">После проверки новые новости появятся на странице «Старт».</div>
          </div>
          <div className="card">
            <div className="row">
              <input
                className="input"
                placeholder="Название"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
              <input
                className="input"
                placeholder="URL"
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <input
                className="input"
                type="number"
                value={form.weight}
                onChange={(e) => setForm((f) => ({ ...f, weight: Number(e.target.value) }))}
              />
              <label className="label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
                Включен
              </label>
              <button className="btn" onClick={create} disabled={loading}>
                Добавить
              </button>
            </div>
          </div>
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>URL</th>
                  <th>Вес</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td>{s.url}</td>
                    <td>{s.weight}</td>
                    <td>
                      <button className="btn secondary" onClick={() => toggle(s)}>
                        {s.enabled ? "Выключить" : "Включить"}
                      </button>
                    </td>
                    <td>
                      <button className="btn danger" onClick={() => remove(s.id)}>
                        Удалить
                      </button>
                    </td>
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
