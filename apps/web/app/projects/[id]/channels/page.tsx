"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { ChannelsApi, TelegramChannel } from "../../../lib/api";

export default function ChannelsPage() {
  const projectId = Number(useParams()?.id);
  const [channels, setChannels] = useState<TelegramChannel[]>([]);
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
    await ChannelsApi.update(ch.id, { enabled: !ch.enabled });
    await load();
  };

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <h2>Telegram каналы</h2>
        {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
        <div className="card">
          <div className="row">
            <input
              className="input"
              placeholder="ID чата"
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
              placeholder="Username"
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            />
            <button className="btn" onClick={addChannel} disabled={loading}>
              Добавить
            </button>
          </div>
        </div>
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Чат</th>
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
                  <td>{ch.enabled ? "Да" : "Нет"}</td>
                  <td>
                    <button className="btn secondary" onClick={() => toggle(ch)}>
                      {ch.enabled ? "Выключить" : "Включить"}
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
