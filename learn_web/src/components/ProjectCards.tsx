import { Link } from "react-router-dom";
import type { Project } from "../api";
import { Icon } from "./ui";
import DeleteLearningButton from "./DeleteLearningButton";

export default function ProjectCards({ projects }: { projects: Project[] }) {
  return (
    <div className="project-grid">
      {projects.map((p, i) => (
        <article className="project-card" key={p.id}>
          <Link className="project-card-link" to={`/study?project=${p.id}`}>
            <span className="project-symbol">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="project-main">
              <h3>{p.title}</h3>
              <p>
                每周 {p.weeklyHours} 小时 ·{" "}
                {p.status === "active" ? "学习中" : p.status}
              </p>
            </div>
            <Icon name="arrow" size={18} />
          </Link>
          <DeleteLearningButton project={p} />
        </article>
      ))}
    </div>
  );
}
