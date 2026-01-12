"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { TelegramApi, TelegramStatus } from "../../../lib/api";

export default function TelegramPage() {
  const projectId = Number(useParams()?.id);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
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

  const startPhone = async () => {
    if (!phone.trim()) {
      setError("Введите номер телефона в международном формате");
      return;
    }
    setLoading(true);
    try {
      await TelegramApi.startPhone(projectId, phone.trim());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const submitCode = async () => {
    if (!code.trim()) {
      setError("Введите код из Telegram");
      return;
    }
    setLoading(true);
    try {
      const res = await TelegramApi.submitCode(projectId, code.trim());
      if (res.status === "password_required") {
        setPasswordNeeded(true);
      } else {
        setPasswordNeeded(false);
        await loadStatus();
      }
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const sendPassword = async () => {
    setLoading(true);
    try {
      await TelegramApi.password(projectId, password);
      setPassword("");
      setPasswordNeeded(false);
      await loadStatus();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
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
      : "-";

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <div className="grid" style={{ gap: 16 }}>
          <h2>Подключение Telegram (Telethon)</h2>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}

          <div className="card grid" style={{ gap: 16 }}>
            <div className="muted">Основной способ — вход по номеру телефона. 2FA поддерживается.</div>
            <div className="card" style={{ minWidth: 360 }}>
              <div className="label">Вход по номеру</div>
              <div className="grid" style={{ gap: 8 }}>
                <input
                  className="input"
                  placeholder="+79991234567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
                <button className="btn" onClick={startPhone} disabled={loading}>
                  Отправить код на телефон
                </button>
                <input
                  className="input"
                  placeholder="Код из Telegram"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <button className="btn secondary" onClick={submitCode} disabled={loading}>
                  Подтвердить код
                </button>
              </div>
            </div>

            {passwordNeeded && (
              <div className="row" style={{ gap: 8 }}>
                <input
                  className="input"
                  type="password"
                  placeholder="Пароль 2FA"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button className="btn" onClick={sendPassword} disabled={loading}>
                  Отправить пароль
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <div className="muted">Статус подключения</div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>
              {status?.status ?? "-"} / каналов: {status?.channels ?? 0}
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
