"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AuthGate } from "../../../components/AuthGate";
import { PageShell } from "../../../components/Nav";
import { ProjectNav } from "../ProjectNav";
import { PostsApi, Post, PreviewApi, PreviewResponse, SourcesApi } from "../../../lib/api";

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" });
}

export default function PostsPage() {
  const projectId = Number(useParams()?.id);
  const [posts, setPosts] = useState<Post[]>([]);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await PostsApi.list(projectId);
      setPosts(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const pullFeeds = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await SourcesApi.pullProject(projectId);
      setPreview(null);
      await load();
      alert(`Загружено записей: ${res.inserted}`);
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
    try {
      const res = await PreviewApi.nextForProject(projectId);
      setPreview(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const generatePredictionPreview = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await PreviewApi.predictionPreview(projectId);
      setPreview(res);
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
    try {
      await PreviewApi.publishForProject(projectId);
      setPreview(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const publishPrediction = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      await PreviewApi.publishPrediction(projectId);
      setPreview(null);
      await load();
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
        <div className="grid" style={{ gap: 12 }}>
          <div
            className="row"
            style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}
          >
            <div>
              <h2 style={{ margin: 0 }}>Публикации / Логи</h2>
              <div className="muted">Шаги: подтянуть новости → сгенерировать превью → опубликовать.</div>
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn" onClick={pullFeeds} disabled={loading}>
                Загрузить новости сейчас
              </button>
              <button className="btn secondary" onClick={generatePreview} disabled={loading}>
                Сгенерировать превью
              </button>
              <button className="btn secondary" onClick={generatePredictionPreview} disabled={loading}>
                Сгенерировать прогноз (превью)
              </button>
              <button className="btn secondary" onClick={publishNext} disabled={loading}>
                Опубликовать следующий
              </button>
              <button className="btn secondary" onClick={publishPrediction} disabled={loading}>
                Опубликовать прогноз сейчас
              </button>
              <button className="btn secondary" onClick={load} disabled={loading}>
                Обновить
              </button>
            </div>
          </div>
          {error && <div className="badge" style={{ background: "#b91c1c" }}>{error}</div>}

          {preview && (
            <div className="card grid" style={{ gap: 8 }}>
              <div className="label">Предпросмотр поста</div>
              <div style={{ fontWeight: 700 }}>{preview.headline}</div>
              <div dangerouslySetInnerHTML={{ __html: preview.body_html }} />
              <div className="muted">Изображение/запрос: {preview.image_query || "—"}</div>
              {preview.reason_if_skip && (
                <div className="badge" style={{ background: "#b45309" }}>
                  Причина пропуска: {preview.reason_if_skip}
                </div>
              )}
            </div>
          )}

          <div className="card">
            {posts.length === 0 && <div className="muted">Нет постов</div>}
            {posts.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Тип</th>
                    <th>Статус</th>
                    <th>Запланировано (МСК)</th>
                    <th>Опубликовано (МСК)</th>
                    <th>Ошибка</th>
                  </tr>
                </thead>
                <tbody>
                  {posts.map((p) => (
                    <tr key={p.id}>
                      <td>{p.id}</td>
                      <td>{p.kind === "prediction" ? "Прогноз" : "Новость"}</td>
                      <td>{p.status}</td>
                      <td>{formatDate(p.planned_at)}</td>
                      <td>{formatDate(p.published_at)}</td>
                      <td style={{ maxWidth: 300, whiteSpace: "pre-wrap" }}>{p.error ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </AuthGate>
    </PageShell>
  );
}
