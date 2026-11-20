import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { endpoints, type Project } from "../api";
import type { Model } from "../api/client";
import { generationStorageKey } from "../api/generation";
import { key } from "../query";
import Dialog from "./Dialog";
import { ErrorNotice } from "./ui";
import { uncertainWrite } from "./WriteRecovery";

export default function DeleteLearningButton({
  project,
  scope = "project",
  onDeleted,
}: {
  project: Project;
  scope?: "project" | "roadmap";
  onDeleted?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const navigate = useNavigate();
  const label = scope === "project" ? "删除学习计划" : "删除学习路线";
  const remove = useMutation({
    mutationFn: () =>
      scope === "project"
        ? endpoints.deleteProject(project.id)
        : endpoints.deleteRoadmap(project.id),
    onSuccess: async () => {
      await client.cancelQueries({ queryKey: key() });
      client.setQueryData(key("nodes", project.id), { items: [] });
      if (scope === "project")
        client.setQueryData<Model<"ProjectList">>(
          key("projects"),
          (old) =>
            old && {
              ...old,
              items: old.items.filter((p) => p.id !== project.id),
            },
        );
      sessionStorage.removeItem(generationStorageKey(project.id));
      onDeleted?.();
      setOpen(false);
      navigate(
        scope === "project" ? "/study" : `/roadmap?project=${project.id}`,
        { replace: true },
      );
      await client.invalidateQueries({ queryKey: key() });
    },
  });
  return (
    <>
      <button
        type="button"
        className="danger-button"
        aria-label={`${label}：${project.title}`}
        onClick={() => {
          remove.reset();
          setOpen(true);
        }}
      >
        {label}
      </button>
      {open && (
        <Dialog
          title={label}
          dismissible={!remove.isPending}
          onClose={() => setOpen(false)}
        >
          <p>
            确认{label}「{project.title}」？
          </p>
          <p className="muted">
            {scope === "project"
              ? "将删除整个计划、全部章节、笔记、测验、复习卡和学习记录。资料库中的原始文件保留。"
              : "将删除该路线的全部章节及关联的笔记、测验、复习卡和学习记录。学习计划、目标和资料库保留，之后可以重新生成路线。"}
          </p>
          <p>删除后无法恢复，请确认已导出需要保留的内容。</p>
          {scope === "roadmap" && (
            <p className="muted small">
              如有学习任务正在生成，请等待完成后再删除。
            </p>
          )}
          <ErrorNotice error={remove.error} />
          {uncertainWrite(remove.error) && (
            <div className="notice">
              <p>
                连接中断，暂时无法确认是否已删除。请先刷新核对结果，再进行其他操作。
              </p>
              <button
                onClick={() => {
                  sessionStorage.removeItem(generationStorageKey(project.id));
                  window.location.reload();
                }}
              >
                刷新核对结果
              </button>
            </div>
          )}
          <div className="content-actions">
            <button disabled={remove.isPending} onClick={() => setOpen(false)}>
              取消
            </button>
            <button
              className="danger-button"
              disabled={remove.isPending || uncertainWrite(remove.error)}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? "正在删除…" : "确认删除"}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
