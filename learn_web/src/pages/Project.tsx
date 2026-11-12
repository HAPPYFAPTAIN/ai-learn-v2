import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  Card,
  DailyReport,
  KNode,
  Material,
  Project as ProjectType,
  QuizSummary,
  WeekPlan,
  endpoints,
} from "../api";
import { describe } from "./Projects";

type Tab = "nodes" | "review" | "materials" | "quizzes" | "path" | "reports";

const TABS: { key: Tab; label: string }[] = [
  { key: "nodes", label: "知识节点" },
  { key: "review", label: "今日复习" },
  { key: "materials", label: "资料" },
  { key: "quizzes", label: "测验" },
  { key: "path", label: "学习路径" },
  { key: "reports", label: "每日报告" },
];

export default function Project() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const [project, setProject] = useState<ProjectType | null>(null);
  const [tab, setTab] = useState<Tab>("nodes");
  const [error, setError] = useState("");

  useEffect(() => {
    endpoints
      .project(id)
      .then(setProject)
      .catch((exc) => setError(describe(exc)));
  }, [id]);

  return (
    <section>
      <div className="section-head">
        <h1>{project?.title ?? "项目"}</h1>
        {project?.goal && <p className="muted">{project.goal}</p>}
      </div>

      <nav className="tabs">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={tab === item.key ? "tab active" : "tab"}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {error && <p className="error">{error}</p>}

      {tab === "nodes" && <NodesTab projectId={id} onError={setError} />}
      {tab === "review" && <ReviewTab onError={setError} />}
      {tab === "materials" && <MaterialsTab projectId={id} onError={setError} />}
      {tab === "quizzes" && <QuizzesTab projectId={id} onError={setError} />}
      {tab === "path" && <PathTab projectId={id} onError={setError} />}
      {tab === "reports" && <ReportsTab projectId={id} onError={setError} />}
    </section>
  );
}

type TabProps = { projectId: number; onError: (message: string) => void };

function NodesTab({ projectId, onError }: TabProps) {
  const [nodes, setNodes] = useState<KNode[]>([]);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [hours, setHours] = useState(2);
  const [stage, setStage] = useState("");

  async function load() {
    try {
      setNodes((await endpoints.nodes(projectId)).items);
    } catch (exc) {
      onError(describe(exc));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!code.trim() || !title.trim()) return;
    try {
      await endpoints.createNode(projectId, {
        code: code.trim(),
        title: title.trim(),
        stage: stage.trim(),
        estHours: Number(hours) || 1,
      });
      setCode("");
      setTitle("");
      await load();
    } catch (exc) {
      onError(describe(exc));
    }
  }

  async function setMastery(node: KNode, mastery: number) {
    try {
      await endpoints.patchNode(node.id, { mastery });
      await load();
    } catch (exc) {
      onError(describe(exc));
    }
  }

  return (
    <div>
      <form className="inline-form" onSubmit={add}>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="编号 A1" size={8} />
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="节点标题" />
        <input value={stage} onChange={(e) => setStage(e.target.value)} placeholder="阶段" size={8} />
        <input
          type="number"
          min={0.5}
          step={0.5}
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          size={5}
        />
        <button>添加</button>
      </form>

      <table className="table">
        <thead>
          <tr>
            <th>编号</th>
            <th>标题</th>
            <th>阶段</th>
            <th>预计</th>
            <th>掌握度</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => (
            <tr key={node.id}>
              <td>{node.code}</td>
              <td>{node.title}</td>
              <td>{node.stage || "-"}</td>
              <td>{node.estHours}h</td>
              <td>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.1}
                  value={node.mastery}
                  onChange={(e) => void setMastery(node, Number(e.target.value))}
                />
                <span className="muted"> {Math.round(node.mastery * 100)}%</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {nodes.length === 0 && <p className="muted">还没有节点。</p>}
    </div>
  );
}

