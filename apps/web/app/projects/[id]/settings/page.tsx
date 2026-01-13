"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { AgentConfig, ConfigApi, CustomEmoji, EmojisApi } from "../../../lib/api";

export default function SettingsPage() {
  const params = useParams();
  const projectId = Number(params?.id);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [emojiLoading, setEmojiLoading] = useState(false);
  const [emojiSearch, setEmojiSearch] = useState("");
  const [emojis, setEmojis] = useState<CustomEmoji[]>([]);

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

  const loadEmojis = useCallback(async () => {
    if (!projectId) return;
    setEmojiLoading(true);
    try {
      const list = await EmojisApi.list(projectId, emojiSearch);
      setEmojis(list);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEmojiLoading(false);
    }
  }, [projectId, emojiSearch]);

  useEffect(() => {
    if (projectId) load();
  }, [projectId, load]);

  useEffect(() => {
    if (projectId) void loadEmojis();
  }, [projectId, loadEmojis]);

  const update = async () => {
    if (!config) return;
    setLoading(true);
    try {
      const data = await ConfigApi.upsert(projectId, config);
      setConfig(data);
      setError(null);
      setInfo("Настройки сохранены");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const syncEmojis = async () => {
    if (!projectId) return;
    setEmojiLoading(true);
    setError(null);
    try {
      await EmojisApi.sync(projectId);
      await loadEmojis();
      setInfo("Премиум-эмодзи синхронизированы");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEmojiLoading(false);
    }
  };

  const selectEmoji = (emoji: CustomEmoji) => {
    onChange("premium_emoji_id", emoji.document_id);
    onChange("premium_emoji_alt", emoji.alt);
    setInfo(`Премиум-эмодзи установлен: ${emoji.alt}`);
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
          Настройте расписание и формат постов. Все тексты публикуются только на русском языке; при выходе модели на английский текст система повторит генерацию и зафиксирует русский вариант.
        </div>
        {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
        {info && <div className="badge" style={{ background: "#065f46" }}>{info}</div>}
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
            </div>
            <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 240 }}>
                <div className="label">Прогнозы матчей (1 раз в день)</div>
                <label className="muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={config.predictions_enabled}
                    onChange={(e) => onChange("predictions_enabled", e.target.checked)}
                  />
                  Включить ежедневный пост с прогнозами на топ-матчи (футбольная ниша).
                </label>
              </div>
              <div style={{ flex: 1, minWidth: 200 }}>
                <div className="label">Время прогноза (МСК)</div>
                <input
                  className="input"
                  value={config.predictions_time_msk}
                  onChange={(e) => onChange("predictions_time_msk", e.target.value)}
                  placeholder="10:00"
                />
                <div className="muted" style={{ fontSize: 12 }}>Если время вне окна — будет сдвинуто внутрь окна.</div>
              </div>
              <div style={{ flex: 1, minWidth: 200 }}>
                <div className="label">Кол-во матчей в прогнозе</div>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={10}
                  value={config.predictions_matches_count}
                  onChange={(e) => onChange("predictions_matches_count", Number(e.target.value))}
                />
              </div>
              <div style={{ flex: 1, minWidth: 240 }}>
                <div className="label">Gemini Web Search (Google)</div>
                <label className="muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={config.web_search_enabled}
                    onChange={(e) => onChange("web_search_enabled", e.target.checked)}
                  />
                  При генерации можно обращаться к поиску Google для уточнения фактов.
                </label>
              </div>
            </div>
            <div className="card" style={{ gap: 8 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="label">Премиум-эмодзи (синхронизация из Telegram)</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    Синхронизируйте ваши премиум-эмодзи и выберите символ. В тексте поста он будет добавлен в начале.
                  </div>
                </div>
                <button className="btn secondary" onClick={syncEmojis} disabled={emojiLoading}>
                  {emojiLoading ? "Синхронизируем..." : "Синхронизировать"}
                </button>
              </div>
              <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  className="input"
                  placeholder="Поиск по эмодзи или названию набора"
                  value={emojiSearch}
                  onChange={(e) => setEmojiSearch(e.target.value)}
                  style={{ maxWidth: 280 }}
                />
                <button className="btn secondary" onClick={loadEmojis} disabled={emojiLoading}>
                  Найти
                </button>
              </div>
              <div className="grid" style={{ gap: 6 }}>
                {emojis.map((emoji) => (
                  <div
                    key={emoji.document_id}
                    className="row"
                    style={{
                      justifyContent: "space-between",
                      alignItems: "center",
                      borderBottom: "1px solid var(--border)",
                      paddingBottom: 6,
                    }}
                  >
                    <div className="grid" style={{ gap: 2 }}>
                      <div style={{ fontSize: 18 }}>{emoji.alt}</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {emoji.stickerset_title || "Без названия"} · tg://emoji?id={emoji.document_id}
                      </div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <button
                        className="btn secondary"
                        onClick={() => navigator.clipboard.writeText(`tg://emoji?id=${emoji.document_id}`)}
                      >
                        Скопировать ссылку
                      </button>
                      <button className="btn" onClick={() => selectEmoji(emoji)}>
                        Использовать
                      </button>
                    </div>
                  </div>
                ))}
                {emojis.length === 0 && <div className="muted">Нет эмодзи. Нажмите «Синхронизировать».</div>}
              </div>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              Посты всегда публикуются на русском, ссылки на источник автоматически не добавляются.
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
