import { Input } from "../components/fields";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import { AutoTextarea, ErrorNotice, Icon } from "../components/ui";
import ProjectCards from "../components/ProjectCards";
import { generationStorageKey } from "../api/generation";
import { creationRequest, type CreationIntent } from "../api/creation";
import type { Model } from "../api/client";
import WriteRecovery, { uncertainWrite } from "../components/WriteRecovery";
export default function Home() {
  const { projects } = useProject();
  const navigate = useNavigate();
  const { hash } = useLocation();
  useEffect(() => {
    if (hash !== "#goal") return;
    document.getElementById("goal")?.scrollIntoView({ block: "start" });
    document.getElementById("goal-text")?.focus({ preventScroll: true });
  }, [hash]);
  const models = useQuery({
    queryKey: key("models"),
    queryFn: ({ signal }) => endpoints.models(signal),
    enabled: !__DEMO__,
  });
  const missingModel =
    !__DEMO__ && models.isSuccess && !models.data.selectedModel;
  const client = useQueryClient();
  const [goal, setGoal] = useState("");
  const [hours, setHours] = useState(5);
  const intent = useRef<CreationIntent | undefined>(undefined);
  async function openProject(p: Model<"ProjectCreated">) {
    // Remember the original job before navigation; recovery never enqueues it again.
    if (p.generation)
      sessionStorage.setItem(generationStorageKey(p.id), p.generation.jobId);
    await client.invalidateQueries({ queryKey: key("projects") });
    intent.current = undefined;
    navigate(`/study?project=${p.id}`, {
      state: {
        generationProjectId: p.id,
        generationJobId: p.generation?.jobId,
      },
    });
  }
  const create = useMutation({
    mutationFn: () =>
      endpoints.createProject(
        creationRequest(intent, {
          title: goal.trim().slice(0, 60),
          goal: goal.trim(),
          weeklyHours: hours,
          generateRoadmap: !__DEMO__,
        }),
      ),
    onSuccess: openProject,
  });
  const blocked =
    create.isPending || uncertainWrite(create.error) || missingModel;
  async function checkCreated() {
    if (!intent.current) return "本次创建尚未提交。";
    const result = await endpoints.projectCreation(intent.current.requestId);
    if (result) {
      await openProject(result);
      return "已找到本次计划，正在进入学习工作台。";
    }
    return "尚未查到本次创建结果。允许重试后，将继续本次创建。";
  }
  return (
    <>
      <section className="home-command">
        <p className="eyebrow">AI LEARN / 学习空间</p>
        <h1>
          每一份好奇，
          <span>都从一个目标开始。</span>
        </h1>
        <p className="home-lede">写下想学会的事，把它拆成可以完成的章节。</p>
        <section id="goal" className="home-start" aria-label="创建学习计划">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (goal.trim() && !blocked) create.mutate();
            }}
          >
            <label htmlFor="goal-text" className="sr-only">
              学习目标
            </label>
            <AutoTextarea
              id="goal-text"
              placeholder="想学什么？例如：用 Python 做一个整理文件的小工具"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              maxLength={5000}
              disabled={blocked}
              required
            />
            <div className="home-start-footer">
              <label className="inline-label">
                每周{" "}
                <Input
                  type="number"
                  aria-label="每周投入小时"
                  min={0.5}
                  max={80}
                  step={0.5}
                  value={hours}
                  disabled={blocked}
                  onChange={(e) => setHours(Number(e.target.value))}
                  required
                />{" "}
                小时
              </label>
              <button className="primary" disabled={!goal.trim() || blocked}>
                {create.isPending ? "正在创建…" : "创建学习计划"}
                <Icon name="arrow" />
              </button>
            </div>
            {missingModel && (
              <p role="alert">
                请先到「模型设置」选择主模型。{" "}
                <Link className="button" to="/models">
                  前往模型设置
                </Link>
              </p>
            )}
            <ErrorNotice error={create.error} />
            <WriteRecovery
              error={create.error}
              onCheck={checkCreated}
              onAllowRetry={() => create.reset()}
            />
          </form>
        </section>
      </section>
      <section className="home-plans" aria-labelledby="home-plans-title">
        <div className="home-plans-heading">
          <h2 id="home-plans-title">我的学习计划</h2>
          <span>{projects.length}</span>
        </div>
        {projects.length ? (
          <ProjectCards projects={projects} />
        ) : (
          <div className="empty-inline">还没有学习计划。</div>
        )}
      </section>
    </>
  );
}
