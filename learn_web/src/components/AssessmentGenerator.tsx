import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api";
import { key } from "../query";
import Select from "./Select";
import { Input } from "./fields";
import { QueryState } from "./ui";
import GenerationAction from "./GenerationAction";

export default function AssessmentGenerator({
  projectId,
  kind,
}: {
  projectId: number;
  kind: "quiz" | "cards";
}) {
  const nodes = useQuery({
    queryKey: key("nodes", projectId),
    queryFn: ({ signal }) => endpoints.nodes(projectId, signal),
  });
  const [selected, select] = useState<number[]>([]);
  const [count, setCount] = useState(5);
  const [qtype, setType] = useState<
    "mixed" | "choice" | "fill" | "short" | "practice"
  >("mixed");
  const ids = selected.filter((id) =>
    nodes.data?.items.some((n) => n.id === id),
  );
  return (
    <section className="panel assessment-generator">
      <h2>{kind === "quiz" ? "创建新测验" : "创建复习卡"}</h2>
      <p className="muted">
        {kind === "quiz"
          ? "选择本次查漏的章节，生成后可开始作答。"
          : "选择一个章节，从学习内容中提炼问答卡片。"}
      </p>
      <QueryState query={nodes} />
      {nodes.data && (
        <>
          {!nodes.data.items.length ? (
            <p>暂无章节，请先生成学习路线。</p>
          ) : (
            <>
              {kind === "cards" ? (
                <Select
                  label="复习章节"
                  value={ids[0]}
                  options={nodes.data.items.map((n) => ({
                    value: n.id,
                    label: `${n.code} ${n.title}`,
                  }))}
                  onChange={(id) => select([id])}
                />
              ) : (
                <fieldset className="assessment-scope">
                  <legend>测验范围（最多 20 个章节）</legend>
                  {nodes.data.items.map((n) => (
                    <label key={n.id}>
                      <input
                        type="checkbox"
                        checked={ids.includes(n.id)}
                        disabled={!ids.includes(n.id) && ids.length >= 20}
                        onChange={(e) =>
                          select(
                            e.target.checked
                              ? [...ids, n.id]
                              : ids.filter((id) => id !== n.id),
                          )
                        }
                      />
                      {n.code} {n.title}
                    </label>
                  ))}
                </fieldset>
              )}
              <div className="form-grid">
                <label>
                  生成数量
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    step={1}
                    value={count}
                    onChange={(e) =>
                      setCount(
                        Math.max(
                          1,
                          Math.min(20, Math.trunc(Number(e.target.value) || 1)),
                        ),
                      )
                    }
                  />
                </label>
                {kind === "quiz" && (
                  <Select
                    label="题型"
                    value={qtype}
                    onChange={setType}
                    options={[
                      { value: "mixed", label: "混合题型" },
                      { value: "choice", label: "选择题" },
                      { value: "fill", label: "填空题" },
                      { value: "short", label: "简答题" },
                      { value: "practice", label: "实操题" },
                    ]}
                  />
                )}
              </div>
            </>
          )}
          <GenerationAction
            projectId={projectId}
            assessment={{ kind, nodeIds: ids, count, qtype }}
          />
        </>
      )}
    </section>
  );
}
