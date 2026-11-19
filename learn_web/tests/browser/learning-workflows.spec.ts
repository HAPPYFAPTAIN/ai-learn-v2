import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { createDemo } from "../../src/demo/data";
async function mock(page: Page) {
  const demo = createDemo();
  await page.route("**/api/v2/**", async (route) => {
    const req = route.request();
    const response = await demo.handle(req.url(), {
      method: req.method(),
      body: req.postData() || undefined,
    });
    await route.fulfill({
      status: response.status,
      contentType: "application/json",
      body: await response.text(),
    });
  });
  return demo;
}
async function choose(page: Page, label: string, option: string | RegExp) {
  await page.getByRole("combobox", { name: label, exact: true }).click();
  await page
    .getByRole("option", { name: option, exact: typeof option === "string" })
    .click();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
for (const width of [390, 1440]) {
  test(`quiz options use canonical letters, block unanswered submissions and filter mistakes at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let submitted = 0;
    let graded = false;
    const questions = [
      {
        id: 701,
        qtype: "choice",
        stem: "哪项是输出函数？",
        options: ["A. input()", "B. print()", "C. int()", "D. str()"],
        difficulty: 1,
      },
      {
        id: 702,
        qtype: "short",
        stem: "变量有什么用途？",
        options: [],
        difficulty: 1,
      },
      {
        id: 703,
        qtype: "choice",
        stem: "哪项表示整数？",
        options: ["整数", "字符串", "列表", "函数"],
        difficulty: 1,
      },
    ];
    const result = {
      correct: 2,
      total: 3,
      score: 2 / 3,
      results: questions.map((q, i) => ({
        questionId: q.id,
        correct: i !== 1,
        expected: ["B", "给数据命名", "A"][i],
        userAnswer: ["B", "不知道", "A"][i],
        explanation: "结合课程再理解一次。",
        feedback: i === 1 ? "需要巩固变量的含义" : "回答正确",
      })),
    };
    await page.route("**/api/v2/quizzes/61", (route) =>
      route.fulfill({
        json: { id: 61, title: "点选测验", quizType: "mixed", questions },
      }),
    );
    await page.route("**/api/v2/quizzes/61/result", (route) =>
      route.fulfill({ json: graded ? result : null }),
    );
    await page.route("**/api/v2/quizzes/61/grade-job", (route) =>
      route.fulfill({ json: null }),
    );
    await page.route("**/api/v2/quizzes/61/grade-jobs", (route) => {
      submitted++;
      expect(route.request().postDataJSON()).toEqual({
        answers: { "701": "B", "702": "不知道", "703": "A" },
      });
      graded = true;
      return route.fulfill({
        status: 202,
        json: { jobId: "letter-grade", state: "done" },
      });
    });
    await page.route("**/api/v2/jobs/letter-grade", (route) =>
      route.fulfill({
        json: { jobId: "letter-grade", state: "done", progress: {} },
      }),
    );
    await page.goto("/quiz?quiz=61");
    await page.getByRole("button", { name: "提交答案", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("还有 3 题未作答");
    expect(submitted).toBe(0);
    await page.getByRole("radio", { name: "B. print()", exact: true }).check();
    await page.getByRole("textbox", { name: "第 2 题答案" }).fill("不知道");
    await page.getByRole("button", { name: "跳转第 3 题，未答" }).click();
    await expect(page.locator("#quiz-question-61-703")).toBeFocused();
    await page.getByRole("radio", { name: "A. 整数", exact: true }).check();
    await page.getByRole("button", { name: "提交答案", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "答对 2 / 3 题" }),
    ).toBeVisible();
    await expect(
      page.getByRole("radio", { name: "B. print()", exact: true }),
    ).toBeDisabled();
    await page.getByRole("checkbox", { name: "仅查看错题" }).check();
    await expect(page.locator(".quiz-results .note-card")).toHaveCount(1);
    await expect(page.locator(".quiz-results .note-card")).toContainText(
      "第 2 题",
    );
    await expect(page.locator(".quiz-results .note-card")).toContainText(
      "我的答案：不知道",
    );
    await page.screenshot({
      path: testInfo.outputPath("quiz-workflow.png"),
      fullPage: true,
    });
    await noOverflow(page);
    expect(submitted).toBe(1);
  });

  test(`notes support chapter/search filters, failed edits, confirmed deletion and Markdown exports at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    const demo = await mock(page);
    await demo.handle("/api/v2/projects/1/notes", {
      method: "POST",
      body: JSON.stringify({
        nodeId: 12,
        content: "变量章节的独立笔记",
        selection: "变量就像一个有标签的收纳盒。",
      }),
    });
    await page.goto("/study?project=1&chapter=11");
    const lessonDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出本节课文" }).click();
    const lesson = await lessonDownload;
    expect(await readFile((await lesson.path())!, "utf8")).toContain(
      "认识 Python 与第一个程序",
    );
    await page.getByRole("tab", { name: "笔记", exact: true }).click();
    await page.getByLabel("记下你的理解").fill("**输出概念**：调用 print");
    await page.getByRole("button", { name: "保存笔记", exact: true }).click();
    await expect(page.locator(".notes-manager .note-card")).toHaveCount(1);
    await expect(page.getByLabel("记下你的理解")).toHaveValue("");
    expect(
      await page
        .getByLabel("记下你的理解")
        .evaluate((el) => el.matches(":user-invalid")),
    ).toBe(false);
    await choose(page, "笔记章节", "全部章节");
    await expect(page.locator(".notes-manager .note-card")).toHaveCount(2);
    await page
      .getByRole("searchbox", { name: "搜索笔记", exact: true })
      .fill("收纳盒");
    await expect(page.locator(".notes-manager .note-card")).toHaveCount(1);
    await choose(page, "笔记类型", "选区批注");
    const dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出当前笔记" }).click();
    const download = await dl;
    const text = await readFile((await download.path())!, "utf8");
    expect(text).toContain("> 变量就像一个有标签的收纳盒。");
    expect(text).toContain("变量章节的独立笔记");
    expect(text).not.toContain("输出概念");
    let edits = 0;
    await page.route("**/api/v2/notes/*", (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      edits++;
      if (edits === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "TEMPORARY",
              message: "保存暂不可用",
              retryable: true,
            },
          },
        });
      return route.fallback();
    });
    await page.getByRole("button", { name: "编辑笔记", exact: true }).click();
    await page.getByLabel("笔记内容", { exact: true }).fill("修订后的变量笔记");
    await page.getByRole("button", { name: "保存修改" }).click();
    await expect(page.getByRole("dialog")).toContainText("保存暂不可用");
    await expect(page.getByLabel("笔记内容", { exact: true })).toHaveValue(
      "修订后的变量笔记",
    );
    expect(edits).toBe(1);
    await page
      .getByRole("button", { name: "核对已保存记录", exact: true })
      .click();
    await page
      .getByRole("button", { name: "已核对，允许再次提交", exact: true })
      .click();
    await page.getByRole("button", { name: "保存修改" }).click();
    await expect(page.locator(".notes-manager .note-card")).toContainText(
      "修订后的变量笔记",
    );
    await expect(
      page.locator(".notes-manager .note-card blockquote"),
    ).toHaveText("变量就像一个有标签的收纳盒。");
    await page.screenshot({
      path: testInfo.outputPath("notes-workflow.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "删除笔记", exact: true }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "取消", exact: true })
      .click();
    await expect(page.locator(".notes-manager .note-card")).toHaveCount(1);
    await page.getByRole("button", { name: "删除笔记", exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.locator(".notes-manager .note-card")).toHaveCount(0);
    await noOverflow(page);
  });
}

for (const width of [390, 1440]) {
  test(`manual review cards preserve failed drafts, use the existing API and filter schedules at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let creates = 0;
    let modelRequests = 0;
    page.on("request", (req) => {
      if (req.method() === "POST" && /card-jobs/.test(req.url()))
        modelRequests++;
    });
    await page.route("**/api/v2/cards", (route) => {
      creates++;
      expect(route.request().headers()["x-learn-expected-user"]).toBe(
        "demo-learner",
      );
      expect(route.request().postDataJSON()).toEqual({
        requestId: expect.stringMatching(/^[\da-f-]{36}$/),
        projectId: 1,
        nodeId: 11,
        front: "手工问题：变量是什么？",
        back: "变量给数据命名。",
        cardType: "basic",
      });
      if (creates === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "TEMPORARY",
              message: "暂时无法保存卡片",
              retryable: true,
            },
          },
        });
      return route.fallback();
    });
    await page.goto("/review");
    await page
      .getByRole("button", { name: "手动添加复习卡", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "手动添加复习卡" });
    await choose(page, "关联章节", /A1 认识 Python/);
    await dialog.getByLabel("卡片问题").fill("手工问题：变量是什么？");
    await dialog.getByLabel("卡片答案").fill("变量给数据命名。");
    await dialog
      .getByRole("button", { name: "保存复习卡", exact: true })
      .click();
    await expect(dialog).toContainText("暂时无法保存卡片");
    await expect(dialog.getByLabel("卡片问题")).toHaveValue(
      "手工问题：变量是什么？",
    );
    expect(creates).toBe(1);
    await dialog
      .getByRole("button", { name: "核对已保存记录", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "已核对，允许再次提交", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "保存复习卡", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole("searchbox", { name: "搜索复习卡" }).fill("手工问题");
    await choose(page, "卡片状态", "已到期");
    await expect(page.locator(".review-schedule-list li")).toHaveCount(1);
    await page.getByText("查看卡片答案", { exact: true }).click();
    await expect(page.locator(".review-schedule-list")).toContainText(
      "变量给数据命名。",
    );
    await page.screenshot({
      path: testInfo.outputPath("manual-review.png"),
      fullPage: true,
    });
    await choose(page, "卡片状态", "已暂停");
    await expect(page.getByText("暂无符合条件的复习卡。")).toBeVisible();
    await page.reload();
    await expect(page.locator(".review-schedule-list")).toContainText(
      "手工问题",
    );
    expect(creates).toBe(2);
    expect(modelRequests).toBe(0);
    await noOverflow(page);
  });
}

test("report ranges deduplicate daily records, export safe CSV and isolate the printed report", async ({
  page,
}, testInfo) => {
  await mock(page);
  await page.addInitScript(() => {
    window.print = () => {
      (window as unknown as { printedScope: string | undefined }).printedScope =
        document.body.dataset.printLearning;
      window.dispatchEvent(new Event("afterprint"));
    };
  });
  await page.route("**/api/v2/projects/1/reports", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: 1,
            date: "2026-11-15",
            studyMinutes: 1000,
            cardsReviewed: 100,
            nodesProgressed: 10,
            content: "过时日报",
          },
          {
            id: 9,
            date: "2026-11-15",
            studyMinutes: 30,
            cardsReviewed: 4,
            nodesProgressed: 1,
            content: '=HYPERLINK("https://example.com")\n逗号,双引号"',
          },
          {
            id: 10,
            date: "2026-11-17",
            studyMinutes: 20,
            cardsReviewed: 2,
            nodesProgressed: 1,
            content: "今日记录",
          },
        ],
      },
    }),
  );
  await page.goto("/dashboard");
  await page.getByLabel("记录开始日期").fill("2026-11-15");
  await page.getByLabel("记录结束日期").fill("2026-11-17");
  const report = page.getByLabel("阶段学习报告");
  await expect(report).toContainText("2 天有日报记录");
  await expect(report).toContainText("50 分钟");
  await expect(page.locator(".report-row")).toHaveCount(2);
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 CSV", exact: true }).click();
  const download = await dl;
  const csv = await readFile((await download.path())!, "utf8");
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  expect(csv).toContain(
    '"\'=HYPERLINK(""https://example.com"")\n逗号,双引号"""',
  );
  expect(csv).not.toContain("过时日报");
  await page.getByLabel("记录开始日期").fill("2026-11-18");
  await expect(page.getByRole("alert")).toContainText(
    "开始日期不能晚于结束日期",
  );
  await expect(
    page.getByRole("button", { name: "导出记录", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("记录开始日期").fill("2026-02-30");
  await expect(page.getByRole("alert")).toContainText("请输入有效日期");
  await page.getByLabel("记录开始日期").fill("2026-11-15");
  await page.getByRole("button", { name: "打印学习报告" }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as unknown as { printedScope: string }).printedScope,
      ),
    )
    .toBe("true");
  await expect(page.locator("body")).not.toHaveAttribute("data-print-learning");
  await page.evaluate(() => (document.body.dataset.printLearning = "true"));
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".sidebar")).toBeHidden();
  await expect(page.getByRole("heading", { level: 1 })).toBeHidden();
  await expect(report).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("print-report.png"),
    fullPage: true,
  });
  await page.emulateMedia({ media: "screen" });
  await page.evaluate(() => delete document.body.dataset.printLearning);
});

for (const fallback of [false, true]) {
  test(`reading search, outline, font preferences and annotation highlights work with ${fallback ? "rectangle fallback" : "native highlights"}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: fallback ? 390 : 1440, height: 960 });
    await page.addInitScript((fallback) => {
      localStorage.setItem("learn.theme", fallback ? "dark" : "light");
      if (fallback)
        Object.defineProperty(window, "Highlight", {
          configurable: true,
          value: undefined,
        });
    }, fallback);
    const demo = await mock(page);
    await demo.handle("/api/v2/projects/1/notes", {
      method: "POST",
      body: JSON.stringify({
        nodeId: 11,
        content: "我理解了变量的用途",
        selection: "变量把信息命名。",
      }),
    });
    await demo.handle("/api/v2/projects/1/notes", {
      method: "POST",
      body: JSON.stringify({
        nodeId: 11,
        content: "旧引用",
        selection: "教材中已经不存在的句子",
      }),
    });
    const response = await demo.handle("/api/v2/projects/1/nodes");
    const nodes = await response.json();
    nodes.items[0].description =
      "## 第一部分\n\n变量把信息命名。\n\n## 第二部分\n\n再次理解变量。\n\n```python\nprint('hello')\n```";
    await page.route("**/api/v2/projects/1/nodes", (route) =>
      route.fulfill({ json: nodes }),
    );
    await page.goto("/study?project=1&chapter=11");
    await page.getByText("课文目录（2）", { exact: true }).click();
    await page
      .getByRole("navigation", { name: "课文目录", exact: true })
      .getByRole("button", { name: "第二部分" })
      .click();
    await expect(
      page.getByRole("heading", { name: "第二部分", exact: true }),
    ).toBeFocused();
    let noteRequests = 0;
    await page.route("**/api/v2/projects/1/notes", (route) => {
      noteRequests++;
      if (noteRequests === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "TEMPORARY",
              message: "暂时无法读取批注",
              retryable: true,
            },
          },
        });
      return route.fallback();
    });
    await page.getByRole("checkbox", { name: "显示批注高亮" }).check();
    await expect(page.getByRole("alert")).toContainText("暂时无法读取批注");
    expect(noteRequests).toBe(1);
    await page.getByRole("button", { name: "重新加载", exact: true }).click();
    await expect(page.getByText(/1 条批注的原文已变化/)).toBeVisible();
    if (fallback)
      await expect(page.locator(".le-annotations span")).not.toHaveCount(0);
    else
      await expect
        .poll(() =>
          page.evaluate(() => CSS.highlights.get("le-annotations")?.size),
        )
        .toBe(1);
    await page
      .getByRole("searchbox", { name: "搜索课文", exact: true })
      .fill("变量");
    await expect(page.getByText("第 1 / 2 处", { exact: true })).toBeVisible();
    if (fallback) {
      await expect(page.locator(".le-search span")).not.toHaveCount(0);
      await expect(page.locator(".le-search-current span")).not.toHaveCount(0);
    } else {
      await expect
        .poll(() => page.evaluate(() => CSS.highlights.get("le-search")?.size))
        .toBe(2);
      await expect
        .poll(() =>
          page.evaluate(() => CSS.highlights.get("le-search-current")?.size),
        )
        .toBe(1);
    }
    await page.getByRole("button", { name: "下一处", exact: true }).click();
    await expect(page.getByText("第 2 / 2 处", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "上一处", exact: true }).click();
    await expect(page.getByText("第 1 / 2 处", { exact: true })).toBeVisible();
    await page.getByRole("slider", { name: "课文字号" }).press("End");
    await expect(page.getByRole("slider", { name: "课文字号" })).toHaveValue(
      "24",
    );
    await page
      .getByRole("searchbox", { name: "搜索课文", exact: true })
      .fill("不存在的词");
    await expect(page.getByText("本节正文未找到匹配文字。")).toBeVisible();
    await page
      .getByRole("searchbox", { name: "搜索课文", exact: true })
      .fill("变量");
    await expect(page.getByText("第 1 / 2 处", { exact: true })).toBeVisible();
    if (fallback)
      await expect(page.locator(".le-search span")).not.toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("reading-tools.png"),
      fullPage: true,
    });
    await expect(page.locator(".lesson-reading .prose mark")).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("slider", { name: "课文字号" })).toHaveValue(
      "24",
    );
    await expect(
      page.getByRole("checkbox", { name: "显示批注高亮" }),
    ).toBeChecked();
    await page.getByRole("checkbox", { name: "显示批注高亮" }).uncheck();
    if (fallback)
      await expect(page.locator(".le-annotations span")).toHaveCount(0);
    else
      await expect
        .poll(() =>
          page.evaluate(() => CSS.highlights.get("le-annotations")?.size),
        )
        .toBe(0);
    await noOverflow(page);
  });
}
