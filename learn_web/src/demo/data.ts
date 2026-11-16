import type { components } from "../api/schema";
type Model<K extends keyof components["schemas"]> = components["schemas"][K];
export function createDemo(empty = false) {
  const now = new Date().toISOString();
  let sequence = 100;
  const projects: Model<"ProjectOut">[] = empty
    ? []
    : [
        {
          id: 1,
          title: "Python 从入门到实践",
          goal: "学会用 Python 解决日常的小问题，做一个自己的文件整理工具。",
          topic: "Python",
          background: "零基础",
          weeklyHours: 5,
          status: "active",
          createdAt: now,
          updatedAt: now,
        },
        {
          id: 2,
          title: "读懂设计的基本语言",
          goal: "理解排版、色彩和留白，让自己的表达更清晰。",
          topic: "设计",
          background: "",
          weeklyHours: 3,
          status: "active",
          createdAt: now,
          updatedAt: now,
        },
      ];
  const nodes: Model<"NodeOut">[] = empty
    ? []
    : [
        {
          id: 11,
          projectId: 1,
          code: "A1",
          title: "认识 Python 与第一个程序",
          description:
            "## 从一个小问题开始\n\n程序，是把一个大问题拆成电脑可以执行的小步骤。\n\n```python\nprint('Hello, learning!')\n```\n\n试着修改括号里的文字，再运行一次。\n\n### 学习要点\n\n- 理解程序按顺序执行\n- 认识字符串与输出\n- 用自己的话解释 `print()` 的作用",
          stage: "基础入门",
          estHours: 2,
          difficulty: 1,
          mastery: 1,
          status: "done",
          contentVersion: 1,
          createdAt: now,
        },
        {
          id: 12,
          projectId: 1,
          code: "A2",
          title: "变量，让信息有个名字",
          description:
            "## 给信息起一个名字\n\n变量就像一个有标签的收纳盒。你可以把数据放进去，也可以随时取出来。\n\n```python\nname = '小林'\nstudy_minutes = 25\nprint(name, study_minutes)\n```\n\n**想一想**：怎样用变量记录你每周计划学习的小时数？",
          stage: "基础入门",
          estHours: 2,
          difficulty: 2,
          mastery: 0.35,
          status: "learning",
          contentVersion: 1,
          createdAt: now,
        },
        {
          id: 13,
          projectId: 1,
          code: "A3",
          title: "用条件与循环解决问题",
          description: "把重复的事情交给循环，把选择的事情交给条件判断。",
          stage: "走向实践",
          estHours: 3,
          difficulty: 2,
          mastery: 0,
          status: "new",
          contentVersion: 1,
          createdAt: now,
        },
        {
          id: 21,
          projectId: 2,
          code: "B1",
          title: "从留白开始理解版式",
          description: "留白让重要的信息更加清晰。",
          stage: "设计基础",
          estHours: 2,
          difficulty: 1,
          mastery: 0,
          status: "new",
          contentVersion: 1,
          createdAt: now,
        },
      ];
  let cards: Model<"CardOut">[] = empty
    ? []
    : [
        {
          id: 31,
          projectId: 1,
          nodeId: 11,
          front: "Python 中，print() 的作用是什么？",
          back: "把括号里的内容输出到屏幕。它能帮助我们查看程序的执行结果。",
          cardType: "basic",
          state: 0,
          step: 0,
          reps: 0,
          stability: 0,
          nextReview: now,
          suspended: false,
        },
      ];
  const notes: Model<"NoteOut">[] = [];
  const tasks: Model<"TaskOut">[] = empty
    ? []
    : [
        {
          id: 41,
          projectId: 1,
          nodeId: 11,
          title: "写一句自己的学习宣言",
          description: "用 print() 输出一句你希望在这次学习中实现的目标。",
          taskType: "practice",
          status: "new",
          output: "",
        },
      ];
  const files: Model<"MaterialOut">[] = empty
    ? []
    : [
        {
          fileId: "demo-1",
          name: "Python 基础学习笔记.md",
          sizeBytes: 18432,
          sha256: "demo",
          createdAt: now,
        },
        {
          fileId: "demo-2",
          name: "第一周练习清单.txt",
          sizeBytes: 4096,
          sha256: "demo",
          createdAt: now,
        },
      ];
  const reports: (Model<"ReportOut"> & { projectId: number })[] = empty
    ? []
    : [
        {
          id: 51,
          projectId: 1,
          date: now.slice(0, 10),
          content: "今天完成了第一个程序的学习，继续保持这份好奇心。",
          studyMinutes: 25,
          cardsReviewed: 2,
          nodesProgressed: 1,
        },
      ];
  const quiz: Model<"QuizOut"> = {
    id: 61,
    title: "Python 入门 · 第一份小测",
    quizType: "mixed",
    questions: [
      {
        id: 62,
        stem: "Python 用哪个函数输出内容？（填写函数名）",
        qtype: "short",
        options: [],
        difficulty: 1,
      },
    ],
  };
  const json = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const jobs = new Map<string, Model<"JobOut">>();
  const reviewedCards: Model<"CardOut">[] = [];
  let grade: Model<"GradeOut"> | null = null;
  let gradeJob: { jobId: string; state: string } | null = null;
  const conversations = new Map<string, Model<"ConversationOut">>();
  const polishJobs = new Map<number, Model<"GenerationOut">>();
  return {
    jobs,
    async handle(url: string, init: RequestInit = {}): Promise<Response> {
      const path = new URL(url, "http://localhost").pathname.replace(
        /^.*\/api\/v2/,
        "",
      );
      const method = init.method || "GET";
      const body = typeof init.body === "string" ? JSON.parse(init.body) : {};
      if (path === "/me")
        return json({
          userId: "demo-learner",
          displayName: "学习者",
          capabilities: { chat: true, jobEvents: true },
          storage: null,
        } satisfies Model<"MeOut">);
      if (path === "/projects" && method === "GET")
        return json({ items: projects, limit: 50, offset: 0 });
      if (path === "/models")
        return json({ items: [], selectedModel: "", selectedAvailable: false });
      if (path === "/projects" && method === "POST") {
        const p = {
          id: ++sequence,
          topic: "",
          background: "",
          weeklyHours: 5,
          status: "active",
          createdAt: now,
          updatedAt: now,
          ...body,
        };
        projects.push(p);
        return json(p, 201);
      }
      const match = path.match(/^\/projects\/(\d+)\/([\w-]+)$/);
      const id = Number(match?.[1]);
      const resource = match?.[2];
      if (match && !projects.some((p) => p.id === id))
        return json(
          {
            error: {
              code: "NOT_FOUND",
              message: "project not found",
              retryable: false,
            },
          },
          404,
        );
      if (resource === "nodes" && method === "GET")
        return json({ items: nodes.filter((n) => n.projectId === id) });
      if (resource === "nodes" && method === "POST") {
        const n = {
          id: ++sequence,
          projectId: id,
          description: "",
          stage: "",
          difficulty: 1,
          mastery: 0,
          status: "new",
          contentVersion: 1,
          createdAt: now,
          ...body,
        };
        nodes.push(n);
        return json(n, 201);
      }
      if (path.startsWith("/nodes/") && method === "PATCH") {
        const n = nodes.find((n) => n.id === Number(path.split("/")[2]));
        Object.assign(n!, body);
        return json(n);
      }
      if (resource === "notes" && method === "GET")
        return json({ items: notes.filter((n) => n.projectId === id) });
      if (resource === "notes" && method === "POST") {
        const n = {
          id: ++sequence,
          projectId: id,
          selection: "",
          updatedAt: now,
          ...body,
        };
        notes.push(n);
        return json(n, 201);
      }
      if (resource === "tasks")
        return json({ items: tasks.filter((t) => t.projectId === id) });
      if (path.startsWith("/tasks/") && method === "PATCH") {
        const t = tasks.find((t) => t.id === Number(path.split("/")[2]));
        Object.assign(t!, body);
        return json(t);
      }
      if (path === "/review/due") return json({ items: cards });
      if (resource === "cards")
        return json({
          items: [...cards, ...reviewedCards].filter((c) => c.projectId === id),
        });
      if (/^\/review\/\d+$/.test(path) && method === "POST") {
        const c = cards.find((c) => c.id === Number(path.split("/")[2]));
        if (c) {
          c.reps += 1;
          c.nextReview = new Date(Date.now() + 86400000).toISOString();
          reviewedCards.push(c);
        }
        cards = cards.filter((c) => c.id !== Number(path.split("/")[2]));
        return json(c);
      }
      if (resource === "quizzes")
        return json({
          items:
            id === 1 && !empty
              ? [
                  {
                    id: 61,
                    title: quiz.title,
                    quizType: quiz.quizType,
                    createdAt: now,
                  },
                ]
              : [],
        });
      if (path === "/quizzes/61") return json(quiz);
      if (path === "/quizzes/61/result") return json(grade);
      if (path === "/quizzes/61/grade-job") return json(gradeJob);
      if (path === "/quizzes/61/grade-jobs") {
        if (gradeJob) return json(gradeJob, 202);
        const ok =
          String(body.answers?.[62] || "")
            .toLowerCase()
            .replace(/\(\)/g, "")
            .trim() === "print";
        grade = {
          correct: Number(ok),
          total: 1,
          score: Number(ok),
          results: [
            {
              questionId: 62,
              correct: ok,
              expected: "print",
              explanation: "print() 用于输出内容。",
              userAnswer: String(body.answers?.[62] || ""),
              feedback: ok ? "答案正确。" : "请对照参考答案巩固。",
            },
          ],
        };
        const jobId = `demo-grade-${++sequence}`;
        gradeJob = { jobId, state: "done" };
        jobs.set(jobId, {
          jobId,
          kind: "grade",
          subject: "quiz:61",
          state: "done",
          progress: { grade },
          error: null,
          updatedAt: now,
        });
        return json(gradeJob, 202);
      }
      if (resource === "materials" && method === "GET")
        return json({ items: files });
      if (path.startsWith("/materials/")) {
        const fid = path.split("/")[2];
        const file = files.find((f) => f.fileId === fid);
        if (!file)
          return json(
            {
              error: {
                code: "NOT_FOUND",
                message: "资料不存在",
                retryable: false,
              },
            },
            404,
          );
        if (method === "DELETE") {
          files.splice(files.indexOf(file), 1);
          return new Response(null, { status: 204 });
        }
        if (path.endsWith("/preview"))
          return json({
            fileId: fid,
            name: file.name,
            text: "这是一段资料内容的本地演示。",
            truncated: false,
          });
        if (path.endsWith("/download"))
          return new Response("本地演示资料", {
            headers: { "Content-Type": "application/octet-stream" },
          });
      }
      if (resource === "conversation")
        return json(
          conversations.get(
            `${id}:${new URL(url, "http://localhost").searchParams.get("mode") || "chat"}`,
          ) || {
            messages: [],
            activeJob: null,
            pendingQuestion: null,
          },
        );
      if (resource === "chat-jobs") {
        const jobId = `demo-chat-${++sequence}`;
        const conversationKey = `${id}:${body.mode || "chat"}`;
        const history = conversations.get(conversationKey) || {
          messages: [],
          activeJob: null,
          pendingQuestion: null,
        };
        history.messages.push(
          {
            role: "user",
            content: body.content,
            references: [],
            createdAt: now,
          },
          {
            role: "assistant",
            content:
              "**这是一段本地演示回答。**\n\n你可以先用自己的话解释概念，再写一个小例子验证。演示模式不会调用真实模型。",
            references: [],
            createdAt: now,
          },
        );
        conversations.set(conversationKey, history);
        jobs.set(jobId, {
          jobId,
          kind: "chat",
          subject: `project:${id}`,
          state: "done",
          progress: { done: 1, total: 1 },
          error: null,
          updatedAt: now,
        });
        return json({ jobId, state: "queued" }, 202);
      }
      if (resource === "polish-job") return json(polishJobs.get(id) || null);
      if (resource === "polish-jobs") {
        const jobId = `demo-polish-${++sequence}`;
        jobs.set(jobId, {
          jobId,
          kind: "polish",
          subject: `project:${id}`,
          state: "done",
          progress: {
            source: body.source,
            purpose: body.purpose,
            result: body.source,
            changed: false,
            done: 1,
            total: 1,
          },
          error: null,
          updatedAt: now,
        });
        const result = { jobId, state: "done" };
        polishJobs.set(id, result);
        return json(result, 202);
      }
      if (resource === "materials" && method === "POST") {
        const file = (init.body as FormData).get("file") as File;
        const jobId = `demo-index-${++sequence}`;
        const f = {
          fileId: String(sequence),
          name: file.name,
          sizeBytes: file.size,
          sha256: "demo",
          createdAt: now,
        };
        files.unshift(f);
        jobs.set(jobId, {
          jobId,
          kind: "index",
          subject: f.fileId,
          state: "queued",
          progress: { done: 0, total: 1 },
          error: null,
          updatedAt: now,
        });
        return json(
          { fileId: f.fileId, sha256: f.sha256, sizeBytes: f.sizeBytes, jobId },
          202,
        );
      }
      if (path.startsWith("/jobs/")) {
        const job = jobs.get(path.split("/")[2]);
        return job
          ? json(job)
          : json(
              {
                error: {
                  code: "NOT_FOUND",
                  message: "job not found",
                  retryable: false,
                },
              },
              404,
            );
      }
      if (resource === "path") {
        const items = nodes.filter((n) => n.projectId === id);
        return json({
          projectId: id,
          totalHours: items.reduce((t, n) => t + n.estHours, 0),
          weeks: Array.from({ length: body.weeks }, (_, i) => ({
            index: i + 1,
            hours: items
              .filter((_, j) => j % body.weeks === i)
              .reduce((t, n) => t + n.estHours, 0),
            items: items
              .filter((_, j) => j % body.weeks === i)
              .map((n) => ({
                nodeId: n.id,
                title: n.title,
                code: n.code,
                hours: n.estHours,
              })),
          })),
        });
      }
      if (resource === "summary") {
        const items = nodes.filter((n) => n.projectId === id);
        const count = items.filter((n) => n.status === "done").length;
        return json({
          totalNodes: items.length,
          nodesByStatus: { done: count },
          masteredNodes: count,
          masteryRatio: items.length ? count / items.length : 0,
          studyMinutes: id === 1 ? 25 : 0,
        });
      }
      if (resource === "reports" && method === "GET")
        return json({ items: reports.filter((r) => r.projectId === id) });
      if (resource === "reports" && method === "POST") {
        let r = reports.find(
          (r) => r.projectId === id && r.date === now.slice(0, 10),
        );
        if (!r) {
          r = {
            id: ++sequence,
            projectId: id,
            date: now.slice(0, 10),
            content: "今天也迈出了学习的一步。",
            studyMinutes: 0,
            cardsReviewed: 0,
            nodesProgressed: 0,
          };
          reports.unshift(r);
        }
        return json(r);
      }
      if (resource === "chat")
        return json({
          eventId: "demo-response",
          content:
            "**这是一段本地演示回答。**\n\n你可以先用自己的话解释概念，再写一个小例子验证。演示模式不会调用真实模型。",
          model: "demo",
          usage: {},
        });
      return json(
        {
          error: {
            code: "NOT_FOUND",
            message: "演示中未实现这个接口",
            retryable: false,
          },
        },
        404,
      );
    },
  };
}
