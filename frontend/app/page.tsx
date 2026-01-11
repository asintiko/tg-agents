import { StatCard } from './components/StatCard';
import type { Article, Channel } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function fetchResource<T>(path: string): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    return (await res.json()) as T;
  } catch (error) {
    console.warn(`Failed to fetch ${path}:`, error);
    return [] as unknown as T;
  }
}

export default async function HomePage() {
  const [channels, articles] = await Promise.all([
    fetchResource<Channel[]>('/channels'),
    fetchResource<Article[]>('/articles'),
  ]);

  const activeChannels = channels.filter((c) => c.active);
  const lastArticles = articles.slice(0, 5);

  return (
    <main className="container">
      <header style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <div className="pill">Автоновости по футболу</div>
          <h1 style={{ marginBottom: 4 }}>Управление Telegram-агентом</h1>
          <p className="muted">
            Следите за готовностью каналов, публикуйте дайджесты и переключайте режим работы
            (бот/пользователь) из одного интерфейса.
          </p>
        </div>
        <div className="card" style={{ maxWidth: 260 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Адрес API</div>
          <div className="muted" style={{ wordBreak: 'break-all' }}>
            {API_BASE}
          </div>
        </div>
      </header>

      <section className="grid two" style={{ marginTop: 18 }}>
        <StatCard label="Активных каналов" value={activeChannels.length} helper="Готовы к постингу" />
        <StatCard
          label="Непубликованных новостей"
          value={Math.max(0, articles.length - lastArticles.length)}
          helper="Ожидают отправки"
        />
      </section>

      <section className="grid two" style={{ marginTop: 22 }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>Каналы</h3>
            <span className="muted">{channels.length} сохранено</span>
          </div>
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Название</th>
                <th>Чат</th>
                <th>Режим</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((channel) => (
                <tr key={channel.id}>
                  <td>{channel.title}</td>
                  <td className="muted">{channel.telegram_chat_id}</td>
                  <td>
                    <span className={channel.mode === 'bot' ? 'pill' : 'pill danger'}>
                      {channel.mode === 'bot' ? 'Bot API' : 'Пользовательский сеанс'}
                    </span>
                  </td>
                  <td>{channel.active ? 'Активен' : 'Пауза'}</td>
                </tr>
              ))}
              {channels.length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Каналы не добавлены. Создайте их через backend API, чтобы начать постинг.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>Последние статьи</h3>
            <span className="muted">{lastArticles.length} шт.</span>
          </div>
          <div style={{ marginTop: 8, display: 'grid', gap: 12 }}>
            {lastArticles.map((article) => (
              <div
                key={article.id}
                style={{
                  padding: 12,
                  borderRadius: 14,
                  border: '1px solid rgba(255,255,255,0.08)',
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                <div style={{ fontWeight: 700 }}>{article.title}</div>
                <div className="muted" style={{ fontSize: 13, margin: '6px 0' }}>
                  {article.summary?.slice(0, 160) ?? 'Резюме пока нет.'}
                </div>
                <a className="pill" href={article.url} target="_blank" rel="noreferrer">
                  Открыть источник
                </a>
              </div>
            ))}
            {lastArticles.length === 0 ? (
              <div className="muted">
                Пока нет загруженных статей. Планировщик подтянет футбольные новости автоматически.
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
