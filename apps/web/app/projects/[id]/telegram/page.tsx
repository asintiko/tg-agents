"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { TelegramApi, TelegramStatus } from "../../../lib/api";

export default function TelegramPage() {
  const projectId = Number(useParams()?.id);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("Тестовое сообщение");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const data = await TelegramApi.status(projectId);
      setStatus(data);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) loadStatus();
  }, [projectId, loadStatus]);

  const startQr = async () => {
    setLoading(true);
    try {
      const res = await TelegramApi.startQr(projectId);
      setQrUrl(res.qr_url);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const waitQr = async () => {
    const res = await TelegramApi.waitQr(projectId);
    if (res.needs_password) {
      setPasswordNeeded(true);
    } else {
      setPasswordNeeded(false);
      setQrUrl(null);
      await loadStatus();
    }
  };

  const sendPassword = async () => {
    await TelegramApi.password(projectId, password);
    setPassword("");
    setPasswordNeeded(false);
    await loadStatus();
  };

  const sendTest = async () => {
    setLoading(true);
    try {
      await TelegramApi.testMessage(projectId, message || "Тестовое сообщение");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const lastConnected =
    status?.last_connected_at && status.last_connected_at !== ""
      ? new Date(status.last_connected_at).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })
      : "—";

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <div className="grid" style={{ gap: 16 }}>
          <h2>Подключение Telegram (Telethon)</h2>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          <div className="card grid" style={{ gap: 10 }}>
            <div className="muted">
              Войдите через QR-код под своим пользовательским аккаунтом Telegram. 2FA пароли
              поддерживаются.
            </div>
            <button className="btn" onClick={startQr} disabled={loading}>
              Получить QR для входа
            </button>
            {qrUrl && (
              <div>
                <div className="label">Сканируйте в мобильном Telegram</div>
                <Image
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(
                    qrUrl,
                  )}`}
                  alt="QR"
                  width={200}
                  height={200}
                />
                <button className="btn secondary" onClick={waitQr}>
                  Я отсканировал QR
                </button>
              </div>
            )}
            {passwordNeeded && (
              <div className="row" style={{ gap: 8 }}>
                <input
                  className="input"
                  type="password"
                  placeholder="Пароль 2FA"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button className="btn" onClick={sendPassword}>
                  Отправить пароль
                </button>
              </div>
            )}
          </div>
          <div className="card">
            <div className="muted">Статус подключения</div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>
              {status?.status ?? "—"} / каналов: {status?.channels ?? 0}
            </div>
            <div className="muted">Последнее подключение: {lastConnected}</div>
          </div>
          <div className="card grid">
            <div className="label">Отправить тест</div>
            <input
              className="input"
              placeholder="Текст сообщения"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <button className="btn secondary" onClick={sendTest} disabled={loading}>
              Отправить
            </button>
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
