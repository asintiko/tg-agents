"use client";

import { useEffect, useState } from "react";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const tok = stored ?? "public";
    if (typeof window !== "undefined") {
      localStorage.setItem("token", tok);
    }
    setToken(tok);
  }, []);

  if (!token) return null;
  return <>{children}</>;
}
