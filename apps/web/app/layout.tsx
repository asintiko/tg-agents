import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "tg-agents — админка",
  description: "Простая панель для работы с Telegram (Telethon) и публикациями.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
