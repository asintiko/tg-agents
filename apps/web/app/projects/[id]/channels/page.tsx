"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { ChannelsApi, DiscoveredChannel, TelegramChannel } from "../../../lib/api";

export default function ChannelsPage() {
  const projectId = Number(useParams()?.id);
  const [channels, setChannels] = useState<TelegramChannel[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredChannel[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [form, setForm] = useState({ tg_chat_id: "", title: "", username: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await ChannelsApi.list(projectId);
      setChannels(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) load();
  }, [projectId, load]);

  const addChannel = async () => {
    if (!form.tg_chat_id || !form.title) return;
    setLoading(true);
    try {
      await ChannelsApi.create(projectId, {
        tg_chat_id: form.tg_chat_id,
        title: form.title,
        username: form.username || null,
        enabled: true,
      });
      setForm({ tg_chat_id: "", title: "", username: "" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggle = async (ch: TelegramChannel) => {
    setLoading(true);
    try {
      await ChannelsApi.update(ch.id, { enabled: !ch.enabled });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const discover = async () => {
    setLoading(true);
    setError(null);
    try {
      const found = await ChannelsApi.discoverForProject(projectId);
      setDiscovered(found);
      setSelected(new Set(found.map((c) => c.tg_chat_id)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (tgChatId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tgChatId)) {
        next.delete(tgChatId);
      } else {
        next.add(tgChatId);
      }
      return next;
    });
  };

  const importSelected = async (replace: boolean) => {
    const toImport = discovered.filter((c) => selected.has(c.tg_chat_id));
    if (!toImport.length) {
      setError("Выберите хотя бы один канал");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await ChannelsApi.importForProject(projectId, toImport, replace);
      setDiscovered([]);
      setSelected(new Set());
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const selectedCount = useMemo(() => selected.size, [selected]);

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <h2>Telegram-каналы</h2>
        <div className="muted" style={{ marginBottom: 12 }}>
          Выберите каналы, где у вашего аккаунта есть права на публикацию.
        </div>
        {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}

        <div className="card" style={{ gap: 12 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="btn" onClick={discover} disabled={loading}>
              {loading ? "Ищем..." : "Найти мои каналы"}
            </button>
            {discovered.length > 0 && (
              <>
                <button className="btn secondary" onClick={() => importSelected(true)} disabled={loading}>
                  Импортировать выбранные (заменить)
                </button>
                <button className="btn secondary" onClick={() => importSelected(false)} disabled={loading}>
                  Импортировать выбранные (добавить)
                </button>
                <div className="muted">Выбрано: {selectedCount} из {discovered.length}</div>
              </>
            )}
          </div>
          {discovered.length > 0 && (
            <div className="card" style={{ background: "var(--bg-secondary)" }}>
              <div className="label">Найденные каналы</div>
              <table className="table">
                <thead>
                  <tr>
                    <th></th>
                    <th>ID</th>
                    <th>Название</th>
                    <th>Username</th>
                  </tr>
                </thead>
                <tbody>
                  {discovered.map((ch) => (
                    <tr key={ch.tg_chat_id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(ch.tg_chat_id)}
                          onChange={() => toggleSelect(ch.tg_chat_id)}
                        />
                      </td>
                      <td>{ch.tg_chat_id}</td>
                      <td>{ch.title}</td>
                      <td>{ch.username || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card" style={{ gap: 8 }}>
          <div className="label">Добавить вручную</div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              className="input"
              placeholder="ID канала (например, -100...)"
              value={form.tg_chat_id}
              onChange={(e) => setForm((f) => ({ ...f, tg_chat_id: e.target.value }))}
            />
            <input
              className="input"
              placeholder="Название"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
            <input
              className="input"
              placeholder="Username (опционально)"
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            />
            <button className="btn" onClick={addChannel} disabled={loading}>
              Добавить
            </button>
          </div>
        </div>

        <div className="card">
          <div className="label">Подключённые каналы</div>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Chat ID</th>
                <th>Название</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {channels.map((ch) => (
                <tr key={ch.id}>
                  <td>{ch.id}</td>
                  <td>{ch.tg_chat_id}</td>
                  <td>{ch.title}</td>
                  <td>{ch.enabled ? "Включен" : "Выключен"}</td>
                  <td>
                    <button className="btn secondary" onClick={() => toggle(ch)} disabled={loading}>
                      {ch.enabled ? "Отключить" : "Включить"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AuthGate>
    </PageShell>
  );
}
