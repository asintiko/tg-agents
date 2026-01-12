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
  const [search, setSearch] = useState("");
  const [showAvailableOnly, setShowAvailableOnly] = useState(true);
  const [showManual, setShowManual] = useState(false);

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

  const remove = async (id: number) => {
    setLoading(true);
    try {
      await ChannelsApi.remove(id);
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
      const selectable = found.filter((c) => c.can_post !== false);
      setSelected(new Set(selectable.map((c) => c.tg_chat_id)));
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

  const filteredDiscovered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return discovered.filter((c) => {
      if (showAvailableOnly && c.can_post === false) return false;
      if (!needle) return true;
      return (
        c.title.toLowerCase().includes(needle) ||
        (c.username || "").toLowerCase().includes(needle) ||
        c.tg_chat_id.toLowerCase().includes(needle)
      );
    });
  }, [discovered, search, showAvailableOnly]);

  const selectedCount = useMemo(() => selected.size, [selected]);

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <h2>Telegram-каналы</h2>
        <div className="muted" style={{ marginBottom: 12 }}>
          Найдите ваши каналы, проверьте права на публикацию, импортируйте и включите нужные.
        </div>
        {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}

        <div className="card" style={{ gap: 12 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="btn" onClick={discover} disabled={loading}>
              {loading ? "Ищем..." : "Найти мои каналы"}
            </button>
            {discovered.length > 0 && (
              <>
                <input
                  className="input"
                  style={{ maxWidth: 260 }}
                  placeholder="Поиск по названию или @username"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <label className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input
                    type="checkbox"
                    checked={showAvailableOnly}
                    onChange={(e) => setShowAvailableOnly(e.target.checked)}
                  />
                  Показывать только доступные
                </label>
                <div className="muted">Выбрано: {selectedCount} из {filteredDiscovered.length}</div>
              </>
            )}
          </div>
          {discovered.length > 0 && (
            <div className="card" style={{ background: "var(--bg-secondary)" }}>
              <div className="label">Найденные каналы</div>
              <div className="grid" style={{ gap: 8 }}>
                {filteredDiscovered.map((ch) => (
                  <div
                    key={ch.tg_chat_id}
                    className="row"
                    style={{
                      gap: 12,
                      alignItems: "center",
                      borderBottom: "1px solid var(--border)",
                      paddingBottom: 8,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(ch.tg_chat_id)}
                      onChange={() => toggleSelect(ch.tg_chat_id)}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700 }}>{ch.title}</div>
                      <div className="muted">{ch.username ? `@${ch.username}` : "без username"}</div>
                      <div className="muted">ID: {ch.tg_chat_id}</div>
                    </div>
                    <div className="badge" style={{ background: ch.can_post === false ? "#7f1d1d" : "#065f46" }}>
                      {ch.can_post === false ? "Нет прав" : "Можно публиковать"}
                    </div>
                    {ch.role && <div className="muted">Роль: {ch.role}</div>}
                  </div>
                ))}
              </div>
              <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                <button className="btn secondary" onClick={() => importSelected(true)} disabled={loading}>
                  Добавить выбранные (заменить)
                </button>
                <button className="btn secondary" onClick={() => importSelected(false)} disabled={loading}>
                  Добавить выбранные (добавить)
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="card" style={{ gap: 8 }}>
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
                  <td className="row" style={{ gap: 8 }}>
                    <button className="btn secondary" onClick={() => toggle(ch)} disabled={loading}>
                      {ch.enabled ? "Отключить" : "Включить"}
                    </button>
                    <button className="btn danger" onClick={() => remove(ch.id)} disabled={loading}>
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card" style={{ gap: 8 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <div className="label">Дополнительно: добавить вручную</div>
            <button className="btn secondary" onClick={() => setShowManual((v) => !v)}>
              {showManual ? "Скрыть" : "Показать"}
            </button>
          </div>
          {showManual && (
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
          )}
        </div>
      </AuthGate>
    </PageShell>
  );
}