function ReviewTab({ onError }: { onError: (message: string) => void }) {
  const [cards, setCards] = useState<Card[]>([]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    endpoints
      .dueCards(20)
      .then((data) => setCards(data.items))
      .catch((exc) => onError(describe(exc)));
  }, [onError]);

  async function rate(rating: number) {
    const card = cards[index];
    if (!card) return;
    try {
      await endpoints.review(card.id, rating);
      setIndex(index + 1);
    } catch (exc) {
      onError(describe(exc));
    }
  }

  const card = cards[index];
  if (!card) return <p className="muted">今天没有到期卡片。</p>;

  return (
    <div className="review-box">
      <p className="muted">
        {index + 1} / {cards.length}
      </p>
      <h2>{card.front}</h2>
      <details>
        <summary>看答案</summary>
        <p>{card.back}</p>
      </details>
      <div className="row">
        <button onClick={() => void rate(1)}>重来</button>
        <button onClick={() => void rate(2)}>有点难</button>
        <button onClick={() => void rate(3)}>记得</button>
        <button onClick={() => void rate(4)}>很熟</button>
      </div>
    </div>
  );
}

function MaterialsTab({ projectId, onError }: TabProps) {
  const [items, setItems] = useState<Material[]>([]);

  async function load() {
    try {
      setItems((await endpoints.materials(projectId)).items);
    } catch (exc) {
      onError(describe(exc));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await endpoints.upload(projectId, file);
      await load();
    } catch (exc) {
      onError(describe(exc));
    } finally {
      event.target.value = "";
    }
  }

  return (
    <div>
      <label className="upload">
        上传资料（≤ 50 MiB，上传后自动排队建索引）
        <input type="file" onChange={(e) => void upload(e)} />
      </label>
      <ul className="list">
        {items.map((item) => (
          <li key={item.fileId}>
            <span>{item.name || "(未命名)"}</span>
            <span className="muted">{(item.sizeBytes / 1024).toFixed(1)} KiB</span>
          </li>
        ))}
      </ul>
      {items.length === 0 && <p className="muted">还没有资料。</p>}
    </div>
  );
}

function QuizzesTab({ projectId, onError }: TabProps) {
  const [items, setItems] = useState<QuizSummary[]>([]);

  useEffect(() => {
    endpoints
      .quizzes(projectId)
      .then((data) => setItems(data.items))
      .catch((exc) => onError(describe(exc)));
  }, [projectId, onError]);

  return (
    <ul className="list">
      {items.map((quiz) => (
        <li key={quiz.id}>
          <span>
            #{quiz.id} {quiz.title || "未命名测验"}
          </span>
          <span className="muted">{quiz.quizType}</span>
        </li>
      ))}
      {items.length === 0 && <p className="muted">还没有测验。</p>}
    </ul>
  );
}

function PathTab({ projectId, onError }: TabProps) {
  const [weeks, setWeeks] = useState(8);
  const [hoursPerWeek, setHours] = useState(10);
  const [plan, setPlan] = useState<WeekPlan[] | null>(null);
  const [total, setTotal] = useState(0);

  async function build() {
    try {
      const data = await endpoints.path(projectId, weeks, hoursPerWeek);
      setPlan(data.weeks);
      setTotal(data.totalHours);
    } catch (exc) {
      onError(describe(exc));
    }
  }

  return (
    <div>
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          void build();
        }}
      >
        <label>
          周数
          <input type="number" min={1} max={52} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} />
        </label>
        <label>
          每周学时
          <input type="number" min={1} max={80} value={hoursPerWeek} onChange={(e) => setHours(Number(e.target.value))} />
        </label>
        <button>生成路径</button>
      </form>

      {plan && (
        <p className="muted">
          共 {total} 小时，{weeks} 周
        </p>
      )}
      <ol className="weeks">
        {plan?.map((week) => (
          <li key={week.index}>
            <strong>第 {week.index} 周</strong>
            <span className="muted"> {week.hours}h</span>
            <ul>
              {week.items.map((item) => (
                <li key={item.nodeId}>
                  {item.code} · {item.title}（{item.hours}h）
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ReportsTab({ projectId, onError }: TabProps) {
  const [items, setItems] = useState<DailyReport[]>([]);

  async function load() {
    try {
      setItems((await endpoints.reports(projectId)).items);
    } catch (exc) {
      onError(describe(exc));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function build() {
    try {
      await endpoints.buildReport(projectId);
      await load();
    } catch (exc) {
      onError(describe(exc));
    }
  }

  return (
    <div>
      <button onClick={() => void build()}>生成今天的报告</button>
      <ul className="list">
        {items.map((report) => (
          <li key={report.id}>
            <div>
              <strong>{report.date}</strong>
              <span className="muted">
                {" "}
                {report.studyMinutes} 分钟 · {report.cardsReviewed} 张卡片
              </span>
            </div>
            <p>{report.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
