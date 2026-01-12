"use client";

import { useEffect, useState } from "react";

import { AuthGate } from "../components/AuthGate";
import { PageShell } from "../components/Nav";
import { ChannelsApi, DiscoveredChannel, TelegramChannel } from "../lib/api";

type SelectMap = Record<string, boolean>;

export default function ChannelsPage() {
  const [discovered, setDiscovered] = useState<DiscoveredChannel[]>([]);
  const [selected, setSelected] = useState<SelectMap>({});
  const [saved, setSaved] = useState<TelegramChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSaved = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await ChannelsApi.listSaved();
      setSaved(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSaved();
  }, []);

  const discover = async () => {
    setLoading(true);
    setError(null);
    try {
      const found = await ChannelsApi.discover();
      setDiscovered(found);
      const nextSelect: SelectMap = {};
      for (const ch of found) {
        nextSelect[ch.tg_chat_id] = true;
      }
      setSelected(nextSelect);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const saveSelected = async () => {
    const toSave = discovered.filter((ch) => selected[ch.tg_chat_id]);
    if (!toSave.length) {
      setError("Выберите хотя бы один канал");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await ChannelsApi.save(toSave, true);
      await loadSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleEnabled = async (channel: TelegramChannel) => {
    setLoading(true);
    setError(null);
    try {
      const updated = await ChannelsApi.toggle(channel.id, !channel.enabled);
      setSaved((prev) => prev.map((ch) => (ch.id === updated.id ? updated : ch)));
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
              <h2>Каналы</h2>
              <div className="muted">Поиск каналов, где вы админ, и сохранение для постинга</div>
            </div>
            <button className="btn" onClick={discover} disabled={loading}>
              {loading ? "Загрузка..." : "Найти мои каналы"}
            </button>
          </div>

          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}

          {discovered.length > 0 && (
            <div className="card">
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <div className="label">Новые каналы</div>
                <button className="btn secondary" onClick={saveSelected} disabled={loading}>
                  Сохранить выбранные
                </button>
              </div>
              <div className="grid" style={{ gap: 8 }}>
                {discovered.map((ch) => (
                  <label key={ch.tg_chat_id} className="row" style={{ gap: 12 }}>
                    <input
                      type="checkbox"
                      checked={selected[ch.tg_chat_id] ?? false}
                      onChange={() => toggleSelect(ch.tg_chat_id)}
                    />
                    <div>
                      <div style={{ fontWeight: 600 }}>{ch.title}</div>
                      <div className="muted">
                        {ch.username ? `@${ch.username}` : "без @username"} · {ch.tg_chat_id}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="card">
            <div className="label">Сохранённые каналы</div>
            {saved.length === 0 && <div className="muted">Список пуст</div>}
            {saved.map((ch) => (
              <div
                key={ch.id}
                className="row"
                style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{ch.title}</div>
                  <div className="muted">
                    {ch.username ? `@${ch.username}` : "без @username"} · {ch.tg_chat_id}
                  </div>
                </div>
                <label className="row" style={{ gap: 8, alignItems: "center" }}>
                  <span className="muted">Включен</span>
                  <input
                    type="checkbox"
                    checked={ch.enabled}
                    onChange={() => toggleEnabled(ch)}
                    disabled={loading}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
