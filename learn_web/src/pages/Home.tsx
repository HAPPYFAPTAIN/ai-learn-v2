import { Input } from "../components/fields";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
  const blocked = create.isPending || uncertainWrite(create.error);
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
      <section className="home-hero">
        <div>
          <h1>
            每一份好奇，
            <br />
            都值得一个<span>学习计划。</span>
          </h1>
          <p>
            从一个想学的目标开始，把知识化成自己的能力。
            <br />
            按自己的节奏，一步一步来。
          </p>
          <a className="button primary" href="#goal">
            开始新的学习 <Icon name="arrow" />
          </a>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="art-card">
            <span className="art-line" />
            <span className="art-line short" />
            <div className="art-progress">
              <Icon name="check" size={27} />
            </div>
            <span className="art-line" />
          </div>
          <span className="floating-label label-one">理解 · 练习 · 掌握</span>
          <span className="floating-label label-two">每天进步一点点 ↗</span>
          <span className="art-spark">✦</span>
        </div>
      </section>
      <section id="goal" className="panel goal-panel">
        <div className="section-title">
          <span className="number-label">01</span>
          <div>
            <h2>写下你的学习目标</h2>
            <p className="muted">
              你想学会什么？可以描述当前基础和希望达到的程度。
            </p>
          </div>
        </div>
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
            placeholder="比如：我想从零学习 Python，能独立写一个整理文件的小工具…"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            maxLength={8000}
            disabled={blocked}
            required
          />
          <div className="form-footer">
            <label className="inline-label">
              每周投入{" "}
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
          <p className="muted small">
            {__DEMO__
              ? "演示模式仅创建示例计划，不调用模型。"
              : "创建后自动进入工作台并用当前主模型生成学习路线，将消耗模型额度。"}
          </p>
          <ErrorNotice error={create.error} />
          <WriteRecovery
            error={create.error}
            onCheck={checkCreated}
            onAllowRetry={() => create.reset()}
          />
        </form>
      </section>
      <section className="section-space">
        <div className="section-title spread">
          <div>
            <h2>我的学习计划</h2>
          </div>
          <span className="badge">{projects.length} 个计划</span>
        </div>
        {projects.length ? (
          <ProjectCards projects={projects} />
        ) : (
          <div className="empty-inline">暂无学习计划，写下第一个目标吧。</div>
        )}
      </section>
    </>
  );
}
