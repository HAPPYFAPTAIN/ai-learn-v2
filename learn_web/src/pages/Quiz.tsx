import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { watchJob } from "../api/jobs";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import AssessmentGenerator from "../components/AssessmentGenerator";
import { Empty, ErrorNotice, PageHeading, QueryState } from "../components/ui";
export default function Quiz() {
  const { id } = useProject();
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get("quiz")) || 0;
  const select = (quiz: number) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("quiz", String(quiz));
      return next;
    });
  const list = useQuery({
    queryKey: key("quizzes", id),
    queryFn: ({ signal }) => endpoints.quizzes(id, signal),
    enabled: !!id,
  });
  return (
    <>
      <PageHeading
        title="查漏测验"
        description="不是为了分数，而是发现下一步值得巩固的地方。"
      />
      {!id ? (
        <Empty title="暂无学习目标" />
      ) : (
        <>
          <AssessmentGenerator key={id} projectId={id} kind="quiz" />
          <QueryState query={list} />
          {list.data && (
            <>
              <div className="quiz-layout">
                <div className="panel">
                  <h2>我的测验</h2>
                  {list.data.items.length ? (
                    list.data.items.map((q) => (
                      <button
                        className={`list-button ${selected === q.id ? "selected" : ""}`}
                        key={q.id}
                        onClick={() => select(q.id)}
                      >
                        {q.title || "未命名测验"}
                        <small>
                          {new Date(q.createdAt).toLocaleDateString("zh-CN")}
                        </small>
                      </button>
                    ))
                  ) : (
                    <p className="empty-inline">暂无测验。</p>
                  )}
                </div>
                {list.data.items.some((q) => q.id === selected) ? (
                  <QuizSheet key={selected} id={selected} />
                ) : (
                  <div className="panel">
                    <Empty
                      title="准备好，检查一下理解"
                      description="选择一份已有测验开始作答。"
                      action={false}
                    />
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
function QuizSheet({ id }: { id: number }) {
  const client = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [job, setJob] = useState<JobProgress>();
  const [jobError, setJobError] = useState<Error>();
  const [reconnecting, setReconnecting] = useState(false);
  const quiz = useQuery({
    queryKey: key("quiz", id),
    queryFn: ({ signal }) => endpoints.quiz(id, signal),
  });
  const submit = useMutation({
    mutationFn: () => endpoints.submitQuiz(id, answers),
    onSuccess: (value) => {
      setJob(undefined);
      setJobError(undefined);
      client.setQueryData(key("quiz-grade-job", id), value);
    },
  });
  const result = useQuery({
    queryKey: key("quiz-result", id),
    queryFn: ({ signal }) => endpoints.quizResult(id, signal),
  });
  const current = useQuery({
    queryKey: key("quiz-grade-job", id),
    queryFn: ({ signal }) => endpoints.quizGradeJob(id, signal),
  });
  const jobId = current.data?.jobId;
  useEffect(() => {
    if (!jobId) return;
    return watchJob(
      jobId,
      (value) => {
        setJob(value);
        if (value.state === "done") {
          void client.invalidateQueries({ queryKey: key("quiz-result", id) });
          void client.invalidateQueries({ queryKey: key("nodes") });
          void client.invalidateQueries({ queryKey: key("summary") });
        }
      },
      (state) => setReconnecting(state === "reconnecting"),
      setJobError,
    );
  }, [jobId, id, client]);
  const state = job && job.jobId === jobId ? job.state : current.data?.state;
  const pending = submit.isPending || state === "queued" || state === "running";
  const blocked =
    pending ||
    !!result.data ||
    current.isPending ||
    result.isPending ||
    !!current.error ||
    !!result.error;
  return (
    <section className="panel">
      <QueryState query={quiz} />
      <QueryState query={result} />
      <QueryState query={current} />
      {quiz.data && (
        <>
          <h2>{quiz.data.title}</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!blocked) submit.mutate();
            }}
          >
            <fieldset disabled={blocked} className="quiz-fields">
              {quiz.data.questions.map((q, i) => (
                <label key={q.id} className="quiz-question">
                  <strong>
                    {i + 1}. {q.stem}
                  </strong>
                  {q.options.length > 0 && (
                    <span className="muted">
                      {q.options.map(String).join(" · ")}
                    </span>
                  )}
                  <textarea
                    aria-label={`第 ${i + 1} 题答案`}
                    rows={q.qtype === "choice" ? 1 : 3}
                    maxLength={8000}
                    value={
                      result.data?.results.find((r) => r.questionId === q.id)
                        ?.userAnswer ||
                      answers[q.id] ||
                      ""
                    }
                    onChange={(e) =>
                      setAnswers({ ...answers, [q.id]: e.target.value })
                    }
                    required
                  />
                </label>
              ))}
            </fieldset>
            <button
              className="primary"
              disabled={blocked || !quiz.data.questions.length}
            >
              {pending ? "批改中…" : result.data ? "已提交" : "提交答案"}
            </button>
            <ErrorNotice error={submit.error} />
            <ErrorNotice
              error={jobError || (job?.error ? new Error(job.error) : null)}
            />
            {pending && (
              <p role="status">
                {state === "queued"
                  ? "答案已保存，等待批改。"
                  : "正在批改答案，可离开此页后回来查看。"}
                {reconnecting && "正在重新连接…"}
              </p>
            )}
            {!pending && !result.data && (
              <p className="muted small">
                选择题直接判分；填空、简答和实操题按需由主模型批改，将消耗模型额度。
              </p>
            )}
          </form>
          {result.data && (
            <div className="quiz-results" role="status">
              <h3>
                答对 {result.data.correct} / {result.data.total} 题
              </h3>
              {result.data.results.map((r, i) => (
                <div key={r.questionId} className="note-card">
                  <strong>
                    第 {i + 1} 题 · {r.correct ? "回答正确" : "需要巩固"}
                  </strong>
                  <p>参考答案：{r.expected}</p>
                  {r.feedback && <p>{r.feedback}</p>}
                  <p className="muted">{r.explanation}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
