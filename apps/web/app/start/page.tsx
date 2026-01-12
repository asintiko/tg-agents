"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AuthGate } from "../components/AuthGate";
import { PageShell } from "../components/Nav";
import { ChannelsApi, TelegramGlobalApi, TestApi, PreviewApi, NewsApi, PreviewResponse } from "../lib/api";

export default function StartPage() {
  const [status, setStatus] = useState<string | null>(null);
  const [lastConnected, setLastConnected] = useState<string | null>(null);
  const [me, setMe] = useState<{ id: number; username: string | null; phone: string | null } | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);

  const loadStatus = async () => {
    try {
      const res = await TelegramGlobalApi.status();
      setStatus(res.status);
      setLastConnected(res.last_connected_at ?? null);
      setMe(res.me ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const startQr = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const res = await TelegramGlobalApi.startQr();
      setStatus(res.status);
      setQrUrl(res.qr_url ?? null);
      setMessage("Отсканируйте QR в Telegram");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const waitQr = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await TelegramGlobalApi.waitQr();
      setStatus(res.status);
      if (res.status === "password_required") {
        setPasswordNeeded(true);
      } else if (res.status === "connected") {
        setPasswordNeeded(false);
        setQrUrl(null);
        setMe(res.me ?? null);
        await loadStatus();
        setMessage("Аккаунт подключён");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const submitPassword = async () => {
    if (!password.trim()) {
      setError("Введите пароль 2FA");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await TelegramGlobalApi.password(password);
      setStatus(res.status);
      setPassword("");
      setPasswordNeeded(false);
      setMessage("Аккаунт подключён");
      await loadStatus();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const resetSession = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      await TelegramGlobalApi.resetSession();
      setStatus("disconnected");
      setQrUrl(null);
      setPassword("");
      setPasswordNeeded(false);
      setMe(null);
      setMessage("Сессия удалена");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const sendTest = async () => {
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await ChannelsApi.listSaved();
      if (!saved.length) {
        setError("Выберите хотя бы один канал");
        return;
      }
      const res = await TestApi.send();
      setMessage(res.tg_message_id ? `Опубликовано (id: ${res.tg_message_id})` : "Опубликовано");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const pullRss = async () => {
    setNewsLoading(true);
    setError(null);
    setMessage(null);
    try {
      await NewsApi.pull();
      setMessage("RSS обновлены");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setNewsLoading(false);
    }
  };

  const previewNext = async () => {
    setNewsLoading(true);
    setError(null);
    setMessage(null);
    try {
      const data = await PreviewApi.next();
      setPreview(data);
      setMessage("Предпросмотр готов");
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
    } finally {
      setNewsLoading(false);
    }
  };

  const publishNext = async () => {
    setNewsLoading(true);
    setError(null);
    setMessage(null);
    try {
      const res = await PreviewApi.publish();
      setMessage(`Опубликовано, news_id: ${res.news_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setNewsLoading(false);
    }
  };

  const statusText = status === "connected"
    ? "Подключен"
    : status === "waiting_for_scan"
      ? "Ожидаем сканирование"
      : status === "password_required"
        ? "Ожидаем пароль 2FA"
        : "Не подключен";

  return (
    <PageShell>
      <AuthGate>
        <div className="grid" style={{ gap: 16 }}>
          <h2>Старт</h2>
          <div className="card grid" style={{ gap: 10 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div className="label">Статус Telegram</div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{statusText}</div>
                {me && <div className="muted">{me.username ? `@${me.username}` : me.phone}</div>}
                {lastConnected && (
                  <div className="muted">
                    Последнее подключение: {new Date(lastConnected).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })}
                  </div>
                )}
              </div>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn secondary" onClick={loadStatus} disabled={loading}>
                  Обновить статус
                </button>
                <button className="btn secondary" onClick={resetSession} disabled={loading}>
                  Сбросить сессию
                </button>
              </div>
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn" onClick={startQr} disabled={loading}>
                Получить QR
              </button>
              {qrUrl && (
                <button className="btn secondary" onClick={waitQr} disabled={loading}>
                  Я отсканировал QR
                </button>
              )}
            </div>
            {qrUrl && (
              <div>
                <div className="label">Сканируйте в мобильном Telegram</div>
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUrl)}`}
                  alt="QR"
                  width={200}
                  height={200}
                />
              </div>
            )}
            {passwordNeeded && (
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <input
                  className="input"
                  type="password"
                  placeholder="Пароль 2FA"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button className="btn" onClick={submitPassword} disabled={loading}>
                  Отправить пароль
                </button>
              </div>
            )}
          </div>

          <div className="card grid" style={{ gap: 10 }}>
            <div className="label">Шаг 2: выбрать каналы</div>
            <div className="muted">Откройте раздел «Каналы», найдите свои чаты и сохраните выбранные.</div>
            <Link href="/channels" className="btn secondary">
              Перейти к каналам
            </Link>
          </div>

          <div className="card grid" style={{ gap: 10 }}>
            <div className="label">Шаг 3: тестовый пост</div>
            {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
            {message && <div className="badge" style={{ background: "#15803d" }}>{message}</div>}
            <button className="btn" onClick={sendTest} disabled={loading}>
              {loading ? "Отправляем..." : "Опубликовать тестовый пост"}
            </button>
          </div>

          <div className="card grid" style={{ gap: 10 }}>
            <div className="label">Шаг 4: новости и публикация</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn secondary" onClick={pullRss} disabled={newsLoading}>
                Обновить RSS
              </button>
              <button className="btn secondary" onClick={previewNext} disabled={newsLoading}>
                Предпросмотр следующей
              </button>
              <button className="btn" onClick={publishNext} disabled={newsLoading}>
                Опубликовать следующую
              </button>
            </div>
            {preview && (
              <div className="card" style={{ background: "#0b1224" }}>
                <div className="label">Черновик</div>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>{preview.headline}</div>
                <div dangerouslySetInnerHTML={{ __html: preview.body_html }} />
                {preview.reason_if_skip && (
                  <div className="badge" style={{ background: "#b91c1c", marginTop: 8 }}>
                    {preview.reason_if_skip}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
