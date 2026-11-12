import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Project, endpoints } from "../api";

export default function Projects() {
  const [items, setItems] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const data = await endpoints.projects();
      setItems(data.items);
      setError("");
    } catch (exc) {
      setError(describe(exc));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      await endpoints.createProject({ title: title.trim() });
      setTitle("");
      await load();
    } catch (exc) {
      setError(describe(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="section-head">
        <h1>学习项目</h1>
        <form className="inline-form" onSubmit={create}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="新项目名称，例如「线性代数 12 周」"
            maxLength={200}
          />
          <button disabled={busy || !title.trim()}>创建</button>
        </form>
      </div>

      {error && <p className="error">{error}</p>}

      {items.length === 0 ? (
        <p className="muted">还没有项目。先建一个，再往里加节点、资料和测验。</p>
      ) : (
        <ul className="cards">
          {items.map((project) => (
            <li key={project.id} className="card">
              <Link to={`/p/${project.id}`}>
                <strong>{project.title}</strong>
              </Link>
              <p className="muted">{project.goal || "未填写目标"}</p>
              <span className="tag">{project.status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function describe(exc: unknown): string {
  if (exc instanceof Error) return exc.message;
  return String(exc);
}
