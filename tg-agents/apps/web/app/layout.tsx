import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'tg-agents admin panel',
  description: 'Minimal admin surface for tg-agents.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
