import { lazy, Suspense, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type KNode } from "../api";
import type { Model } from "../api/client";
import { key } from "../query";
import { useProject } from "./ProjectContext";
import Select from "./Select";
import Dialog from "./Dialog";
import { SearchField } from "./fields";
import { AutoTextarea, ErrorNotice, QueryState } from "./ui";
import { notesMarkdown, saveMarkdown } from "./contentExport";
import { useDraftGuard } from "./DraftProtection";
import WriteRecovery, { uncertainWrite } from "./WriteRecovery";
import { creationRequest, type CreationIntent } from "../api/creation";
const Markdown = lazy(() => import("./Markdown"));
export default function NotesManager({ node }: { node: KNode }) {
  const { id, project } = useProject();
  const client = useQueryClient();
  const createForm = useRef<HTMLFormElement>(null);
  const intent = useRef<CreationIntent | undefined>(undefined);
  const [content, setContent] = useState("");
  const [search, setSearch] = useState("");
  const [chapter, setChapter] = useState(String(node.id));
  const [kind, setKind] = useState("all");
  const [editing, setEditing] = useState<Model<"NoteOut">>();
  const [draft, setDraft] = useState("");
  const [deleting, setDeleting] = useState<Model<"NoteOut">>();
  const [notice, setNotice] = useState("");
  const submittedCreate = useRef<
    { ids: number[]; content: string; known: boolean } | undefined
  >(undefined);
  const submittedEdit = useRef<
    { content: string; editing: number } | undefined
  >(undefined);
  const notes = useQuery({
    queryKey: key("notes", id),
    queryFn: ({ signal }) => endpoints.notes(id, signal),
  });
  const nodes = useQuery({
    queryKey: key("nodes", id),
    queryFn: ({ signal }) => endpoints.nodes(id, signal),
  });
  const changed = () => {
    void client.invalidateQueries({ queryKey: key("notes", id) });
  };
  const create = useMutation({
    mutationFn: () => {
      submittedCreate.current = {
        ids: notes.data?.items.map((n) => n.id) || [],
        content: content.trim(),
        known: !!notes.data,
      };
      return endpoints.createNote(
        id,
        creationRequest(intent, {
          nodeId: node.id,
          content: content.trim(),
        }),
      );
    },
    onSuccess: () => {
      intent.current = undefined;
      setContent("");
      createForm.current?.reset();
      setNotice("笔记已保存。");
      changed();
    },
  });
  const edit = useMutation({
    mutationFn: () => {
      submittedEdit.current = { content: draft.trim(), editing: editing!.id };
      return endpoints.updateNote(editing!.id, { content: draft.trim() });
    },
    onSuccess: () => {
      setEditing(undefined);
      setNotice("笔记已更新。");
      changed();
    },
  });
  const remove = useMutation({
    mutationFn: () => endpoints.deleteNote(deleting!.id),
    onSuccess: () => {
      setDeleting(undefined);
      setNotice("笔记已删除。");
      changed();
    },
  });
  useDraftGuard("新笔记", !!content, create.isPending);
  const closeEdit = useDraftGuard(
    "笔记修改",
    !!editing && draft !== editing.content,
    edit.isPending,
  );
  async function checkSaved(kind: "create" | "edit") {
    const result = await notes.refetch();
    if (result.error) throw result.error;
    const sent =
      kind === "create" ? submittedCreate.current : submittedEdit.current;
    const matches =
      result.data?.items.filter(
        (note) =>
          sent &&
          note.content === sent.content &&
          ("editing" in sent
            ? note.id === sent.editing
            : sent.known &&
              note.nodeId === node.id &&
              !note.selection &&
              !sent.ids.includes(note.id)),
      ) || [];
    if (matches.length === 1 && sent) {
      if ("editing" in sent) {
        if (draft.trim() === sent.content) setEditing(undefined);
        edit.reset();
      } else {
        intent.current = undefined;
        if (content.trim() === sent.content) {
          setContent("");
          createForm.current?.reset();
        }
        create.reset();
      }
      setNotice("已核对，本次笔记已保存，无需再次提交。");
    }
    return "已更新笔记列表，请核对正文和更新时间。";
  }
  const visible = (notes.data?.items || [])
    .filter(
      (note) =>
        (chapter === "all" || String(note.nodeId) === chapter) &&
        (kind === "all" ||
          (kind === "annotation"
            ? !!note.selection.trim()
            : !note.selection.trim())) &&
        `${note.content}\n${note.selection}`
          .toLowerCase()
          .includes(search.trim().toLowerCase()),
    )
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || b.id - a.id);
  return (
    <section className="notes-manager" aria-label="笔记管理">
      <form
        ref={createForm}
        onSubmit={(e) => {
          e.preventDefault();
          if (
            content.trim() &&
            !create.isPending &&
            !uncertainWrite(create.error)
          )
            create.mutate();
        }}
      >
        <label htmlFor="lesson-note">记下你的理解</label>
        <AutoTextarea
          id="lesson-note"
          disabled={create.isPending}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="一个想通的概念、一段自己的总结…"
          required
          maxLength={10000}
        />
        <p className="muted small">保存到当前章节：{node.title}</p>
        <button
          className="primary"
          disabled={
            !content.trim() || create.isPending || uncertainWrite(create.error)
          }
        >
          {create.isPending ? "保存中…" : "保存笔记"}
        </button>
        <ErrorNotice error={create.error} />
        <WriteRecovery
          error={create.error}
          onCheck={() => checkSaved("create")}
          onAllowRetry={() => create.reset()}
        />
      </form>
      <div className="feature-toolbar section-space">
        <SearchField
          label="搜索笔记"
          placeholder="搜索正文或引用原文"
          value={search}
          onChange={setSearch}
        />
        <Select
          label="笔记章节"
          value={chapter}
          onChange={setChapter}
          options={[
            { value: "all", label: "全部章节" },
            ...(nodes.data?.items || [node]).map((n) => ({
              value: String(n.id),
              label: `${n.code} ${n.title}`,
            })),
          ]}
        />
        <Select
          label="笔记类型"
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: "笔记与批注" },
            { value: "note", label: "普通笔记" },
            { value: "annotation", label: "选区批注" },
          ]}
        />
        <button
          type="button"
          disabled={!visible.length}
          onClick={() =>
            saveMarkdown(
              notesMarkdown(
                visible,
                nodes.data?.items || [node],
                project?.title || "学习计划",
              ),
              `${project?.title || "学习计划"}-笔记`,
            )
          }
        >
          导出当前笔记
        </button>
      </div>
      <QueryState query={notes} />
      <QueryState query={nodes} />
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {notes.data && (
        <p className="muted small">
          显示 {visible.length} / {notes.data.items.length} 条笔记与批注
        </p>
      )}
      {visible.map((note) => (
        <article className="note-card" key={note.id}>
          <p className="muted small">
            {nodes.data?.items.find((n) => n.id === note.nodeId)?.title ||
              "原章节已不可用"}{" "}
            · {new Date(note.updatedAt).toLocaleString("zh-CN")}
          </p>
          {note.selection && (
            <blockquote className="annotation-quote">
              {note.selection}
            </blockquote>
          )}
          <Suspense fallback={null}>
            <Markdown>{note.content}</Markdown>
          </Suspense>
          <div className="content-actions">
            <button
              type="button"
              onClick={() => {
                edit.reset();
                setEditing(note);
                setDraft(note.content);
              }}
            >
              编辑笔记
            </button>
            <button
              type="button"
              onClick={() => {
                remove.reset();
                setDeleting(note);
              }}
            >
              删除笔记
            </button>
          </div>
        </article>
      ))}
      {notes.data && !visible.length && (
        <p className="empty-inline">暂无符合条件的笔记。</p>
      )}
      {editing && (
        <Dialog
          title="编辑笔记"
          dismissible={!edit.isPending}
          onClose={() => closeEdit(() => setEditing(undefined))}
        >
          {editing.selection && (
            <blockquote className="annotation-quote">
              {editing.selection}
            </blockquote>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (
                draft.trim() &&
                !edit.isPending &&
                !uncertainWrite(edit.error)
              )
                edit.mutate();
            }}
          >
            <label htmlFor="edit-note">笔记内容</label>
            <AutoTextarea
              id="edit-note"
              disabled={edit.isPending}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              required
              maxLength={10000}
            />
            <ErrorNotice error={edit.error} />
            <WriteRecovery
              error={edit.error}
              onCheck={() => checkSaved("edit")}
              onAllowRetry={() => edit.reset()}
            />
            <div className="content-actions">
              <button
                type="button"
                disabled={edit.isPending}
                onClick={() => closeEdit(() => setEditing(undefined))}
              >
                取消
              </button>
              <button
                className="primary"
                disabled={
                  !draft.trim() || edit.isPending || uncertainWrite(edit.error)
                }
              >
                {edit.isPending ? "保存中…" : "保存修改"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {deleting && (
        <Dialog
          title="删除笔记"
          dismissible={!remove.isPending}
          onClose={() => setDeleting(undefined)}
        >
          <p>确定删除这条笔记或批注？删除后无法从本页面撤回。</p>
          <p className="annotation-quote">{deleting.content}</p>
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
              onClick={() => remove.mutate()}
            >
              确认删除
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
