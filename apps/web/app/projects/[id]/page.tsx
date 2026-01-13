"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../components/AuthGate";
import { PageShell } from "../../components/Nav";
import { ProjectNav } from "./ProjectNav";
import {
  ChannelsApi,
  FeedSource,
  ProjectStatusApi,
  ProjectStatus,
  ConfigApi,
  PlanApi,
  PreviewApi,
  PreviewResponse,
  SourcesApi,
  TelegramApi,
  TelegramStatus,
  TelegramChannel,
} from "../../lib/api";

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" });
}

export default function ProjectStartPage() {
  const projectId = Number(useParams()?.id);
  const [teleStatus, setTeleStatus] = useState<TelegramStatus | null>(null);
  const [channels, setChannels] = useState<TelegramChannel[]>([]);
  const [sources, setSources] = useState<FeedSource[]>([]);
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [tele, ch, src, stat] = await Promise.all([
        TelegramApi.status(projectId),
        ChannelsApi.list(projectId),
        SourcesApi.list(projectId),
        ProjectStatusApi.get(projectId),
      ]);
      setTeleStatus(tele);
      setChannels(ch);
      setSources(src);
      setStatus(stat);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const pullRss = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await SourcesApi.pullProject(projectId);
      setInfo(`RSS обновлены. Добавлено записей: ${res.inserted}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const generatePreview = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await PreviewApi.nextForProject(projectId);
      setPreview(res);
      setInfo("Предпросмотр готов. Проверьте текст ниже.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const publishNext = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await PreviewApi.publishForProject(projectId);
      setInfo(`Пост отправлен. ID новости: ${res.news_id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const planToday = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await PlanApi.planToday(projectId);
      setInfo(`План обновлён. Запланировано постов: ${res.planned}.`);
      const stat = await ProjectStatusApi.get(projectId);
      setStatus(stat);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const runOnce = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await PlanApi.runOnce(projectId);
      setInfo(`Автопостинг запущен вручную. Обработано: ${res.processed}.`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const refreshStatus = async () => {
    if (!projectId) return;
    try {
      const stat = await ProjectStatusApi.get(projectId);
      setStatus(stat);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const toggleAutopublish = async () => {
    if (!projectId || !status) return;
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      await ConfigApi.upsert(projectId, { autopublish_enabled: !status.autopublish_enabled });
      const stat = await ProjectStatusApi.get(projectId);
      setStatus(stat);
      setInfo(`Автопубликация ${!status.autopublish_enabled ? "включена" : "выключена"}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const enabledChannels = channels.filter((c) => c.enabled).length;
  const enabledSources = sources.filter((s) => s.enabled).length;
  const teleLabel = teleStatus?.status ?? "—";

  return (
    <PageShell>
      <AuthGate>
        <ProjectNav />
        <div className="grid" style={{ gap: 14 }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>Старт / Настройка</h2>
            <div className="muted">
              Шаги: 1) подключите Telegram по QR на вкладке «Telegram», 2) найдите и включите свои каналы, 3) обновите RSS-ленты, 4) убедитесь что автопостинг активен (карточка ниже), 5) посмотрите превью и опубликуйте.
            </div>
          </div>

          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}
          {info && <div className="badge" style={{ background: "#065f46" }}>{info}</div>}

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Автопостинг</div>
              <div style={{ fontWeight: 700 }}>
                Воркер: {status ? (status.worker_online ? "онлайн" : "офлайн") : "—"}
              </div>
            </div>
            <div className="muted">
              Автопубликация: {status ? (status.autopublish_enabled ? "включена" : "выключена") : "—"}.
              Следующий пост:{" "}
              {status
                ? status.next_planned_msk
                  ? new Date(status.next_planned_msk).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })
                  : "план отсутствует — создайте его на сегодня"
                : "загружаем..."}.
              В очереди сегодня: {status ? status.planned_today_count : "—"}, просрочено: {status ? status.due_count : "—"}.
              Последняя публикация:{" "}
              {status && status.last_published_msk
                ? new Date(status.last_published_msk).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })
                : "—"}.
              {status?.last_error && (
                <span className="badge" style={{ marginLeft: 8, background: "#b45309" }}>
                  Последняя ошибка: {status.last_error}
                </span>
              )}
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn secondary" onClick={refreshStatus} disabled={loading}>
                Обновить статус
              </button>
              <button className="btn secondary" onClick={toggleAutopublish} disabled={loading || !status}>
                Переключить автопубликацию
              </button>
              <button className="btn secondary" onClick={planToday} disabled={loading}>
                Сформировать план на сегодня
              </button>
              <button className="btn secondary" onClick={pullRss} disabled={loading}>
                Проверить RSS сейчас
              </button>
              <button className="btn secondary" onClick={runOnce} disabled={loading}>
                Запустить обработку сейчас
              </button>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              Планировщик пересчитывает очередь ежедневно в 00:05 МСК. Если очередь пуста — нажмите «Сформировать план».
              Автопубликация работает только при подключённом Telegram и активных каналах. Если воркер офлайн — перезапустите docker compose или контейнер worker. Последний heartbeat: {status?.worker_last_heartbeat_msk ? new Date(status.worker_last_heartbeat_msk).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" }) : "нет данных"}.
            </div>
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Шаг 1</div>
              <div style={{ fontWeight: 700 }}>Telegram</div>
            </div>
            <div className="muted">Статус: {teleLabel}. Если нет подключения — войдите по QR.</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <Link href={`/projects/${projectId}/telegram`} className="btn">
                Подключить / Переподключить
              </Link>
              <button className="btn secondary" onClick={load} disabled={loading}>
                Обновить статус
              </button>
            </div>
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Шаг 2</div>
              <div style={{ fontWeight: 700 }}>Каналы</div>
            </div>
            <div className="muted">Включено каналов: {enabledChannels} из {channels.length}.</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <Link href={`/projects/${projectId}/channels`} className="btn">
                Выбрать каналы
              </Link>
            </div>
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Шаг 3</div>
              <div style={{ fontWeight: 700 }}>Источники</div>
            </div>
            <div className="muted">
              Активных RSS: {enabledSources} из {sources.length}. Обновите ленту перед генерацией поста.
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn" onClick={pullRss} disabled={loading}>
                Проверить RSS сейчас
              </button>
              <Link href={`/projects/${projectId}/sources`} className="btn secondary">
                Управлять RSS
              </Link>
            </div>
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Шаг 4</div>
              <div style={{ fontWeight: 700 }}>Превью</div>
            </div>
            <div className="muted">Сгенерируйте черновик поста и проверьте текст.</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn" onClick={generatePreview} disabled={loading}>
                Сгенерировать превью поста
              </button>
            </div>
            {preview && (
              <div className="card" style={{ background: "#0b1224" }}>
                <div className="label">Заголовок</div>
                <div style={{ fontWeight: 700 }}>{preview.headline}</div>
                <div className="label" style={{ marginTop: 8 }}>Текст</div>
                <div dangerouslySetInnerHTML={{ __html: preview.body_html }} />
                <div className="label" style={{ marginTop: 8 }}>Картинка</div>
                <div className="muted">{preview.image_query || "—"}</div>
                {preview.reason_if_skip && (
                  <div className="badge" style={{ background: "#b45309", marginTop: 8 }}>
                    Возможный пропуск: {preview.reason_if_skip}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="card grid" style={{ gap: 12 }}>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <div className="badge" style={{ background: "#1f2937" }}>Шаг 5</div>
              <div style={{ fontWeight: 700 }}>Публикация</div>
            </div>
            <div className="muted">
              Отправьте следующий пост в выбранные каналы. Перед этим убедитесь, что Telegram подключен.
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn" onClick={publishNext} disabled={loading || enabledChannels === 0}>
                Опубликовать следующий пост
              </button>
              <Link href={`/projects/${projectId}/posts`} className="btn secondary">
                Смотреть логи
              </Link>
            </div>
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
