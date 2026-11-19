import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import type { Model } from "../api/client";
import { key } from "../query";
import { SearchField } from "./fields";
import Select from "./Select";
import Dialog from "./Dialog";
import { AutoTextarea, ErrorNotice, QueryState } from "./ui";
import { useDraftGuard } from "./DraftProtection";
import WriteRecovery, { uncertainWrite } from "./WriteRecovery";
import { creationRequest, type CreationIntent } from "../api/creation";

export default function CardLibrary({
  projectId,
  cards,
}: {
  projectId: number;
  cards: Model<"CardOut">[];
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [chapter, setChapter] = useState("all");
  const [sort, setSort] = useState("due");
  const [open, setOpen] = useState(false);
  const [front, setFront] = useState("");
  const [back, setBack] = useState("");
  const [node, setNode] = useState("none");
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const intent = useRef<CreationIntent | undefined>(undefined);
  const sent = useRef<
    | { ids: number[]; front: string; back: string; node: number | null }
    | undefined
  >(undefined);
  const nodes = useQuery({
    queryKey: key("nodes", projectId),
    queryFn: ({ signal }) => endpoints.nodes(projectId, signal),
  });
  const create = useMutation({
    mutationFn: () => {
      sent.current = {
        ids: cards.map((card) => card.id),
        front: front.trim(),
        back: back.trim(),
        node: node === "none" ? null : Number(node),
      };
      return endpoints.createCard(
        creationRequest(intent, {
          projectId,
          nodeId: node === "none" ? null : Number(node),
          front: front.trim(),
          back: back.trim(),
          cardType: "basic",
        }),
      );
    },
    onSuccess: () => {
      intent.current = undefined;
      setOpen(false);
      setFront("");
      setBack("");
      setNotice("复习卡已保存，可以开始复习。");
      void client.invalidateQueries({ queryKey: key("cards", projectId) });
      void client.invalidateQueries({ queryKey: key("due") });
    },
  });
  const closeDraft = useDraftGuard(
    "手动复习卡",
    open && (!!front || !!back || node !== "none"),
    create.isPending,
  );
  const close = () =>
    closeDraft(() => {
      intent.current = undefined;
      setOpen(false);
      setFront("");
      setBack("");
      setNode("none");
      create.reset();
    });
  async function checkSaved() {
    const fresh = await endpoints.cards(projectId);
    client.setQueryData(key("cards", projectId), fresh);
    const value = sent.current;
    const matches = fresh.items.filter(
      (card) =>
        value &&
        !value.ids.includes(card.id) &&
        card.front === value.front &&
        card.back === value.back &&
        card.nodeId === value.node,
    );
    if (matches.length === 1) {
      intent.current = undefined;
      if (
        front.trim() === value?.front &&
        back.trim() === value.back &&
        (node === "none" ? null : Number(node)) === value.node
      ) {
        setOpen(false);
        setFront("");
        setBack("");
        setNode("none");
      }
      create.reset();
      setNotice("已核对，复习卡已保存，无需再次提交。");
      void client.invalidateQueries({ queryKey: key("due") });
    }
    return "已更新当前计划的复习卡列表，请核对问题和答案。";
  }
  const due = (card: Model<"CardOut">) =>
    !card.suspended &&
    !!card.nextReview &&
    Date.parse(card.nextReview) <= Date.now();
  const visible = cards
    .filter(
      (card) =>
        `${card.front}\n${card.back}`
          .toLowerCase()
          .includes(search.trim().toLowerCase()) &&
        (chapter === "all" ||
          (chapter === "none"
            ? card.nodeId == null
            : String(card.nodeId) === chapter)) &&
        (status === "all" ||
          (status === "due"
            ? due(card)
            : status === "suspended"
              ? card.suspended
              : !card.suspended && !due(card))),
    )
    .sort((a, b) =>
      sort === "newest"
        ? b.id - a.id
        : (a.nextReview ? Date.parse(a.nextReview) : Infinity) -
            (b.nextReview ? Date.parse(b.nextReview) : Infinity) || a.id - b.id,
    );
  return (
    <>
      <div className="section-title spread">
        <h2>当前计划的复习安排</h2>
        <button
          className="primary"
          type="button"
          onClick={() => {
            create.reset();
            setOpen(true);
          }}
        >
          手动添加复习卡
        </button>
      </div>
      <div className="feature-toolbar">
        <SearchField
          label="搜索复习卡"
          placeholder="搜索问题或答案"
          value={search}
          onChange={setSearch}
        />
        <Select
          label="卡片章节"
          value={chapter}
          onChange={setChapter}
          options={[
            { value: "all", label: "全部章节" },
            { value: "none", label: "未关联章节" },
            ...(nodes.data?.items || []).map((n) => ({
              value: String(n.id),
              label: `${n.code} ${n.title}`,
            })),
          ]}
        />
        <Select
          label="卡片状态"
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "全部状态" },
            { value: "due", label: "已到期" },
            { value: "future", label: "未到期或待安排" },
            { value: "suspended", label: "已暂停" },
          ]}
        />
        <Select
          label="卡片排序"
          value={sort}
          onChange={setSort}
          options={[
            { value: "due", label: "下次复习时间" },
            { value: "newest", label: "最新创建" },
          ]}
        />
      </div>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <p className="muted small">
        显示 {visible.length} / {cards.length} 张；已到期{" "}
        {cards.filter(due).length} 张，已暂停{" "}
        {cards.filter((c) => c.suspended).length} 张。
      </p>
      {visible.length ? (
        <ul className="review-schedule-list">
          {visible.map((item) => (
            <li key={item.id} className="review-card-detail">
              <div>
                <strong>{item.front}</strong>
                <p className="muted small">
                  {item.nodeId == null
                    ? "未关联章节"
                    : nodes.data?.items.find((n) => n.id === item.nodeId)
                        ?.title || "原章节已不可用"}
                </p>
                <details>
                  <summary>查看卡片答案</summary>
                  <p className="annotation-content">{item.back}</p>
                </details>
              </div>
              <span className="muted">
                已复习 {item.reps} 次 ·{" "}
                {item.suspended
                  ? "已暂停"
                  : item.nextReview
                    ? `下次 ${new Date(item.nextReview).toLocaleString("zh-CN")}`
                    : "待安排"}
                {due(item) && " · 已到期"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-inline">暂无符合条件的复习卡。</p>
      )}
      {open && (
        <Dialog
          title="手动添加复习卡"
          dismissible={!create.isPending}
          onClose={close}
        >
          <p className="muted small">
            自己编写问题和答案，不调用 AI。保存后按现有复习规则安排。
          </p>
          <QueryState query={nodes} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (
                front.trim() &&
                back.trim() &&
                !create.isPending &&
                !uncertainWrite(create.error) &&
                !nodes.isPending &&
                !nodes.error &&
                (node === "none" ||
                  nodes.data?.items.some((n) => String(n.id) === node))
              )
                create.mutate();
            }}
          >
            <Select
              label="关联章节"
              value={node}
              onChange={setNode}
              disabled={create.isPending}
              options={[
                { value: "none", label: "不关联章节" },
                ...(nodes.data?.items || []).map((n) => ({
                  value: String(n.id),
                  label: `${n.code} ${n.title}`,
                })),
              ]}
            />
            <label htmlFor="manual-card-front">卡片问题</label>
            <AutoTextarea
              id="manual-card-front"
              disabled={create.isPending}
              required
              maxLength={4000}
              value={front}
              onChange={(e) => setFront(e.target.value)}
            />
            <label htmlFor="manual-card-back">卡片答案</label>
            <AutoTextarea
              id="manual-card-back"
              disabled={create.isPending}
              required
              maxLength={8000}
              value={back}
              onChange={(e) => setBack(e.target.value)}
            />
            <ErrorNotice error={create.error} />
            <WriteRecovery
              error={create.error}
              onCheck={checkSaved}
              onAllowRetry={() => create.reset()}
            />
            <div className="content-actions">
              <button type="button" disabled={create.isPending} onClick={close}>
                取消
              </button>
              <button
                className="primary"
                disabled={
                  !front.trim() ||
                  !back.trim() ||
                  create.isPending ||
                  uncertainWrite(create.error) ||
                  nodes.isPending ||
                  !!nodes.error
                }
              >
                {create.isPending ? "保存中…" : "保存复习卡"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </>
  );
}
