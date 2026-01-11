import React from 'react';
import type { Metadata } from 'next';
import { Space_Grotesk } from 'next/font/google';
import './globals.css';

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin', 'cyrillic'],
  variable: '--font-space',
});

export const metadata: Metadata = {
  title: 'Панель Telegram-агента новостей',
  description: 'Панель управления агентом футбольных новостей для Telegram.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={spaceGrotesk.className}>
      <body>{children}</body>
    </html>
  );
}
