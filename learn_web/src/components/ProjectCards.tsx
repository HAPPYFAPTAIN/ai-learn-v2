import { Link } from "react-router-dom";
import type { Project } from "../api";
import { Icon } from "./ui";

export default function ProjectCards({ projects }: { projects: Project[] }) {
  return (
    <div className="project-grid">
      {projects.map((p, i) => (
        <Link
          className="panel project-card"
          key={p.id}
          to={`/study?project=${p.id}`}
        >
          <div className="project-card-top">
            <span className="project-symbol">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="badge">
              {p.status === "active" ? "学习中" : p.status}
            </span>
          </div>
          <h3>{p.title}</h3>
          <p className="muted clamp-two">
            {p.goal || "从今天开始，慢慢积累。"}
          </p>
          <div className="project-card-bottom">
            <span>每周 {p.weeklyHours} 小时</span>
            <span>
              进入计划 <Icon name="arrow" size={16} />
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
