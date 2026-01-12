"use client";

import { useEffect, useState } from "react";

import { login } from "../lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (stored) setToken(stored);
  }, []);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const tok = await login(password);
      setToken(tok);
      setPassword("");
    } catch (e) {
      setError("Неверный пароль или сервис недоступен");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="shell" style={{ maxWidth: 420, margin: "80px auto" }}>
        <div className="card grid" style={{ gap: 12 }}>
          <h2>Вход администратора</h2>
          <input
            className="input"
            type="password"
            placeholder="Пароль из переменной ADMIN_PASSWORD"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          <button className="btn" onClick={submit} disabled={loading || !password.trim()}>
            {loading ? "Авторизация..." : "Войти"}
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
