"use client";

import { useEffect, useState } from "react";
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

  const load = async () => {
    setLoading(true);
    try {
      const data = await ConfigApi.get(projectId);
      setConfig(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) load();
  }, [projectId]);

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
                  <option value="off">off</option>
                  <option value="basic">basic</option>
                  <option value="premium">premium</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div className="label">Картинки</div>
                <select
                  className="input"
                  value={config.image_mode}
                  onChange={(e) => onChange("image_mode", e.target.value)}
                >
                  <option value="wikimedia">wikimedia</option>
                  <option value="og_image">og_image</option>
                  <option value="link_preview">link_preview</option>
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
