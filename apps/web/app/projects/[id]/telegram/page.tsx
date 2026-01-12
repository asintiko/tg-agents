"use client";

import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import {
  TelegramApi,
  TelegramAuthInfo,
  TelegramGlobalApi,
  TelegramStatus,
} from "../../../lib/api";

export default function TelegramPage() {
  const projectId = Number(useParams()?.id);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [globalStatus, setGlobalStatus] = useState<TelegramAuthInfo | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("Тестовое сообщение");
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const qrWaitActive = useRef(false);

  const stopQrWait = useCallback(() => {
    qrWaitActive.current = false;
    setPolling(false);
  }, []);

  const loadStatus = useCallback(async () => {
    if (!projectId) return;
    try {
      const [proj, global] = await Promise.all([
        TelegramApi.status(projectId),
        TelegramGlobalApi.status(),
      ]);
      setStatus(proj);
      setGlobalStatus(global);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) loadStatus();
    return () => stopQrWait();
  }, [projectId, loadStatus, stopQrWait]);

  useEffect(() => {
    if (globalStatus?.status === "password_required") {
      setPasswordNeeded(true);
    } else if (globalStatus?.status === "connected") {
      setPasswordNeeded(false);
    }
  }, [globalStatus]);

  const waitForQr = useCallback(async () => {
    if (!projectId) return;
    qrWaitActive.current = true;
    setPolling(true);
    try {
      const res = await TelegramApi.waitQr(projectId);
      if (!qrWaitActive.current) return;
      if (res.connected) {
        setQrUrl(null);
        setPasswordNeeded(false);
        setInfo("Телеграм подключён по QR");
        await loadStatus();
      } else if (res.needs_password) {
        setPasswordNeeded(true);
        setInfo("Введите пароль 2FA для завершения входа");
      } else {
        setError("QR-код истёк, запросите новый");
        setQrUrl(null);
      }
    } catch (e) {
      if (qrWaitActive.current) setError((e as Error).message);
    } finally {
      stopQrWait();
    }
  }, [projectId, loadStatus, stopQrWait]);

  const startQr = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    setPasswordNeeded(false);
    stopQrWait();
    try {
      const res = await TelegramApi.startQr(projectId);
      if (res.status === "connected") {
        setQrUrl(null);
        setInfo("Аккаунт уже подключен");
        await loadStatus();
        return;
      }
      setQrUrl(res.qr_url ?? null);
      setInfo("Сканируйте QR через Telegram → Настройки → Устройства");
      void waitForQr();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const startPhone = async () => {
    if (!projectId) return;
    if (!phone.trim()) {
      setError("Введите номер телефона в международном формате");
      return;
    }
    setLoading(true);
    setError(null);
    setInfo(null);
    setPasswordNeeded(false);
    stopQrWait();
    try {
      await TelegramApi.startPhone(projectId, phone.trim());
      setInfo("Код отправлен, проверьте Telegram");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const submitCode = async () => {
    if (!projectId) return;
    if (!code.trim()) {
      setError("Введите код из Telegram");
      return;
    }
    setLoading(true);
    setError(null);
    setInfo(null);
    stopQrWait();
    try {
      const res = await TelegramApi.submitCode(projectId, code.trim());
      if (res.status === "password_required") {
        setPasswordNeeded(true);
        setInfo("Введите пароль 2FA для завершения входа");
      } else {
        setPasswordNeeded(false);
        setInfo("Код принят, Telegram подключён");
        await loadStatus();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const sendPassword = async () => {
    if (!projectId) return;
    if (!password.trim()) {
      setError("Введите пароль 2FA");
      return;
    }
    setLoading(true);
    setError(null);
    setInfo(null);
    stopQrWait();
    try {
      await TelegramApi.password(projectId, password.trim());
      setPassword("");
      setPasswordNeeded(false);
      setQrUrl(null);
      setInfo("Пароль принят, Telegram подключён");
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
    setInfo(null);
    stopQrWait();
    try {
      await TelegramGlobalApi.resetSession();
      setQrUrl(null);
      setPasswordNeeded(false);
      setInfo("Сессия сброшена, выполните вход заново");
      await loadStatus();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const sendTest = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      await TelegramApi.testMessage(projectId, message || "Тестовое сообщение");
      setInfo("Тестовое сообщение отправлено");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const lastConnectedRaw =
    globalStatus?.last_connected_at && globalStatus.last_connected_at !== ""
      ? globalStatus.last_connected_at
      : status?.last_connected_at && status.last_connected_at !== ""
        ? status.last_connected_at
        : null;
  const lastConnected = lastConnectedRaw
    ? new Date(lastConnectedRaw).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })
    : "-";
  const me = globalStatus?.me;
  const accountLabel = me
    ? [me.username, me.phone, me.id ? `id ${me.id}` : null].filter(Boolean).join(" / ")
    : "—";
  const connectionLabel = globalStatus?.status ?? status?.status ?? "-";

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <div className="grid" style={{ gap: 16 }}>
          <h2>Подключение Telegram (Telethon)</h2>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          {info && <div className="badge" style={{ background: "#065f46" }}>{info}</div>}

          <div className="card grid" style={{ gap: 12 }}>
            <div className="muted">Статус подключения</div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>
              {connectionLabel} / каналов: {status?.channels ?? 0}
            </div>
            <div className="muted">Аккаунт: {accountLabel}</div>
            <div className="muted">Последнее подключение: {lastConnected}</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn secondary" onClick={loadStatus} disabled={loading}>
                Обновить статус
              </button>
              <button className="btn secondary" onClick={resetSession} disabled={loading}>
                Сбросить сессию
              </button>
            </div>
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="muted">
              Основной способ — вход по QR. Если не работает, используйте резервный вход по номеру.
            </div>
            <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
              <div className="card" style={{ minWidth: 320, flex: 1 }}>
                <div className="label">Вход по QR</div>
                <div className="grid" style={{ gap: 8 }}>
                  <button className="btn" onClick={startQr} disabled={loading || polling}>
                    {polling ? "Ждём подтверждения..." : "Получить QR"}
                  </button>
                  {qrUrl && (
                    <div className="grid" style={{ gap: 8, alignItems: "center" }}>
                      <div style={{ display: "flex", justifyContent: "center" }}>
                        <QRCodeSVG value={qrUrl} size={220} />
                      </div>
                      <div className="muted" style={{ textAlign: "center" }}>
                        Откройте Telegram → Настройки → Устройства → Подключить устройство (QR)
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="card" style={{ minWidth: 360, flex: 1 }}>
                <div className="label">Резерв: вход по номеру</div>
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
            </div>

            {passwordNeeded && (
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <input
                  className="input"
                  type="password"
                  placeholder="Пароль 2FA"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  className="btn"
                  onClick={sendPassword}
                  disabled={loading || !password.trim()}
                >
                  Отправить пароль
                </button>
              </div>
            )}
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
