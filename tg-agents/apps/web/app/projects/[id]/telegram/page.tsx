"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { TelegramApi, TelegramStatus } from "../../../lib/api";

export default function TelegramPage() {
  const projectId = Number(useParams()?.id);
  const [mode, setMode] = useState<"bot" | "user">("bot");
  const [botToken, setBotToken] = useState("");
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const data = await TelegramApi.status(projectId);
      setStatus(data);
      setMode((data.mode as "bot" | "user" | null) ?? "bot");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    if (projectId) loadStatus();
  }, [projectId]);

  const connectBot = async () => {
    setLoading(true);
    try {
      const data = await TelegramApi.connectBot(projectId, botToken);
      setStatus(data);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

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
      await TelegramApi.testMessage(projectId, message || "Test message");
      setError(null);
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
        <div className="grid" style={{ gap: 16 }}>
          <h2>Подключение Telegram</h2>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          <div className="row" style={{ gap: 10 }}>
            <button
              className="btn secondary"
              onClick={() => setMode("bot")}
              style={{ background: mode === "bot" ? "#0f172a" : "#1f2937" }}
            >
              Режим бота
            </button>
            <button
              className="btn secondary"
              onClick={() => setMode("user")}
              style={{ background: mode === "user" ? "#0f172a" : "#1f2937" }}
            >
              Режим пользователя
            </button>
          </div>
          {mode === "bot" && (
            <div className="card grid">
              <div className="label">Токен бота</div>
              <input
                className="input"
                placeholder="123:ABC"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
              />
              <button className="btn" onClick={connectBot} disabled={loading}>
                {loading ? "Подключаю..." : "Подключить бота"}
              </button>
            </div>
          )}
          {mode === "user" && (
            <div className="card grid" style={{ gap: 10 }}>
              <button className="btn" onClick={startQr} disabled={loading}>
                Начать вход по QR
              </button>
              {qrUrl && (
                <div>
                  <div className="label">Сканируйте в Telegram</div>
                  <Image
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(
                      qrUrl,
                    )}`}
                    alt="QR"
                    width={200}
                    height={200}
                  />
                  <button className="btn secondary" onClick={waitQr}>
                    Я просканировал
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
          )}
          <div className="card">
            <div className="muted">Статус</div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>
              {status ? `${status.mode ?? "-"} / ${status.status ?? "-"}` : "Неизвестно"}
            </div>
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
