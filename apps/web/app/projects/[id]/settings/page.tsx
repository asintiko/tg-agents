"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { AgentConfig, ConfigApi } from "../../../lib/api";

export default function SettingsPage() {
  const params = useParams();
  const projectId = Number(params?.id);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await ConfigApi.get(projectId);
      setConfig(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) load();
  }, [projectId, load]);

  const update = async () => {
    if (!config) return;
    setLoading(true);
    try {
      const data = await ConfigApi.upsert(projectId, config);
      setConfig(data);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const onChange = (field: keyof AgentConfig, value: any) => {
    setConfig((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <h2>Конфигурация агента</h2>
        <div className="muted" style={{ marginBottom: 8 }}>
          Настройте расписание и формат постов. После изменений нажмите «Сохранить».
        </div>
        {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
        {!config && <div className="muted">Загрузка...</div>}
        {config && (
          <div className="grid" style={{ gap: 12 }}>
            <div className="row">
              <div style={{ flex: 1 }}>
                <div className="label">Постов в день</div>
                <input
                  className="input"
                  type="number"
                  value={config.posts_per_day}
                  onChange={(e) => onChange("posts_per_day", Number(e.target.value))}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Окно: начало</div>
                <input
                  className="input"
                  value={config.window_start}
                  onChange={(e) => onChange("window_start", e.target.value)}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Окно: конец</div>
                <input
                  className="input"
                  value={config.window_end}
                  onChange={(e) => onChange("window_end", e.target.value)}
                />
              </div>
            </div>
            <div className="row">
              <div style={{ flex: 1 }}>
                <div className="label">Мин. интервал (минут)</div>
                <input
                  className="input"
                  type="number"
                  value={config.min_interval_minutes}
                  onChange={(e) => onChange("min_interval_minutes", Number(e.target.value))}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Тональность</div>
                <input
                  className="input"
                  value={config.tone}
                  onChange={(e) => onChange("tone", e.target.value)}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Язык</div>
                <input
                  className="input"
                  value={config.language}
                  onChange={(e) => onChange("language", e.target.value)}
                />
              </div>
            </div>
            <div>
              <div className="label">Подпись (HTML)</div>
              <textarea
                className="input"
                style={{ minHeight: 80 }}
                value={config.signature_html ?? ""}
                onChange={(e) => onChange("signature_html", e.target.value)}
              />
            </div>
            <div className="row">
              <div style={{ flex: 1 }}>
                <div className="label">Эмодзи</div>
                <select
                  className="input"
                  value={config.emoji_mode}
                  onChange={(e) => onChange("emoji_mode", e.target.value)}
                >
                  <option value="off">Без эмодзи</option>
                  <option value="basic">Базовые</option>
                  <option value="premium">Premium</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Брендовый премиум-эмодзи</div>
                <input
                  className="input"
                  placeholder="tg://emoji?id=123... или число"
                  value={config.premium_emoji_id ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const match = raw.match(/(\d+)/);
                    const id = match ? Number(match[1]) : null;
                    onChange("premium_emoji_id", id);
                  }}
                />
                <div className="muted" style={{ fontSize: 12 }}>
                  Вставьте ссылку tg://emoji или числовой ID. Если оставить пустым, будет использован запасной символ.
                </div>
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Запасной символ эмодзи</div>
                <input
                  className="input"
                  maxLength={4}
                  placeholder="Например, ⚽"
                  value={config.premium_emoji_fallback ?? ""}
                  onChange={(e) => onChange("premium_emoji_fallback", e.target.value)}
                />
                <div className="muted" style={{ fontSize: 12 }}>
                  Отобразится в тексте, если премиум-эмодзи не доступен.
                </div>
              </div>
            </div>
            <div className="row">
              <div style={{ flex: 1 }}>
                <div className="label">Картинки</div>
                <select
                  className="input"
                  value={config.image_mode}
                  onChange={(e) => onChange("image_mode", e.target.value)}
                >
                  <option value="wikimedia">Wikimedia</option>
                  <option value="og_image">OG из новости</option>
                  <option value="link_preview">Без поиска картинки</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Добавлять ссылку на источник</div>
                <input
                  type="checkbox"
                  checked={config.include_source_link}
                  onChange={(e) => onChange("include_source_link", e.target.checked)}
                />
              </div>
            </div>
            <button className="btn" onClick={update} disabled={loading}>
              {loading ? "Сохраняю..." : "Сохранить"}
            </button>
          </div>
        )}
      </AuthGate>
    </PageShell>
  );
}
