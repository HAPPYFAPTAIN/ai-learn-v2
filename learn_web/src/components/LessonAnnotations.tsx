import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import type { Model } from "../api/client";
import { key } from "../query";
import Dialog from "./Dialog";
import { AutoTextarea, ErrorNotice, QueryState } from "./ui";
import { quoteRange, readingIndex, matchingRanges } from "./quoteRange";
import RangePaint from "./RangePaint";
import { useDraftGuard } from "./DraftProtection";
import WriteRecovery, { uncertainWrite } from "./WriteRecovery";

type Draft = { selection: string; content: string; noteId?: number };
export default function LessonAnnotations({
  projectId,
  nodeId,
  children,
}: {
  projectId: number;
  nodeId: number;
  children: ReactNode;
}) {
  const reading = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState<{
    text: string;
    left: number;
    top: number;
  }>();
  const [draft, setDraft] = useState<Draft>();
  const draftInitial = useRef("");
  const sent = useRef<
    { value: Draft; ids: number[]; known: boolean } | undefined
  >(undefined);
  const [deleting, setDeleting] = useState<Model<"NoteOut">>();
  const [expanded, setExpanded] = useState(false);
  const [highlight, setHighlight] = useState(
    () => localStorage.getItem("learn.reading.highlights") === "1",
  );
  const [ranges, setRanges] = useState<Range[]>([]);
  const [unmatched, setUnmatched] = useState(0);
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const notes = useQuery({
    queryKey: key("notes", projectId),
    queryFn: ({ signal }) => endpoints.notes(projectId, signal),
    enabled: expanded || highlight,
  });
  const annotations =
    notes.data?.items.filter(
      (note) => note.nodeId === nodeId && note.selection.trim(),
    ) || [];
  const save = useMutation({
    mutationFn: (value: Draft) => {
      sent.current = {
        value: { ...value, content: value.content.trim() },
        ids: notes.data?.items.map((note) => note.id) || [],
        known: !!notes.data,
      };
      return value.noteId
        ? endpoints.updateNote(value.noteId, {
            content: value.content.trim(),
            selection: value.selection,
          })
        : endpoints.createNote(projectId, {
            nodeId,
            content: value.content.trim(),
            selection: value.selection,
          });
    },
    onSuccess: () => {
      setDraft(undefined);
      setExpanded(true);
      setHighlight(true);
      localStorage.setItem("learn.reading.highlights", "1");
      setNotice("批注已保存，可在本章批注和笔记中查看。");
      window.getSelection()?.removeAllRanges();
      void client.invalidateQueries({ queryKey: key("notes", projectId) });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => endpoints.deleteNote(id),
    onSuccess: () => {
      setDeleting(undefined);
      setNotice("批注已删除。");
      void client.invalidateQueries({ queryKey: key("notes", projectId) });
    },
  });
  const closeDraft = useDraftGuard(
    "课文批注",
    !!draft && draft.content !== draftInitial.current,
    save.isPending,
  );
  const close = () => closeDraft(() => setDraft(undefined));
  async function checkSaved() {
    const fresh = await notes.refetch();
    if (fresh.error) throw fresh.error;
    const value = sent.current;
    const matches =
      fresh.data?.items.filter(
        (note) =>
          value &&
          note.nodeId === nodeId &&
          note.content === value.value.content &&
          note.selection === value.value.selection &&
          (value.value.noteId
            ? note.id === value.value.noteId
            : value.known && !value.ids.includes(note.id)),
      ) || [];
    if (matches.length === 1 && value) {
      if (draft?.content.trim() === value.value.content) setDraft(undefined);
      save.reset();
      setExpanded(true);
      setHighlight(true);
      setNotice("已核对，批注已保存，无需再次提交。");
    }
    return "已更新本章批注，请核对引用和批注内容。";
  }
  useEffect(() => {
    let frame = 0;
    function capture() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const selected = window.getSelection();
        const root = reading.current;
        if (
          !root ||
          !selected ||
          selected.isCollapsed ||
          !selected.rangeCount
        ) {
          setSelection(undefined);
          return;
        }
        const range = selected.getRangeAt(0);
        if (
          !root.contains(range.startContainer) ||
          !root.contains(range.endContainer)
        ) {
          setSelection(undefined);
          return;
        }
        const text = selected.toString().trim();
        const rect = range.getBoundingClientRect();
        if (!text || rect.bottom < 0 || rect.top > window.innerHeight) {
          setSelection(undefined);
          return;
        }
        setSelection({
          text,
          left: Math.max(12, Math.min(window.innerWidth - 208, rect.left)),
          top:
            rect.bottom + 52 < window.innerHeight
              ? rect.bottom + 8
              : Math.max(12, rect.top - 48),
        });
      });
    }
    document.addEventListener("selectionchange", capture);
    document.addEventListener("pointerup", capture);
    document.addEventListener("keyup", capture);
    window.addEventListener("scroll", capture, true);
    window.addEventListener("resize", capture);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("selectionchange", capture);
      document.removeEventListener("pointerup", capture);
      document.removeEventListener("keyup", capture);
      window.removeEventListener("scroll", capture, true);
      window.removeEventListener("resize", capture);
    };
  }, []);
  useEffect(() => {
    const root = reading.current;
    if (!root) return;
    let frame = 0;
    function paint() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!highlight) {
          setRanges([]);
          setUnmatched(0);
          return;
        }
        const index = readingIndex(root!);
        const matched: Range[] = [];
        let missing = 0;
        for (const note of notes.data?.items || []) {
          if (note.nodeId !== nodeId || !note.selection.trim()) continue;
          const result = matchingRanges(index, note.selection, 2);
          if (result.ranges.length === 1) matched.push(result.ranges[0]);
          else missing++;
        }
        setRanges(matched);
        setUnmatched(missing);
      });
    }
    const observer = new MutationObserver((mutations) => {
      if (
        mutations.some((m) => {
          const target =
            m.target instanceof Element ? m.target : m.target.parentElement;
          if (target?.closest(".range-paint")) return false;
          const changed = [...m.addedNodes, ...m.removedNodes];
          return (
            !changed.length ||
            !changed.every(
              (n) =>
                n instanceof Element && n.classList.contains("range-paint"),
            )
          );
        })
      )
        paint();
    });
    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    paint();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [notes.data, highlight, nodeId]);
  function edit(value: Draft) {
    draftInitial.current = value.content;
    save.reset();
    setDraft(value);
    setSelection(undefined);
  }
  function locate(quote: string) {
    const found = reading.current && quoteRange(reading.current, quote);
    if (!found?.range) {
      setNotice(
        found?.ambiguous
          ? "课文中存在多处相同原文，请结合上下文查找。"
          : "当前课文中未找到这段原文，教材可能已更新；引用和批注仍保留。",
      );
      return;
    }
    found.range.startContainer.parentElement?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    });
    const selected = window.getSelection();
    selected?.removeAllRanges();
    selected?.addRange(found.range);
    setNotice("已选中课文中的对应原文。");
  }
  return (
    <>
      <div className="lesson-reading-hint">
        <span className="muted small">
          选中课文文字后可添加批注；也支持键盘选取文字。
        </span>
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "收起本章批注" : "查看本章批注"}
        </button>
      </div>
      <label className="filter-check annotation-highlight-toggle">
        <input
          type="checkbox"
          checked={highlight}
          onChange={(e) => {
            setHighlight(e.target.checked);
            localStorage.setItem(
              "learn.reading.highlights",
              e.target.checked ? "1" : "0",
            );
          }}
        />
        显示批注高亮
      </label>
      {highlight && !expanded && <QueryState query={notes} />}
      {highlight && unmatched > 0 && (
        <p className="muted small" role="status">
          {unmatched} 条批注的原文已变化或出现多次，暂不高亮；引用和批注仍保留。
        </p>
      )}
      <div className="lesson-reading" ref={reading}>
        {children}
        <RangePaint ranges={ranges} host={reading} name="le-annotations" />
      </div>
      {selection && !draft && !deleting && (
        <button
          type="button"
          className="primary annotation-selection-action"
          style={{ left: selection.left, top: selection.top }}
          onPointerDown={(event) => event.preventDefault()}
          onClick={() => edit({ selection: selection.text, content: "" })}
          disabled={selection.text.length > 4000}
        >
          {selection.text.length > 4000
            ? "请缩小选区（最多4000字）"
            : "为所选文字添加批注"}
        </button>
      )}
      {notice && (
        <p role="status" className="notice annotation-notice">
          {notice}
        </p>
      )}
      {expanded && (
        <section className="annotation-list" aria-label="本章批注">
          <h3>本章批注</h3>
          <QueryState query={notes} />
          {notes.data && !annotations.length && (
            <p className="muted">暂无批注，选中一段课文开始记录你的想法。</p>
          )}
          {annotations.map((note) => (
            <article className="annotation-card" key={note.id}>
              <blockquote>{note.selection}</blockquote>
              <p className="annotation-content">{note.content}</p>
              <div className="content-actions">
                <button type="button" onClick={() => locate(note.selection)}>
                  定位原文
                </button>
                <button
                  type="button"
                  onClick={() =>
                    edit({
                      noteId: note.id,
                      content: note.content,
                      selection: note.selection,
                    })
                  }
                >
                  编辑批注
                </button>
                <button
                  type="button"
                  onClick={() => {
                    remove.reset();
                    setDeleting(note);
                  }}
                >
                  删除批注
                </button>
              </div>
            </article>
          ))}
        </section>
      )}
      {draft && (
        <Dialog
          title={draft.noteId ? "编辑批注" : "添加批注"}
          dismissible={!save.isPending}
          onClose={close}
        >
          <p className="muted small">引用原文</p>
          <blockquote className="annotation-quote">
            {draft.selection}
          </blockquote>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (
                draft.content.trim() &&
                !save.isPending &&
                !uncertainWrite(save.error)
              )
                save.mutate(draft);
            }}
          >
            <label htmlFor="annotation-content">我的批注</label>
            <AutoTextarea
              id="annotation-content"
              disabled={save.isPending}
              autoFocus
              required
              maxLength={10000}
              value={draft.content}
              onChange={(event) =>
                setDraft({ ...draft, content: event.target.value })
              }
              placeholder="记下你的理解、疑问或一个例子…"
            />
            <ErrorNotice error={save.error} />
            <WriteRecovery
              error={save.error}
              onCheck={checkSaved}
              onAllowRetry={() => save.reset()}
            />
            <div className="content-actions annotation-dialog-actions">
              <button type="button" disabled={save.isPending} onClick={close}>
                取消
              </button>
              <button
                className="primary"
                disabled={
                  !draft.content.trim() ||
                  save.isPending ||
                  uncertainWrite(save.error)
                }
              >
                {save.isPending ? "正在保存…" : "保存批注"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {deleting && (
        <Dialog
          title="删除批注"
          dismissible={!remove.isPending}
          onClose={() => setDeleting(undefined)}
        >
          <p>删除后无法从本页面撤回，确定删除这条批注吗？</p>
          <blockquote className="annotation-quote">
            {deleting.selection}
          </blockquote>
          <ErrorNotice error={remove.error} />
          <div className="content-actions">
            <button
              type="button"
              disabled={remove.isPending}
              onClick={() => setDeleting(undefined)}
            >
              取消
            </button>
            <button
              className="primary"
              disabled={remove.isPending}
              onClick={() => remove.mutate(deleting.id)}
            >
              {remove.isPending ? "正在删除…" : "确认删除"}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
