import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { createDemo } from "../../src/demo/data";
import { samplePdf } from "./pdfFixture";
async function mock(page: Page, empty = false) {
  const demo = createDemo(empty);
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
const pages = [
  ["/", "每一份好奇"],
  ["/study", "学习工作台"],
  ["/roadmap", "学习路线"],
  ["/chat", "知识问答"],
  ["/library", "资料库"],
  ["/review", "间隔复习"],
  ["/quiz", "查漏测验"],
  ["/dashboard", "学习看板"],
  ["/tools", "学习工具"],
  ["/models", "模型设置"],
];

for (const width of [1024, 1440, 1920]) {
  for (const theme of ["light", "dark"]) {
    test(`sidebar collapses for focused study at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/study?project=1&chapter=12");
      const sidebar = page.locator("#primary-nav");
      const collapse = page.getByRole("button", {
        name: "收起侧栏",
        exact: true,
      });
      const expand = page.getByRole("button", {
        name: "展开侧栏",
        exact: true,
      });
      await expect(collapse).toBeVisible();
      const before = (await page.getByRole("main").boundingBox())!;
      // A layout toggle must keep the selected tab and unsaved input intact.
      await page.getByRole("tab", { name: "笔记", exact: true }).click();
      const textbox = page.getByRole("textbox", {
        name: "记下你的理解",
        exact: true,
      });
      await textbox.fill("收起菜单时保留的笔记草稿");
      await collapse.click();
      await expect(sidebar).toBeHidden();
      await expect(expand).toBeFocused();
      await expect(expand).toHaveAttribute("aria-expanded", "false");
      await expect(
        page.getByRole("tab", { name: "笔记", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      await expect(textbox).toHaveValue("收起菜单时保留的笔记草稿");
      const after = (await page.getByRole("main").boundingBox())!;
      expect(after.width).toBeGreaterThan(before.width);
      expect(after.x).toBe(0);
      expect(after.width).toBe(width);
      await expect(page).toHaveURL(/chapter=12/);
      await page.screenshot({ path: testInfo.outputPath("focused-study.png") });
      await textbox.fill("");
      await page.reload();
      await expect(sidebar).toBeHidden();
      await expect(expand).toBeVisible();
      await expand.focus();
      await page.keyboard.press("Enter");
      await expect(sidebar).toBeVisible();
      await expect(collapse).toBeFocused();
      await expect(collapse).toHaveAttribute("aria-expanded", "true");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath("sidebar-restored.png"),
      });
    });
  }
}

test("collapsed desktop preference keeps mobile navigation usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await mock(page);
  await page.goto("/study?project=1&chapter=12");
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const sidebar = page.locator("#primary-nav");
  await expect(sidebar).toHaveAttribute("inert", "");
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await expect(sidebar).not.toHaveAttribute("inert", "");
  await expect(
    page.getByRole("link", { name: "学习首页", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  await expect(sidebar).toHaveAttribute("inert", "");
  await expect(
    page.getByRole("button", { name: "打开导航", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await page.getByRole("link", { name: "学习工作台", exact: true }).click();
  await expect(page).toHaveURL(/\/study$/);
  await expect(sidebar).toHaveAttribute("inert", "");
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect(sidebar).toBeHidden();
  await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
  await expect(sidebar).toBeVisible();
});

test("sidebar toggle works when preference storage is unavailable", async ({
  page,
}) => {
  await mock(page);
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key === "learn.sidebar.collapsed")
        throw new DOMException("Storage blocked", "SecurityError");
      original.call(this, key, value);
    };
  });
  await page.goto("/study");
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  await expect(page.locator("#primary-nav")).toBeHidden();
  await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
  await expect(page.locator("#primary-nav")).toBeVisible();
});

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`pages retain normal layouts without a plan at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await mock(page, true);
      const requests: string[] = [];
      page.on("request", (r) => {
        if (r.url().includes("/api/v2/")) requests.push(r.url());
      });
      await page.goto("/chat");
      if (theme === "dark")
        await page.getByRole("button", { name: "切换深色主题" }).click();
      const main = page.getByRole("main");
      async function check(path: string) {
        await expect(
          main.getByRole("link", { name: "添加学习计划" }),
        ).toHaveCount(0);
        await expect(
          main.getByRole("button", { name: "添加学习计划" }),
        ).toHaveCount(0);
        await expect(main.getByRole("alert")).toHaveCount(0);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
        ).toBe(true);
        await page.screenshot({
          path: testInfo.outputPath(`${path}.png`),
          fullPage: true,
        });
      }
      await expect(main.locator(".chat-panel")).toBeVisible();
      await expect(
        page.getByRole("textbox", { name: "向助教提问" }),
      ).toBeDisabled();
      await expect(
        main.getByRole("button", { name: "发送", exact: true }),
      ).toBeDisabled();
      await check("chat-empty");
      await page.goto("/library");
      await expect(
        main.getByRole("heading", { name: "我的资料", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("searchbox", { name: "搜索资料" }),
      ).toBeEnabled();
      await page
        .getByRole("combobox", { name: "资料类型", exact: true })
        .click();
      await page.getByRole("option", { name: "PDF", exact: true }).click();
      await expect(
        main.getByRole("button", { name: "上传资料", exact: true }),
      ).toBeDisabled();
      await check("library-empty");
      await page.goto("/dashboard");
      await expect(main.locator(".stat-card")).toHaveCount(3);
      await expect(
        main.getByRole("heading", { name: "学习趋势", exact: true }),
      ).toBeVisible();
      await expect(
        main.getByRole("heading", { name: "学习记录", exact: true }),
      ).toBeVisible();
      await expect(
        main.getByRole("button", { name: "整理今日报告", exact: true }),
      ).toBeDisabled();
      await check("dashboard-empty");
      await page.goto("/tools");
      await expect(
        main.getByRole("combobox", { name: "练习章节", exact: true }),
      ).toBeDisabled();
      await expect(main.locator(".chat-panel")).toBeVisible();
      await check("coach-empty");
      await main.getByRole("button", { name: /文本润色 保留原意/ }).click();
      await expect(
        main.getByRole("textbox", { name: "原文", exact: true }),
      ).toBeDisabled();
      await expect(
        main.getByRole("button", { name: "开始润色", exact: true }),
      ).toBeDisabled();
      await check("polish-empty");
      expect(requests.some((url) => /\/projects\/0\b/.test(url))).toBe(false);
    });
  }
}

for (const width of [390, 1440]) {
  test(`learning plan deletion requires confirmation and persists at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    await page.goto("/");
    const name = "删除学习计划：Python 从入门到实践";
    let deletes = 0;
    page.on("request", (r) => {
      if (r.method() === "DELETE") deletes++;
    });
    await page.getByRole("button", { name, exact: true }).click();
    const dialog = page.getByRole("dialog", {
      name: "删除学习计划",
      exact: true,
    });
    await expect(dialog).toContainText("资料库中的原始文件保留");
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    expect(deletes).toBe(0);
    await expect(page).toHaveURL("/");
    await page.getByRole("button", { name, exact: true }).click();
    await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page).toHaveURL("/study");
    await expect(page.locator(".project-card")).toHaveCount(1);
    await expect(
      page.getByRole("heading", { name: "读懂设计的基本语言" }),
    ).toBeVisible();
    expect(deletes).toBe(1);
    await page.reload();
    await expect(page.locator(".project-card")).toHaveCount(1);
    await page
      .getByRole("button", {
        name: "删除学习计划：读懂设计的基本语言",
        exact: true,
      })
      .click();
    await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "暂无学习计划" }),
    ).toBeVisible();
  });

  test(`roadmap deletion retains the plan and permits generation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    await page.goto("/roadmap?project=1");
    if (width === 1440)
      await page.getByRole("button", { name: "切换深色主题" }).click();
    await page.getByRole("button", { name: "生成周计划", exact: true }).click();
    await expect(page.locator(".week-card")).toHaveCount(8);
    await page
      .getByRole("button", {
        name: "删除学习路线：Python 从入门到实践",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "删除学习路线",
      exact: true,
    });
    await expect(dialog).toContainText("学习计划、目标和资料库保留");
    await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".roadmap-list li")).toHaveCount(0);
    await expect(page.locator(".week-card")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "AI 生成学习路线", exact: true }),
    ).toBeEnabled();
    await page.reload();
    await expect(page.locator(".roadmap-list li")).toHaveCount(0);
    await page.goto("/study");
    await expect(page.locator(".project-card")).toHaveCount(2);
    await page.goto("/library?project=1");
    await expect(page.locator(".file-row")).toHaveCount(2);
  });
}

test("roadmap deletion keeps content and dialog when a task is running", async ({
  page,
}) => {
  await mock(page);
  let calls = 0;
  await page.route("**/api/v2/projects/1/roadmap", (route) => {
    calls++;
    return route.fulfill({
      status: 409,
      json: { error: { code: "JOB_RUNNING", message: "请等待任务完成" } },
    });
  });
  await page.goto("/roadmap?project=1");
  await page
    .getByRole("button", {
      name: "删除学习路线：Python 从入门到实践",
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "删除学习路线",
    exact: true,
  });
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("请等待任务完成");
  await expect(page.locator(".roadmap-list li")).toHaveCount(3);
  expect(calls).toBe(1);
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
});

test("roadmap deletion prevents repeat requests after a lost response", async ({
  page,
}) => {
  await mock(page);
  let calls = 0;
  await page.route("**/api/v2/projects/1/roadmap", (route) => {
    calls++;
    return route.abort("failed");
  });
  await page.goto("/roadmap?project=1");
  await page
    .getByRole("button", {
      name: "删除学习路线：Python 从入门到实践",
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "删除学习路线",
    exact: true,
  });
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "刷新核对结果" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "确认删除", exact: true }),
  ).toBeDisabled();
  expect(calls).toBe(1);
  await expect(page.locator(".roadmap-list li")).toHaveCount(3);
});

for (const width of [390, 1440]) {
  test(`batch deletion confirms the full selection and preserves its result at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    const requests: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "DELETE") requests.push(req.url());
    });
    await page.goto("/library");
    const all = page.getByRole("checkbox", { name: "选择当前结果" });
    await page
      .getByRole("checkbox", { name: "选择资料：Python 基础学习笔记.md" })
      .check();
    await expect(all).toHaveJSProperty("indeterminate", true);
    await all.check();
    await expect(all).toBeChecked();
    await page.getByRole("searchbox", { name: "搜索资料" }).fill("Python");
    await expect(
      page.getByText(
        "已选资料中有 1 份不在当前筛选结果中，删除前可核对完整清单。",
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: "批量删除", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "批量删除资料" });
    await expect(dialog).toContainText("第一周练习清单.txt");
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    expect(requests).toHaveLength(0);
    await page.getByRole("button", { name: "批量删除", exact: true }).click();
    await page.screenshot({ path: testInfo.outputPath("batch-confirm.png") });
    const box = (await dialog.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await dialog.getByRole("button", { name: "确认删除 2 份资料" }).click();
    await expect(dialog.getByRole("status")).toHaveText("已删除 2 份资料。");
    expect(requests).toHaveLength(2);
    await expect(page.locator(".file-row")).toHaveCount(0);
    await dialog.getByRole("button", { name: "完成", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "资料库还是空的" }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "资料库还是空的" }),
    ).toBeVisible();
  });
}

test("batch deletion retries only unfinished files", async ({ page }) => {
  await mock(page);
  const attempts: Record<string, number> = {};
  await page.route("**/api/v2/materials/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    const id = route.request().url().split("/").pop()!;
    attempts[id] = (attempts[id] || 0) + 1;
    if (id === "demo-2" && attempts[id] === 1)
      return route.fulfill({
        status: 409,
        json: {
          error: { code: "FILE_BUSY", message: "资料处理中", retryable: true },
        },
      });
    return route.fallback();
  });
  await page.goto("/library");
  await page.getByRole("checkbox", { name: "选择当前结果" }).check();
  await page.getByRole("button", { name: "批量删除", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量删除资料" });
  await dialog.getByRole("button", { name: "确认删除 2 份资料" }).click();
  await expect(dialog.getByRole("status")).toContainText(
    "已删除 1 份资料，1 份未完成",
  );
  await expect(page.locator(".file-row")).toHaveCount(1);
  await expect(
    page.getByRole("checkbox", { name: "选择资料：第一周练习清单.txt" }),
  ).toBeChecked();
  await dialog.getByRole("button", { name: "重试未完成的 1 份" }).click();
  await expect(dialog.getByRole("status")).toHaveText("已删除 2 份资料。");
  expect(attempts).toEqual({ "demo-1": 1, "demo-2": 2 });
});

for (const status of [0, 429, 503]) {
  test(`batch deletion stops later requests after HTTP ${status}`, async ({
    page,
  }) => {
    await mock(page);
    let count = 0;
    await page.route("**/api/v2/materials/*", async (route) => {
      if (route.request().method() !== "DELETE") return route.fallback();
      count++;
      if (status === 0) return route.abort("failed");
      return route.fulfill({
        status,
        json: { error: { code: "BUSY", message: "稍后重试", retryable: true } },
      });
    });
    await page.goto("/library");
    await page.getByRole("checkbox", { name: "选择当前结果" }).check();
    await page.getByRole("button", { name: "批量删除", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "批量删除资料" });
    await dialog.getByRole("button", { name: "确认删除 2 份资料" }).click();
    await expect(dialog.getByRole("status")).toContainText(
      "已删除 0 份资料，2 份未完成",
    );
    await expect(dialog).toContainText("未处理：尚未处理，可稍后重试");
    expect(count).toBe(1);
  });
}

test("batch deletion can stop after its current request", async ({ page }) => {
  await mock(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let count = 0;
  await page.route("**/api/v2/materials/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    count++;
    await pending;
    return route.fallback();
  });
  await page.goto("/library");
  await page.getByRole("checkbox", { name: "选择当前结果" }).check();
  await page.getByRole("button", { name: "批量删除", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量删除资料" });
  await dialog.getByRole("button", { name: "确认删除 2 份资料" }).click();
  await expect.poll(() => count).toBe(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "停止后续删除" }).click();
  release();
  await expect(dialog.getByRole("status")).toContainText(
    "已删除 1 份资料，1 份未完成",
  );
  expect(count).toBe(1);
});

test("batch deletion stops on account changes and clears old filenames", async ({
  page,
}) => {
  await mock(page);
  let count = 0;
  await page.route("**/api/v2/materials/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    count++;
    return route.fulfill({
      status: 409,
      json: {
        error: {
          code: "ACCOUNT_CHANGED",
          message: "账号已切换",
          retryable: false,
        },
      },
    });
  });
  await page.goto("/library");
  await page.getByRole("checkbox", { name: "选择当前结果" }).check();
  await page.getByRole("button", { name: "批量删除", exact: true }).click();
  await page.getByRole("button", { name: "确认删除 2 份资料" }).click();
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(
    page.getByText("Python 基础学习笔记.md", { exact: true }),
  ).toHaveCount(0);
  expect(count).toBe(1);
});

test("batch deletion caps each confirmed operation at 50 files", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/v2/projects/*/materials", (route) =>
    route.fulfill({
      json: {
        items: Array.from({ length: 51 }, (_, i) => ({
          fileId: `file-${i}`,
          name: `资料${i}.txt`,
          sizeBytes: 100,
          createdAt: "2026-11-17T00:00:00Z",
          sha256: "fixture",
        })),
      },
    }),
  );
  await page.goto("/library");
  await page.getByRole("checkbox", { name: "选择当前结果" }).check();
  await expect(
    page.getByRole("button", { name: "批量删除", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("每批最多删除 50 份资料，请减少选择。"),
  ).toBeVisible();
});

test("identity contract rejects malformed accounts before loading business data", async ({
  page,
}) => {
  await mock(page);
  let business = 0;
  await page.route("**/api/v2/**", async (route) => {
    if (route.request().url().endsWith("/me"))
      return route.fulfill({
        json: { userId: "", displayName: "学习者", capabilities: {} },
      });
    business++;
    return route.fallback();
  });
  await page.goto("/library");
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("账号信息格式不正确");
  expect(business).toBe(0);
});

test("identity contract clears ready data when account renewal becomes malformed", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/library");
  await expect(page.locator(".file-row")).toHaveCount(2);
  await page.route("**/api/v2/me", (route) =>
    route.fulfill({
      json: {
        userId: "demo-user",
        displayName: "学习者",
        capabilities: { chat: "true" },
      },
    }),
  );
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(
    page.getByText("Python 基础学习笔记.md", { exact: true }),
  ).toHaveCount(0);
});

async function mockPdf(page: Page, sizeBytes = 4096) {
  await mock(page);
  await page.route("**/api/v2/projects/*/materials", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            fileId: "pdf-first",
            name: "课程原件.pdf",
            sizeBytes,
            createdAt: "2026-11-17T00:00:00Z",
            sha256: "fixture",
          },
          {
            fileId: "demo-1",
            name: "第10课.md",
            sizeBytes: 100,
            createdAt: "2026-11-15T00:00:00Z",
            sha256: "fixture",
          },
          {
            fileId: "demo-2",
            name: "第2课.txt",
            sizeBytes: 200,
            createdAt: "2026-11-16T00:00:00Z",
            sha256: "fixture",
          },
        ],
      },
    }),
  );
  await page.route("**/api/v2/materials/pdf-first/preview", (route) =>
    route.fulfill({
      json: {
        fileId: "pdf-first",
        name: "课程原件.pdf",
        text: "可复制的 PDF 提取文字。",
        truncated: false,
      },
    }),
  );
  await page.route("**/api/v2/materials/pdf-first/download", (route) =>
    route.fulfill({ contentType: "application/pdf", body: samplePdf() }),
  );
}

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`PDF original renders, pages and zooms at ${width}px / ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mockPdf(page);
      const errors: string[] = [];
      const external: string[] = [];
      let dialogs = 0;
      let downloads = 0;
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (req) => {
        if (!req.url().startsWith("http://127.0.0.1:"))
          external.push(req.url());
        if (req.url().endsWith("/pdf-first/download")) downloads++;
      });
      page.on("dialog", (dialog) => {
        dialogs++;
        void dialog.dismiss();
      });
      await page.goto("/library");
      await page
        .locator(".file-row")
        .filter({ hasText: "课程原件.pdf" })
        .getByRole("button", { name: "查看", exact: true })
        .click();
      const dialog = page.getByRole("dialog", { name: "课程原件.pdf" });
      await expect(dialog).toContainText("可复制的 PDF 提取文字。");
      expect(downloads).toBe(0);
      await dialog
        .getByRole("button", { name: "PDF 原件", exact: true })
        .click();
      await expect(dialog.locator(".pdf-canvas-scroll")).toHaveAttribute(
        "aria-busy",
        "false",
      );
      const canvas = dialog.getByRole("img", { name: "课程原件.pdf，第 1 页" });
      await expect(canvas).toBeVisible();
      const originalWidth = await canvas.evaluate(
        (element) => (element as HTMLCanvasElement).width,
      );
      expect(originalWidth).toBeGreaterThan(100);
      expect(
        await canvas.evaluate((element) => {
          const c = element as HTMLCanvasElement;
          const pixel = c
            .getContext("2d")!
            .getImageData(
              Math.floor(c.width / 2),
              Math.floor(c.height / 4),
              1,
              1,
            ).data;
          return pixel[1] > pixel[0] && pixel[1] > pixel[2];
        }),
      ).toBe(true);
      await dialog.getByRole("button", { name: "下一页", exact: true }).click();
      await expect(
        dialog.getByRole("img", { name: "课程原件.pdf，第 2 页" }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "下一页", exact: true }),
      ).toBeDisabled();
      await dialog.getByRole("button", { name: "放大 PDF" }).click();
      await expect(dialog.locator(".pdf-toolbar")).toContainText("125%");
      await expect(dialog.locator(".pdf-canvas-scroll")).toHaveAttribute(
        "aria-busy",
        "false",
      );
      await dialog
        .getByRole("button", { name: "适应宽度", exact: true })
        .click();
      await dialog.getByRole("spinbutton", { name: "PDF 页码" }).fill("1");
      await dialog.getByRole("button", { name: "跳转", exact: true }).click();
      await expect(
        dialog.getByRole("img", { name: "课程原件.pdf，第 1 页" }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "上一页", exact: true }),
      ).toBeDisabled();
      await expect(dialog.locator(".pdf-canvas-scroll")).toHaveAttribute(
        "aria-busy",
        "false",
      );
      await expect
        .poll(() =>
          canvas.evaluate((element) => {
            const c = element as HTMLCanvasElement;
            const pixel = c
              .getContext("2d")!
              .getImageData(
                Math.floor(c.width / 2),
                Math.floor(c.height / 4),
                1,
                1,
              ).data;
            return pixel[1] > pixel[0] && pixel[1] > pixel[2];
          }),
        )
        .toBe(true);
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await page.screenshot({ path: testInfo.outputPath("pdf-preview.png") });
      const download = page.waitForEvent("download");
      await dialog
        .getByRole("button", { name: "下载原件", exact: true })
        .click();
      expect((await download).suggestedFilename()).toBe("课程原件.pdf");
      await dialog
        .getByRole("button", { name: "提取文字", exact: true })
        .click();
      await expect(dialog.locator(".material-preview-text")).toContainText(
        "可复制的 PDF",
      );
      await expect(dialog.locator("canvas")).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
      expect(dialogs).toBe(0);
    });
  }
}

test("PDF errors retry safely and oversized files keep the extracted text available", async ({
  page,
}) => {
  await mockPdf(page);
  let calls = 0;
  let corrupt = true;
  await page.route("**/api/v2/materials/pdf-first/download", (route) => {
    calls++;
    return route.fulfill({
      contentType: "application/pdf",
      body: corrupt ? Buffer.from("not a PDF") : samplePdf(),
    });
  });
  await page.goto("/library");
  await page
    .locator(".file-row")
    .filter({ hasText: "课程原件.pdf" })
    .getByRole("button", { name: "查看", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "课程原件.pdf" });
  await dialog.getByRole("button", { name: "PDF 原件", exact: true }).click();
  await expect(dialog).toContainText("PDF 原件暂时无法预览");
  const beforeRetry = calls;
  corrupt = false;
  await dialog.getByRole("button", { name: "重试预览", exact: true }).click();
  await expect(dialog.getByRole("img")).toBeVisible();
  expect(calls).toBe(beforeRetry + 1);
  await page.keyboard.press("Escape");
  await mockPdf(page, 21 * 1024 * 1024);
  let oversizedDownloads = 0;
  await page.route("**/api/v2/materials/pdf-first/download", (route) => {
    oversizedDownloads++;
    return route.fulfill({ contentType: "application/pdf", body: samplePdf() });
  });
  await page.reload();
  await page
    .locator(".file-row")
    .filter({ hasText: "课程原件.pdf" })
    .getByRole("button", { name: "查看", exact: true })
    .click();
  await dialog.getByRole("button", { name: "PDF 原件", exact: true }).click();
  await expect(dialog).toContainText("20 MB 以内");
  expect(oversizedDownloads).toBe(0);
  await dialog.getByRole("button", { name: "提取文字", exact: true }).click();
  await expect(dialog.locator(".material-preview-text")).toContainText(
    "可复制的 PDF",
  );
});

test("PDF page count limit preserves the text fallback", async ({ page }) => {
  await mockPdf(page);
  await page.route("**/api/v2/materials/pdf-first/download", (route) =>
    route.fulfill({ contentType: "application/pdf", body: samplePdf(201) }),
  );
  await page.goto("/library");
  await page
    .locator(".file-row")
    .filter({ hasText: "课程原件.pdf" })
    .getByRole("button", { name: "查看", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "课程原件.pdf" });
  await dialog.getByRole("button", { name: "PDF 原件", exact: true }).click();
  await expect(dialog).toContainText("最多支持 200 页");
  await expect(dialog.locator("canvas")).toHaveCount(0);
  await dialog.getByRole("button", { name: "提取文字", exact: true }).click();
  await expect(dialog.locator(".material-preview-text")).toContainText(
    "可复制的 PDF",
  );
});

test("closing a PDF preview aborts its pending file request", async ({
  page,
}) => {
  await mockPdf(page);
  let finish!: () => void;
  await page.route("**/api/v2/materials/pdf-first/download", async (route) => {
    await new Promise<void>((resolve) => {
      finish = resolve;
    });
    await route.fulfill({ contentType: "application/pdf", body: samplePdf() });
  });
  await page.goto("/library");
  await page
    .locator(".file-row")
    .filter({ hasText: "课程原件.pdf" })
    .getByRole("button", { name: "查看", exact: true })
    .click();
  await page.getByRole("button", { name: "PDF 原件", exact: true }).click();
  await expect.poll(() => !!finish).toBe(true);
  const cancelled = page.waitForEvent("requestfailed", (req) =>
    req.url().endsWith("/pdf-first/download"),
  );
  await page.keyboard.press("Escape");
  await cancelled;
  finish();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

for (const width of [390, 1440]) {
  test(`library combines search, type filtering and sorting at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await mockPdf(page);
    await page.goto("/library");
    await expect(page.locator(".file-name strong")).toHaveText([
      "课程原件.pdf",
      "第2课.txt",
      "第10课.md",
    ]);
    await page.getByRole("combobox", { name: "资料排序" }).click();
    await page.getByRole("option", { name: "名称顺序", exact: true }).click();
    await expect(page.locator(".file-name strong")).toHaveText([
      "第2课.txt",
      "第10课.md",
      "课程原件.pdf",
    ]);
    await page.getByRole("combobox", { name: "资料排序" }).click();
    await page.getByRole("option", { name: "最早添加", exact: true }).click();
    await expect(page.locator(".file-name strong")).toHaveText([
      "第10课.md",
      "第2课.txt",
      "课程原件.pdf",
    ]);
    await page.getByRole("combobox", { name: "资料排序" }).click();
    await page.getByRole("option", { name: "文件大小", exact: true }).click();
    await expect(page.locator(".file-name strong")).toHaveText([
      "课程原件.pdf",
      "第2课.txt",
      "第10课.md",
    ]);
    await page.getByRole("combobox", { name: "资料类型" }).click();
    await page.getByRole("option", { name: "PDF", exact: true }).click();
    await expect(page.locator(".file-row")).toHaveCount(1);
    await expect(page.getByRole("status")).toContainText("显示 1 / 3 份资料");
    await page.getByRole("searchbox", { name: "搜索资料" }).fill("不存在");
    await expect(
      page.getByText("没有找到匹配的资料。", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "清除筛选", exact: true }).click();
    await expect(page.locator(".file-row")).toHaveCount(3);
    await expect(page.getByRole("searchbox", { name: "搜索资料" })).toHaveValue(
      "",
    );
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  });
}

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`code highlighting and copy preserve source at ${width}px / ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript((theme) => {
        localStorage.setItem("learn.theme", theme);
        Object.defineProperty(navigator, "clipboard", {
          configurable: true,
          value: {
            writeText: async (text: string) => {
              document.documentElement.setAttribute("data-copied", text);
            },
          },
        });
      }, theme);
      await mock(page);
      await page.goto("/study?project=1&chapter=11");
      await expect(page.locator(".code-block .hljs-string")).toContainText(
        "Hello, learning!",
      );
      await page.getByRole("button", { name: "复制代码", exact: true }).click();
      await expect(page.locator("html")).toHaveAttribute(
        "data-copied",
        "print('Hello, learning!')",
      );
      await expect(
        page.getByRole("status").filter({ hasText: "已复制" }),
      ).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
    });

    test(`roadmap mindmap supports zoom, export and project changes at ${width}px / ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      const external: string[] = [];
      page.on("request", (request) => {
        if (!request.url().startsWith("http://127.0.0.1:"))
          external.push(request.url());
      });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/roadmap?project=1");
      await page.getByRole("button", { name: "思维导图", exact: true }).click();
      const map = page.getByRole("region", { name: "思维导图", exact: true });
      await expect(map.getByRole("img")).toBeVisible();
      await expect(map.locator("svg")).toContainText(
        /认识\s*Python\s*与第一个程序/,
      );
      const transform = () =>
        map.locator("svg > g").first().getAttribute("transform");
      const initial = await transform();
      await map.getByRole("button", { name: "放大导图" }).click();
      await expect.poll(transform).not.toBe(initial);
      await map.getByRole("button", { name: "缩小导图" }).click();
      await map.getByRole("button", { name: "适应画布" }).click();
      await map.getByText("查看文字大纲", { exact: true }).click();
      await expect(map.locator(".mindmap-outline")).toContainText(
        "A1 认识 Python 与第一个程序",
      );
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await page.screenshot({
        path: testInfo.outputPath("mindmap.png"),
        fullPage: true,
      });
      const downloaded = page.waitForEvent("download");
      await page.getByRole("button", { name: "导出路线", exact: true }).click();
      const file = await downloaded;
      expect(file.suggestedFilename()).toBe("Python 从入门到实践-学习路线.md");
      const contents = await readFile((await file.path())!, "utf8");
      expect(contents).toContain("学会用 Python 解决日常的小问题");
      expect(contents).toContain("A1 认识 Python 与第一个程序");
      expect(contents).toContain("掌握度：100%");
      expect(contents).toContain("不包含教材正文、笔记或完整账号数据");
      expect(contents).not.toContain("Hello, learning!");
      await page
        .getByRole("button", { name: "收起思维导图", exact: true })
        .click();
      await expect(map).toHaveCount(0);
      await expect(page.locator(".roadmap-list li")).toHaveCount(3);
      await page.getByRole("combobox", { name: "当前学习计划" }).click();
      await page.getByRole("option", { name: "读懂设计的基本语言" }).click();
      await expect(page.locator(".roadmap-list li")).toHaveCount(1);
      await expect(map).toHaveCount(0);
      await page.getByRole("button", { name: "思维导图", exact: true }).click();
      await expect(map.locator("svg")).toContainText("从留白开始理解版式");
      await expect(map.locator("svg")).not.toContainText(/认识\s*Python/);
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
    });
  }
}

test("mindmap code fences ignore active content and unknown languages remain readable", async ({
  page,
}) => {
  const demo = await mock(page);
  await page.route("**/projects/1/nodes", async (route) => {
    const data = await (
      await demo.handle(route.request().url(), { method: "GET" })
    ).json();
    data.items[0].description = [
      "```markmap",
      "# 安全导图",
      "## [链接文字](javascript:alert(1))",
      "## ![图片文字](https://untrusted.invalid/a.png)",
      "## <img src=x onerror=alert(1)>普通文字",
      "```",
      "```unknown-language",
      "raw <value> & text",
      "```",
    ].join("\n");
    await route.fulfill({ json: data });
  });
  const external: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("untrusted.invalid"))
      external.push(request.url());
  });
  await page.goto("/study?project=1&chapter=11");
  await expect(page.locator(".code-block").last().locator("pre")).toHaveText(
    "raw <value> & text\n",
  );
  await page.getByRole("button", { name: "查看思维导图", exact: true }).click();
  const map = page.getByRole("region", { name: "思维导图", exact: true });
  await expect(map.locator("svg")).toContainText("链接文字");
  await expect(map.locator("svg")).toContainText("图片文字");
  await expect(map.locator("img, a, script, foreignObject")).toHaveCount(0);
  expect(external).toEqual([]);
  await page.getByRole("button", { name: "查看源码", exact: true }).click();
  await expect(map).toHaveCount(0);
  await expect(
    page.locator(".code-block").first().locator("pre"),
  ).toContainText("# 安全导图");
});

test("empty roadmap disables mindmap and export and denied clipboard shows manual fallback", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async () => {
          throw new Error("denied");
        },
      },
    }),
  );
  await mock(page);
  await page.route("**/projects/1/nodes", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.goto("/roadmap?project=1");
  await expect(
    page.getByRole("button", { name: "思维导图", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "导出路线", exact: true }),
  ).toBeDisabled();
  await page.unroute("**/projects/1/nodes");
  await page.goto("/study?project=1&chapter=11");
  await page.getByRole("button", { name: "复制代码", exact: true }).click();
  await expect(page.getByText("复制失败，请选中代码手动复制")).toBeVisible();
  await expect(page.locator(".code-block pre")).toContainText(
    "Hello, learning!",
  );
});
for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test.describe(`${width}px / ${theme}`, () => {
      test.use({ viewport: { width, height: 960 } });
      for (const [path, title] of pages)
        test(`${path} loads with no overflow`, async ({ page }, testInfo) => {
          const errors: string[] = [];
          page.on("pageerror", (error) => errors.push(error.message));
          await page.addInitScript(
            (theme) => localStorage.setItem("learn.theme", theme),
            theme,
          );
          await mock(page);
          await page.goto(path);
          await expect(page.getByRole("heading", { level: 1 })).toContainText(
            title,
          );
          await expect(page.locator("html")).toHaveAttribute(
            "data-theme",
            theme,
          );
          await expect(page.locator("#main-content")).toBeVisible();
          await expect(page.locator(".page-heading .eyebrow")).toHaveCount(0);
          await expect
            .poll(() =>
              page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
              ),
            )
            .toBe(true);
          expect(errors).toEqual([]);
          if (
            (path === "/" && width === 1440 && theme === "light") ||
            (path === "/library" && width === 390 && theme === "dark")
          ) {
            await page.screenshot({
              path: testInfo.outputPath("layout.png"),
              fullPage: true,
            });
          }
        });
    });
  }
test("empty state creates a project and enters the workbench", async ({
  page,
}) => {
  await mock(page, true);
  await page.goto("/study");
  await expect(
    page.getByRole("heading", { name: "暂无学习计划" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "添加学习计划" }).click();
  await expect(page.getByLabel("学习目标", { exact: true })).toBeFocused();
  await page
    .getByLabel("学习目标", { exact: true })
    .fill("从零开始学习概率论，理解生活中的不确定性。");
  await page.getByRole("button", { name: "创建学习计划" }).click();
  await expect(page).toHaveURL(/\/study\?project=\d+/);
  await expect(
    page.getByRole("heading", { name: "暂无学习章节" }),
  ).toBeVisible();
});
test("workbench saves notes and project changes clear the previous draft", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/study?project=1&chapter=11");
  await page.getByRole("tab", { name: "笔记" }).click();
  await page
    .getByLabel("记下你的理解")
    .fill("用自己的语言解释程序的执行顺序。");
  await page.getByRole("button", { name: "保存笔记" }).click();
  await expect(page.locator(".note-card")).toContainText(
    "用自己的语言解释程序的执行顺序。",
  );
  await page.getByLabel("记下你的理解").fill("旧计划的草稿");
  await page.getByRole("combobox", { name: "当前学习计划" }).click();
  await page.getByRole("option", { name: "读懂设计的基本语言" }).click();
  await page
    .getByRole("button", { name: "放弃未保存内容", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "从留白开始理解版式" }),
  ).toBeVisible();
  await expect(page).not.toHaveURL(/chapter=/);
  await page.getByRole("link", { name: /从留白开始理解版式/ }).click();
  await page.getByRole("tab", { name: "笔记" }).click();
  await expect(page.getByLabel("记下你的理解")).toHaveValue("");
});
test("reading completion preserves mastery and uses completion statistics", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/study?project=1&chapter=12");
  const update = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/v2/nodes/12"),
  );
  await page.getByRole("button", { name: "标记为已学完", exact: true }).click();
  expect((await update).postDataJSON()).toEqual({ status: "done" });
  await expect(
    page.getByRole("button", { name: "已完成学习", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "学习看板", exact: true }).click();
  await expect(
    page.locator(".stat-card").filter({ hasText: "已完成章节" }),
  ).toContainText("2");
  await page.reload();
  await expect(
    page.locator(".stat-card").filter({ hasText: "已完成章节" }),
  ).toContainText("2");
});

test("review requires revealing the answer and advances after rating", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/review");
  await expect(
    page.getByRole("button", { name: "记得", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "查看答案" }).click();
  await expect(page.locator(".review-answer")).toBeVisible();
  await page.getByRole("button", { name: "记得", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "今日复习已完成" }),
  ).toBeVisible();
});
test("quiz hides expected answers until submit", async ({ page }) => {
  await mock(page);
  await page.goto("/quiz");
  await page.getByRole("button", { name: /Python 入门/ }).click();
  await expect(page.getByText("参考答案：print")).toHaveCount(0);
  await page.getByRole("textbox", { name: "第 1 题答案" }).fill("print");
  await page.getByRole("button", { name: "提交答案" }).click();
  await expect(
    page.getByRole("heading", { name: "答对 1 / 1 题" }),
  ).toBeVisible();
});
test("ACCOUNT_CHANGED hides old content and prevents further business requests", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/study?project=1&chapter=11");
  await expect(
    page.getByRole("heading", { name: "认识 Python 与第一个程序" }),
  ).toBeVisible();
  await page.route("**/api/v2/projects/1/notes", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "ACCOUNT_CHANGED",
          message: "changed",
          retryable: false,
        },
      }),
    }),
  );
  await page.getByRole("tab", { name: "笔记" }).click();
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(page.getByText("认识 Python 与第一个程序")).toHaveCount(0);
});
test("storage event clears the account immediately", async ({ page }) => {
  await mock(page);
  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "知识问答" })).toBeVisible();
  await page.evaluate(() =>
    dispatchEvent(
      new StorageEvent("storage", {
        key: "aethericai-community-access-token",
        newValue: "new-login",
      }),
    ),
  );
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "向助教提问" })).toHaveCount(
    0,
  );
});
test("server errors have a retry path, never appear as an empty workspace", async ({
  page,
}) => {
  await mock(page);
  let unavailable = true;
  await page.route("**/api/v2/projects", (route) =>
    unavailable
      ? route.fulfill({
          status: 500,
          contentType: "application/json",
          body: '{"error":{"code":"INTERNAL","message":"暂时不可用","retryable":true}}',
        })
      : route.fallback(),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("暂时不可用");
  unavailable = false;
  await page.getByRole("button", { name: "重新加载" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "每一份好奇",
  );
});
test("chat submits once, restores the saved answer after refresh and keeps accounts separate", async ({
  page,
}) => {
  await mock(page);
  let count = 0;
  page.on("request", (req) => {
    if (req.url().endsWith("/chat-jobs") && req.method() === "POST") count++;
  });
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "向助教提问" }).fill("如何开始？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant")).toContainText(
    "这是一段本地演示回答。",
  );
  expect(count).toBe(1);
  await page.reload();
  await expect(page.locator(".message.assistant")).toContainText(
    "这是一段本地演示回答。",
  );
  expect(count).toBe(1);
  await page.getByRole("combobox", { name: "当前学习计划" }).click();
  await page.getByRole("option", { name: "读懂设计的基本语言" }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(0);
});

for (const width of [390, 1440]) {
  test(`library preview, download and confirmed deletion at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    await page.goto("/library");
    const row = page
      .locator(".file-row")
      .filter({ hasText: "Python 基础学习笔记.md" });
    await row.getByRole("button", { name: "查看", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Python 基础学习笔记.md" });
    await expect(dialog).toContainText("这是一段资料内容的本地演示。");
    await page.screenshot({ path: testInfo.outputPath("library-preview.png") });
    const box = (await dialog.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await page.keyboard.press("Escape");
    await expect(
      row.getByRole("button", { name: "查看", exact: true }),
    ).toBeFocused();
    const ready = page.waitForEvent("download");
    await row.getByRole("button", { name: "下载", exact: true }).click();
    expect((await ready).suggestedFilename()).toBe("Python 基础学习笔记.md");
    await row.getByRole("button", { name: "删除", exact: true }).click();
    await page.getByRole("button", { name: "取消", exact: true }).click();
    await expect(page.locator(".file-row")).toHaveCount(2);
    await row.getByRole("button", { name: "删除", exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.locator(".file-row")).toHaveCount(1);
    await page.reload();
    await expect(page.locator(".file-row")).toHaveCount(1);
  });
}
test("job progress reconnects and binds the stream to the page owner", async ({
  page,
}) => {
  await mock(page);
  const job = {
    jobId: "j1",
    kind: "index",
    subject: "f1",
    state: "running",
    progress: { done: 0, total: 1 },
    error: null,
    updatedAt: new Date().toISOString(),
  };
  await page.route("**/api/v2/projects/1/materials", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({
            fileId: "f1",
            sha256: "demo",
            sizeBytes: 4,
            jobId: "j1",
          }),
        })
      : route.fallback(),
  );
  await page.route("**/api/v2/jobs/j1", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(job),
    }),
  );
  let streams = 0;
  await page.route("**/api/v2/jobs/j1/events?*", (route) => {
    expect(new URL(route.request().url()).searchParams.get("__le_owner")).toBe(
      "demo-learner",
    );
    streams++;
    return route.fulfill({
      contentType: "text/event-stream",
      body: `retry: 250\nevent: progress\ndata: ${JSON.stringify({ ...job, state: streams > 1 ? "done" : "running" })}\n\n`,
    });
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("test"),
  });
  await expect(page.locator(".job-status")).toContainText("资料索引已完成");
  expect(streams).toBeGreaterThanOrEqual(2);
  await expect(
    page.getByRole("button", { name: "上传资料", exact: true }),
  ).toBeEnabled();
});
test("entry ticket is removed from the URL without being saved", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/?ticket=test-entry-ticket");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "每一份好奇",
  );
  await expect(page).toHaveURL(/\/$/);
  expect(
    await page.evaluate(() => sessionStorage.getItem("le.ticket")),
  ).toBeNull();
});

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`project picker opens downwards at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 800 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/study");
      await expect(page.locator(".project-card")).toHaveCount(2);
      await expect(page.locator(".chapter-card")).toHaveCount(0);
      await page.getByRole("link", { name: /Python 从入门到实践/ }).click();
      const trigger = page.getByRole("combobox", { name: "当前学习计划" });
      await trigger.click();
      const list = page.getByRole("listbox", { name: "学习计划", exact: true });
      await expect(list).toBeVisible();
      await expect(trigger).toHaveAttribute("aria-expanded", "true");
      const buttonBox = (await trigger.boundingBox())!;
      const menuBox = (await list.boundingBox())!;
      expect(menuBox.y).toBeGreaterThanOrEqual(buttonBox.y + buttonBox.height);
      expect(menuBox.x).toBeGreaterThanOrEqual(0);
      expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(width);
      await expect(
        page.getByRole("option", { name: "暂无学习计划" }),
      ).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath("picker.png") });
      await page.locator(".topbar").click({ position: { x: 5, y: 5 } });
      await expect(list).toHaveCount(0);
    });
  }
test("project picker supports keyboard selection and escape", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/study");
  const trigger = page.getByRole("combobox", { name: "当前学习计划" });
  await trigger.focus();
  await trigger.press("ArrowDown");
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await trigger.press("End");
  await trigger.press("Escape");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(trigger).toBeFocused();
  await expect(trigger).toContainText("选择学习计划");
  await trigger.press("Enter");
  await trigger.press("End");
  await trigger.press("Enter");
  await expect(page).toHaveURL(/project=2/);
  await expect(trigger).toContainText("读懂设计的基本语言");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
});
test("empty project picker stays disabled", async ({ page }) => {
  await mock(page, true);
  await page.goto("/");
  const trigger = page.getByRole("combobox", { name: "当前学习计划" });
  await expect(trigger).toContainText("暂无学习计划");
  await expect(trigger).toBeDisabled();
});

for (const [width, theme] of [
  [1440, "light"],
  [390, "dark"],
] as const)
  test(`library search filters and clears at ${width}px in ${theme}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await page.addInitScript(
      (theme) => localStorage.setItem("learn.theme", theme),
      theme,
    );
    await mock(page);
    await page.goto("/library");
    const search = page.getByRole("searchbox", { name: "搜索资料" });
    await expect(page.locator(".file-row")).toHaveCount(2);
    await search.fill("Python");
    await expect(page.locator(".file-row")).toHaveCount(1);
    await expect(page.locator(".file-row")).toContainText(
      "Python 基础学习笔记.md",
    );
    await page.screenshot({
      path: testInfo.outputPath("search.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "清空搜索资料" }).click();
    await expect(search).toHaveValue("");
    await expect(search).toBeFocused();
    await expect(page.locator(".file-row")).toHaveCount(2);
    await search.fill("不存在的资料");
    await expect(page.getByText("没有找到匹配的资料。")).toBeVisible();
    await search.press("Escape");
    await expect(search).toHaveValue("");
    await expect(search).toBeFocused();
    await expect(page.locator(".file-row")).toHaveCount(2);
  });

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`workbench has separate directory and lesson at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/study");
      await expect(page.locator(".project-card")).toHaveCount(2);
      await expect(page.locator(".chapter-card")).toHaveCount(0);
      await page.getByRole("link", { name: /Python 从入门到实践/ }).click();
      await expect(
        page.getByRole("heading", { name: "课程章节", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".chapter-card")).toHaveCount(3);
      await expect(page.getByRole("tablist")).toHaveCount(0);
      const first = page.locator(".chapter-card").first();
      const directory = (await first.boundingBox())!;
      const main = (await page.locator("#main-content").boundingBox())!;
      expect(directory.width).toBeGreaterThan(main.width * 0.75);
      await page.screenshot({
        path: testInfo.outputPath("chapters.png"),
        fullPage: true,
      });
      await page.getByRole("link", { name: /变量，让信息有个名字/ }).click();
      await expect(page).toHaveURL(/project=1&chapter=12/);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "变量，让信息有个名字",
      );
      await expect(
        page.getByRole("heading", { name: "给信息起一个名字", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".chapter-directory")).toHaveCount(0);
      const lesson = (await page.locator(".lesson-panel").boundingBox())!;
      expect(lesson.width).toBeGreaterThan(main.width * 0.75);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath("lesson.png"),
        fullPage: true,
      });
      await page.reload();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "变量，让信息有个名字",
      );
      await page.getByRole("link", { name: "返回章节目录" }).click();
      await expect(page.locator(".chapter-card")).toHaveCount(3);
      await expect(page.getByRole("tablist")).toHaveCount(0);
      await page.goBack();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "变量，让信息有个名字",
      );
      if (width === 390)
        await page.getByRole("button", { name: "打开导航" }).click();
      await page.getByRole("link", { name: "学习工作台", exact: true }).click();
      await expect(page).toHaveURL(/\/study$/);
      await expect(page.locator(".project-card")).toHaveCount(2);
      await page.getByRole("link", { name: /读懂设计的基本语言/ }).click();
      await expect(page).toHaveURL(/\/study\?project=2$/);
      await expect(page.locator(".chapter-card")).toHaveCount(1);
    });
  }

test("roadmap opens the selected chapter and invalid chapters have a return path", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/roadmap");
  await page
    .getByRole("link", { name: "用条件与循环解决问题", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "用条件与循环解决问题",
  );
  await expect(page).toHaveURL(/chapter=13/);
  await page.goto("/study?project=1&chapter=21");
  await expect(
    page.getByRole("heading", { name: "找不到该章节" }),
  ).toBeVisible();
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await page.getByRole("link", { name: "返回章节目录" }).click();
  await expect(page.locator(".chapter-card")).toHaveCount(3);
});

test("model settings show the gateway catalog empty state without a credential form", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/v2/models", (route) =>
    route.fulfill({
      json: { items: [], selectedModel: "", selectedAvailable: false },
    }),
  );
  await page.goto("/models");
  await expect(
    page.getByRole("heading", { name: "暂无可用模型" }),
  ).toBeVisible();
  await expect(page.getByLabel("API Key", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("模型由官网提供，使用当前账号的可用积分。"),
  ).toBeVisible();
});

for (const width of [390, 1440]) {
  test(`gateway model preference persists and failed saves preserve it at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let selectedModel = "deepseek-test";
    let saves = 0;
    let fail = true;
    await page.route("**/api/v2/models", (route) =>
      route.fulfill({
        json: {
          items: [
            { id: "deepseek-test", provider: "deepseek" },
            { id: "qwen-test", provider: "alibaba" },
          ],
          selectedModel,
          selectedAvailable: true,
        },
      }),
    );
    await page.route("**/models/selection", async (route) => {
      saves++;
      expect(route.request().postDataJSON()).toEqual({ model: "qwen-test" });
      if (fail)
        await route.fulfill({
          status: 503,
          json: {
            error: {
              code: "GATEWAY_UNAVAILABLE",
              message: "模型服务暂不可用",
              retryable: true,
            },
          },
        });
      else {
        selectedModel = route.request().postDataJSON().model;
        await route.fulfill({ json: { selectedModel } });
      }
    });
    await page.goto("/models");
    const picker = page.getByRole("combobox", { name: "主模型", exact: true });
    await picker.click();
    await page.getByRole("option", { name: "qwen-test", exact: true }).click();
    await expect(page.locator(".primary-model-summary")).toContainText(
      "deepseek-test",
    );
    const save = page.getByRole("button", { name: "设为主模型", exact: true });
    await save.click();
    await expect(page.getByRole("alert")).toContainText("模型服务暂不可用");
    await expect(page.locator(".primary-model-summary")).toContainText(
      "deepseek-test",
    );
    expect(saves).toBe(1);
    fail = false;
    await save.click();
    await expect(page.locator(".primary-model-summary")).toContainText(
      "qwen-test",
    );
    await page.reload();
    await expect(picker).toContainText("qwen-test");
    expect(saves).toBe(2);
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  });
}

for (const width of [390, 1440]) {
  for (const outcome of ["done", "failed"] as const) {
    test(`automatic roadmap survives refresh and ends ${outcome} at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 960 });
      const demo = await mock(page, true);
      let state: "queued" | "running" | "done" | "failed" = "queued";
      let phase = "queued";
      let creates = 0;
      let manualSubmissions = 0;
      const startedAt = new Date().toISOString();
      await page.route("**/api/v2/projects", async (route) => {
        const req = route.request();
        const response = await demo.handle(req.url(), {
          method: req.method(),
          body: req.postData() || undefined,
        });
        const body = await response.json();
        if (req.method() === "POST") {
          expect(req.postDataJSON().generateRoadmap).toBe(true);
          creates++;
          body.generation = { jobId: "auto-roadmap", state: "queued" };
        }
        await route.fulfill({ status: response.status, json: body });
      });
      await page.route("**/projects/*/nodes", (route) =>
        route.fulfill({ json: { items: [] } }),
      );
      await page.route("**/roadmap-jobs", async (route) => {
        manualSubmissions++;
        await route.fulfill({
          status: 202,
          json: { jobId: "auto-roadmap", state },
        });
      });
      // Simulate an unavailable event stream: the existing reconnect poll must recover.
      await page.route("**/jobs/auto-roadmap/events?*", (route) =>
        route.abort(),
      );
      await page.route("**/jobs/auto-roadmap", (route) =>
        route.fulfill({
          json: {
            jobId: "auto-roadmap",
            kind: "roadmap",
            subject: "test",
            state,
            progress: {
              phase,
              attemptStartedAt: startedAt,
              estimatedModelMs: 45000,
              estimateSource: "history",
              queueMs: 100,
              modelMs: 1200,
              totalMs: 1350,
            },
            error: state === "failed" ? "测试模型暂时不可用，请重试" : null,
            updatedAt: new Date().toISOString(),
          },
        }),
      );
      await page.goto("/");
      await page
        .getByLabel("学习目标", { exact: true })
        .fill("测试自动创建和任务恢复");
      await page.getByRole("button", { name: "创建学习计划" }).click();
      await expect(page).toHaveURL(/\/study\?project=\d+/);
      const bar = page.getByRole("progressbar", { name: "学习路线生成进度" });
      await expect(bar).toHaveAttribute("aria-valuenow", "3");
      await expect(page.locator(".generation-progress")).toContainText(
        "排队等待模型",
      );
      await expect(page.locator(".generation-progress")).toContainText(
        "连接恢复中，剩余时间暂不可用",
      );
      state = "running";
      phase = "generating";
      await expect(page.locator(".generation-progress")).toContainText(
        "正在规划章节与学习顺序",
      );
      await page.reload();
      await expect(page.locator(".generation-progress")).toContainText(
        "根据近期同模型生成耗时估算",
      );
      expect(
        Number(await bar.getAttribute("aria-valuenow")),
      ).toBeLessThanOrEqual(90);
      if (outcome === "done") {
        phase = "saving";
        await expect(bar).toHaveAttribute("aria-valuenow", "96");
        state = "done";
        await expect(bar).toHaveAttribute("aria-valuenow", "100");
        await expect(page.locator(".generation-timings")).toContainText(
          "1.35 秒",
        );
        await page.getByRole("button", { name: "完成", exact: true }).click();
        await expect(page).toHaveURL(/\/study$/);
        await page.locator(".project-card").first().click();
        await expect(page.locator(".job-status")).toHaveCount(0);
      } else {
        state = "failed";
        await expect(page.locator(".job-status")).toContainText("生成失败");
        await expect(bar).toHaveCount(0);
        await expect(
          page.getByRole("button", { name: "AI 生成学习路线", exact: true }),
        ).toBeEnabled();
      }
      expect(creates).toBe(1);
      expect(manualSubmissions).toBe(0);
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
    });
  }
}

for (const width of [390, 1440]) {
  test(`roadmap and lesson generation track jobs and timings at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    const demo = await mock(page, true);
    let pid = 0;
    let roadmapReady = false;
    let lessonReady = false;
    let submissions = 0;
    const node = () => ({
      id: 501,
      projectId: pid,
      code: "1.1",
      title: "认识变量",
      description: lessonReady
        ? "## 核心概念\n\n变量让数据有一个名字。\n\n" +
          "通过实际例子理解变量并验证自己的理解。".repeat(30)
        : "理解变量并完成一个例子。",
      stage: "base",
      estHours: 2,
      difficulty: 1,
      mastery: 0,
      status: "pending",
      contentVersion: lessonReady ? 1 : 0,
      createdAt: new Date().toISOString(),
    });
    await page.route("**/projects/*/nodes", async (route) => {
      pid = Number(
        route
          .request()
          .url()
          .match(/projects\/(\d+)/)?.[1],
      );
      await route.fulfill({ json: { items: roadmapReady ? [node()] : [] } });
    });
    await page.route("**/roadmap-jobs", async (route) => {
      submissions++;
      await route.fulfill({
        status: 202,
        json: { jobId: "test-roadmap", state: "queued" },
      });
    });
    await page.route("**/api/v2/projects", async (route) => {
      const req = route.request();
      const response = await demo.handle(req.url(), {
        method: req.method(),
        body: req.postData() || undefined,
      });
      const body = await response.json();
      if (req.method() === "POST") {
        expect(req.postDataJSON().generateRoadmap).toBe(true);
        submissions++;
        body.generation = { jobId: "test-roadmap", state: "queued" };
      }
      await route.fulfill({ status: response.status, json: body });
    });
    await page.route("**/lesson-jobs", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ force: false });
      submissions++;
      await route.fulfill({
        status: 202,
        json: { jobId: "test-lesson", state: "queued" },
      });
    });
    await page.route("**/jobs/test-*", async (route) => {
      const lesson = route.request().url().endsWith("test-lesson");
      if (lesson) lessonReady = true;
      else roadmapReady = true;
      await route.fulfill({
        json: {
          jobId: lesson ? "test-lesson" : "test-roadmap",
          kind: lesson ? "lesson" : "roadmap",
          subject: "test",
          state: "done",
          progress: {
            done: 1,
            total: 1,
            queueMs: 100,
            modelMs: 1200,
            totalMs: 1350,
          },
          error: null,
          updatedAt: new Date().toISOString(),
        },
      });
    });
    await page.goto("/");
    await page
      .getByLabel("学习目标", { exact: true })
      .fill("学习 Python，理解变量");
    await page.getByRole("button", { name: "创建学习计划" }).click();
    await expect(page.locator(".chapter-card")).toHaveCount(1);
    await expect(page.locator(".generation-timings")).toContainText("1.35 秒");
    await page.locator(".chapter-card").click();
    await page
      .getByRole("button", { name: "生成本节教材", exact: true })
      .click();
    await expect(page.locator(".prose")).toContainText("变量让数据有一个名字");
    await expect(page.locator(".generation-timings")).toContainText("1.20 秒");
    await expect(
      page.getByRole("button", { name: "重新生成本节教材" }),
    ).toBeDisabled();
    const box = await page
      .getByRole("checkbox", { name: "重新生成并替换本节教材" })
      .boundingBox();
    expect(box?.width).toBeLessThanOrEqual(20);
    expect(box?.height).toBeLessThanOrEqual(20);
    expect(submissions).toBe(2);
    await page.reload();
    await expect(page.locator(".generation-timings")).toContainText("1.35 秒");
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: testInfo.outputPath("generated-lesson.png"),
      fullPage: true,
    });
  });
}

for (const width of [390, 1440]) {
  test(`assessment generation, grading recovery and card scheduling at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let generatedQuiz = false;
    let generatedCards = false;
    let quizCalls = 0;
    let cardCalls = 0;
    let gradeCalls = 0;
    let gradeStarted = false;
    let gradeDone = false;
    let rated = false;
    const grade = {
      correct: 1,
      total: 1,
      score: 1,
      results: [
        {
          questionId: 62,
          correct: true,
          expected: "print",
          explanation: "输出内容。",
          userAnswer: "输出函数 print",
          feedback: "关键要点正确。",
        },
      ],
    };
    const card = () => ({
      id: 301,
      projectId: 1,
      nodeId: 11,
      front: "新卡片：变量用途是什么？",
      back: "给数据命名。",
      cardType: "basic",
      state: 1,
      step: 1,
      reps: Number(rated),
      stability: 1,
      nextReview: rated ? "2030-01-01T00:00:00Z" : new Date().toISOString(),
      suspended: false,
    });
    await page.route("**/projects/1/quizzes", (route) =>
      route.fulfill({
        json: {
          items: generatedQuiz
            ? [
                {
                  id: 61,
                  title: "新生成的章节测验",
                  quizType: "mixed",
                  createdAt: new Date().toISOString(),
                },
              ]
            : [],
        },
      }),
    );
    await page.route("**/projects/1/quiz-jobs", (route) => {
      expect(route.request().postDataJSON()).toEqual({
        nodeIds: [11],
        count: 1,
        qtype: "mixed",
      });
      quizCalls++;
      return route.fulfill({
        status: 202,
        json: { jobId: "assessment-quiz", state: "queued" },
      });
    });
    await page.route("**/projects/1/card-jobs", (route) => {
      expect(route.request().postDataJSON().nodeIds).toEqual([11]);
      cardCalls++;
      return route.fulfill({
        status: 202,
        json: { jobId: "assessment-cards", state: "queued" },
      });
    });
    await page.route("**/jobs/assessment-*", (route) => {
      const kind = route.request().url().endsWith("quiz") ? "quiz" : "cards";
      if (kind === "quiz") generatedQuiz = true;
      else generatedCards = true;
      return route.fulfill({
        json: {
          jobId: `assessment-${kind}`,
          kind,
          subject: "project:1",
          state: "done",
          progress: {
            count: 1,
            done: 1,
            total: 1,
            modelMs: 1000,
            queueMs: 10,
            totalMs: 1050,
          },
          error: null,
          updatedAt: new Date().toISOString(),
        },
      });
    });
    await page.route("**/quizzes/61/grade-jobs", (route) => {
      expect(route.request().postDataJSON().answers).toEqual({
        "62": "输出函数 print",
      });
      gradeCalls++;
      gradeStarted = true;
      return route.fulfill({
        status: 202,
        json: { jobId: "pending-grade", state: "queued" },
      });
    });
    await page.route("**/quizzes/61/grade-job", (route) =>
      route.fulfill({
        json: gradeStarted
          ? { jobId: "pending-grade", state: gradeDone ? "done" : "running" }
          : null,
      }),
    );
    await page.route("**/quizzes/61/result", (route) =>
      route.fulfill({ json: gradeDone ? grade : null }),
    );
    await page.route("**/jobs/pending-grade", (route) =>
      route.fulfill({
        json: {
          jobId: "pending-grade",
          kind: "grade",
          subject: "quiz:61",
          state: gradeDone ? "done" : "running",
          progress: {},
          error: null,
          updatedAt: new Date().toISOString(),
        },
      }),
    );
    await page.route("**/jobs/pending-grade/events?*", (route) =>
      route.fulfill({
        contentType: "text/event-stream",
        body: "event: end\ndata: {}\n\n",
      }),
    );
    await page.route("**/review/due?*", (route) =>
      route.fulfill({
        json: { items: generatedCards && !rated ? [card()] : [] },
      }),
    );
    await page.route("**/projects/1/cards", (route) =>
      route.fulfill({ json: { items: generatedCards ? [card()] : [] } }),
    );
    await page.route("**/review/301", (route) => {
      expect(route.request().postDataJSON()).toEqual({
        rating: 3,
        expectedReps: 0,
      });
      rated = true;
      return route.fulfill({ json: card() });
    });
    await page.goto("/quiz");
    await expect(
      page.getByRole("button", { name: "生成测验", exact: true }),
    ).toBeDisabled();
    const checkbox = page.getByRole("checkbox", { name: /A1 认识 Python/ });
    await checkbox.check();
    const bounds = await checkbox.boundingBox();
    expect(bounds?.width).toBeLessThanOrEqual(20);
    expect(bounds?.height).toBeLessThanOrEqual(20);
    await page.getByLabel("生成数量").fill("1");
    await page.getByRole("button", { name: "生成测验", exact: true }).click();
    await page.getByRole("button", { name: /新生成的章节测验/ }).click();
    await expect(page.getByText("参考答案：print")).toHaveCount(0);
    await page
      .getByRole("textbox", { name: "第 1 题答案" })
      .fill("输出函数 print");
    await page.getByRole("button", { name: "提交答案" }).click();
    await expect(page.getByRole("button", { name: "批改中…" })).toBeDisabled();
    await page.reload();
    await expect(page.getByRole("button", { name: "批改中…" })).toBeDisabled();
    gradeDone = true;
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "答对 1 / 1 题" }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "第 1 题答案" }),
    ).toHaveValue("输出函数 print");
    await expect(page.getByText("关键要点正确。")).toBeVisible();
    expect(gradeCalls).toBe(1);
    expect(quizCalls).toBe(1);
    await page.goto("/review");
    await page.getByRole("combobox", { name: "复习章节" }).click();
    await page.getByRole("option", { name: /A1 认识 Python/ }).click();
    await page.getByLabel("生成数量").fill("1");
    await page.getByRole("button", { name: "生成复习卡", exact: true }).click();
    await expect(page.locator(".review-panel")).toContainText(
      "新卡片：变量用途是什么？",
    );
    await expect(page.locator(".review-answer")).toHaveCount(0);
    await page.getByRole("button", { name: "查看答案", exact: true }).click();
    await expect(page.locator(".review-answer")).toContainText("给数据命名。");
    await page.getByRole("button", { name: "记得", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "今日复习已完成" }),
    ).toBeVisible();
    await expect(page.locator(".review-schedule")).toContainText("已复习 1 次");
    await page.reload();
    await expect(page.locator(".review-schedule")).toContainText("已复习 1 次");
    expect(cardCalls).toBe(1);
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: testInfo.outputPath("review-schedule.png"),
      fullPage: true,
    });
  });
}

for (const width of [390, 1440]) {
  test(`practice coach and polish preserve separate results across refresh at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let calls = 0;
    page.on("request", (req) => {
      if (req.url().endsWith("/polish-jobs") && req.method() === "POST")
        calls++;
    });
    await page.goto("/tools?tool=polish");
    const source = page.getByRole("textbox", { name: "原文", exact: true });
    await source.fill("每周学习3小时，使用 `print(3)` 练习。");
    await page.getByRole("button", { name: "开始润色", exact: true }).click();
    await expect(page.getByRole("region", { name: "润色结果" })).toContainText(
      "每周学习3小时",
    );
    await expect(source).toHaveValue("每周学习3小时，使用 `print(3)` 练习。");
    await page.reload();
    await expect(page.getByRole("region", { name: "润色结果" })).toContainText(
      "print(3)",
    );
    await expect(source).toHaveValue("每周学习3小时，使用 `print(3)` 练习。");
    expect(calls).toBe(1);
    await source.fill("这是一份新原文");
    await expect(
      page.getByText("这是上一份原文的结果；当前原文有修改，请重新润色。"),
    ).toBeVisible();
    await page.getByRole("button", { name: /分步练习教练/ }).click();
    await expect(
      page.getByRole("checkbox", { name: "结合资料库回答" }),
    ).toHaveCSS("width", "18px");
    await expect(
      page.getByRole("checkbox", { name: "结合资料库回答" }),
    ).toHaveCSS("appearance", "none");
    await page
      .getByRole("textbox", { name: "向教练反馈" })
      .fill("带我练习变量");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(page.locator(".message.assistant")).toContainText("演示回答");
    await page.screenshot({ path: testInfo.outputPath("practice-coach.png") });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.goto("/chat");
    await expect(page.locator(".message.assistant")).toHaveCount(0);
  });
}

test("accepted polish task is recovered when its submission response is lost", async ({
  page,
}) => {
  const demo = await mock(page);
  await page.goto("/tools?tool=polish");
  const source = page.getByRole("textbox", { name: "原文", exact: true });
  await source.fill("第一份学习笔记");
  await page.getByRole("button", { name: "开始润色", exact: true }).click();
  await expect(page.getByRole("region", { name: "润色结果" })).toContainText(
    "第一份学习笔记",
  );
  let calls = 0;
  await page.route("**/polish-jobs", async (route) => {
    calls++;
    const req = route.request();
    await demo.handle(req.url(), {
      method: req.method(),
      body: req.postData() || undefined,
    });
    await route.abort("failed");
  });
  await source.fill("第二份学习笔记");
  await page.getByRole("button", { name: "开始润色", exact: true }).click();
  await expect(page.getByRole("region", { name: "润色结果" })).toContainText(
    "第二份学习笔记",
  );
  expect(calls).toBe(1);
});

for (const width of [390, 1440]) {
  test(`lesson renders formulas and reveals self-test answers only on request at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    const demo = await mock(page);
    await page.route("**/projects/1/nodes", async (route) => {
      const response = await demo.handle(route.request().url(), {
        method: "GET",
      });
      const data = await response.json();
      data.items[0].description = [
        "## 核心概念",
        "行内公式 $x^2$。",
        "$$",
        "\\frac{1}{2}",
        "$$",
        "## 📝 自测练习",
        "1. 求一半的表示。",
        "",
        "```text",
        "### 自测参考答案",
        "代码中的标题应保持原样。",
        "```",
        "",
        "### 自测参考答案",
        "答案测试标记：$x=1$。",
        "",
        "## 学习小结",
        "小结不应随答案收起。",
      ].join("\n\n");
      data.items[0].contentVersion = 1;
      await route.fulfill({ json: data });
    });
    await page.goto("/study?project=1&chapter=11");
    await expect(page.locator(".prose .katex-display .katex")).toBeVisible();
    await expect(page.getByText("答案测试标记", { exact: false })).toHaveCount(
      0,
    );
    await expect(page.getByText("小结不应随答案收起。")).toBeVisible();
    await expect(page.locator(".prose pre")).toContainText("自测参考答案");
    const button = page.getByRole("button", { name: "显示答案", exact: true });
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await button.click();
    await expect(page.locator(".exercise-answer-content")).toContainText(
      "答案测试标记",
    );
    await expect(page.locator(".exercise-answer-content .katex")).toBeVisible();
    await page.getByRole("button", { name: "收起答案", exact: true }).click();
    await expect(page.locator(".exercise-answer-content")).toHaveCount(0);
    await button.click();
    await page.reload();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  });
}

test("gateway mode restores supplier cards without accepting a personal key", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/models");
  await expect(page.locator(".provider-preset")).toHaveCount(33);
  await page
    .getByRole("button", { name: "自定义添加新模型", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "添加新供应商" }),
  ).toBeVisible();
  await expect(page.getByLabel("API Key", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "由官网网关管理", exact: true }),
  ).toBeDisabled();
});

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`personal key import selects, reloads and removes owned models at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      let connection:
        | {
            id: string;
            provider: string;
            name: string;
            baseUrl: string;
            models: string[];
            revision: string;
          }
        | undefined;
      let selectedModel = "";
      let fail = true;
      const ids: string[] = [];
      await page.route("**/api/v2/models", (route) =>
        route.fulfill({
          json: {
            items: connection
              ? connection.models.map((id) => ({
                  id,
                  provider: connection!.id,
                }))
              : [],
            selectedModel,
            selectedAvailable: !!selectedModel,
            source: "personal",
            providerImportEnabled: true,
          },
        }),
      );
      await page.route("**/api/v2/model-providers", async (route) => {
        if (route.request().method() === "GET")
          return route.fulfill({
            json: {
              enabled: true,
              connections: connection ? [connection] : [],
            },
          });
        const input = route.request().postDataJSON();
        expect(input.apiKey).toBe("test-personal-key");
        ids.push(input.id);
        if (fail)
          return route.fulfill({
            status: 422,
            json: {
              error: {
                code: "PROVIDER_KEY_INVALID",
                message: "API Key 无效，请检查后重新导入。",
              },
            },
          });
        connection = {
          id: input.id,
          provider: input.provider,
          name: input.name,
          baseUrl: input.baseUrl,
          models: [`personal.${input.id}.qwen-test`],
          revision: "a".repeat(64),
        };
        return route.fulfill({ json: { connection, verifiedMs: 320 } });
      });
      await page.route("**/api/v2/models/selection", (route) => {
        selectedModel = route.request().postDataJSON().model;
        return route.fulfill({ json: { selectedModel } });
      });
      let edits = 0;
      await page.route("**/api/v2/model-providers/*", (route) => {
        if (route.request().method() === "PUT") {
          const input = route.request().postDataJSON();
          expect(input.revision).toBe(connection!.revision);
          expect(input.apiKey).toBe(edits === 0 ? "" : "rotated-test-key");
          edits += 1;
          connection = {
            ...connection!,
            name: input.name,
            baseUrl: input.baseUrl,
            models: input.models.map(
              (id: string) => `personal.${connection!.id}.${id}`,
            ),
            revision: "b".repeat(64),
          };
          return route.fulfill({ json: { connection, verifiedMs: 150 } });
        }
        expect(route.request().method()).toBe("DELETE");
        connection = undefined;
        selectedModel = "";
        return route.fulfill({ status: 204 });
      });
      await page.goto("/models");
      await expect(page.locator(".primary-model-summary")).toContainText(
        "尚未设置主模型",
      );
      await expect(
        page.getByText("deepseek-v4.1-flash-1017", { exact: true }),
      ).toHaveCount(0);
      await page
        .getByRole("button", { name: "自定义添加新模型", exact: true })
        .click();
      const dialog = page.getByRole("dialog", { name: "添加新供应商" });
      await expect(page.getByLabel("API Key", { exact: true })).toBeEnabled();
      await page
        .getByLabel("供应商名称", { exact: true })
        .fill("我的个人供应商");
      await page
        .getByLabel("API 地址", { exact: true })
        .fill("https://api.provider.test/v1");
      await page.getByLabel("模型 ID", { exact: true }).fill("qwen-test");
      await page
        .getByLabel("API Key", { exact: true })
        .fill("test-personal-key");
      await page.screenshot({
        path: testInfo.outputPath("personal-import.png"),
      });
      await dialog
        .getByRole("button", { name: "验证并添加", exact: true })
        .click();
      await expect(dialog.getByRole("alert")).toContainText("Key 无效");
      fail = false;
      await dialog
        .getByRole("button", { name: "验证并添加", exact: true })
        .click();
      await expect(dialog).toHaveCount(0);
      expect(ids).toHaveLength(2);
      expect(ids[0]).toBe(ids[1]);
      await expect(page.locator(".primary-model-summary")).toContainText(
        "尚未设置主模型",
      );
      await page
        .getByRole("button", { name: "设为主模型", exact: true })
        .click();
      await expect(page.locator(".primary-model-summary")).toContainText(
        "qwen-test",
      );
      await page.reload();
      await expect(page.locator(".primary-model-summary")).toContainText(
        "qwen-test",
      );
      expect(
        await page.evaluate(() =>
          JSON.stringify({
            local: { ...localStorage },
            session: { ...sessionStorage },
          }),
        ),
      ).not.toContain("test-personal-key");
      await page.getByRole("button", { name: /我的个人供应商/ }).click();
      await page
        .getByRole("button", { name: "编辑当前供应商", exact: true })
        .click();
      const edit = page.getByRole("dialog", { name: "编辑供应商" });
      await expect(edit).toBeVisible();
      await expect(edit.getByLabel("API Key", { exact: true })).toHaveValue("");
      await expect(edit.getByLabel("模型 ID", { exact: true })).toHaveValue(
        "qwen-test",
      );
      await edit
        .getByLabel("供应商名称", { exact: true })
        .fill("修改后的供应商");
      await page.screenshot({ path: testInfo.outputPath("personal-edit.png") });
      await edit
        .getByRole("button", { name: "验证并保存", exact: true })
        .click();
      await expect(edit).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: /修改后的供应商/ }),
      ).toBeVisible();
      await expect(page.locator(".primary-model-summary")).toContainText(
        "qwen-test",
      );
      await page
        .getByRole("button", { name: "编辑当前供应商", exact: true })
        .click();
      await edit
        .getByLabel("API 地址", { exact: true })
        .fill("https://new.provider.test/v1");
      await edit
        .getByRole("button", { name: "验证并保存", exact: true })
        .click();
      await expect(edit.getByRole("alert")).toContainText("重新填写");
      expect(edits).toBe(1);
      await edit
        .getByLabel("API Key", { exact: true })
        .fill("rotated-test-key");
      await edit
        .getByRole("button", { name: "验证并保存", exact: true })
        .click();
      await expect(edit).toHaveCount(0);
      expect(edits).toBe(2);
      await page
        .getByRole("button", { name: "编辑当前供应商", exact: true })
        .click();
      await page
        .getByRole("button", { name: "删除供应商", exact: true })
        .click();
      await expect(edit).toHaveCount(0);
      await expect(
        page.getByRole("region", { name: "确认移除供应商" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "确认移除", exact: true }).click();
      await expect(page.locator(".primary-model-summary")).toContainText(
        "尚未设置主模型",
      );
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
    });
  }
}

test("missing personal key explains the problem and links to import without discarding the goal", async ({
  page,
}) => {
  await mock(page, true);
  await page.route("**/api/v2/projects", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 422,
          json: {
            error: {
              code: "MODEL_NOT_CONFIGURED",
              message: "请先导入 API Key，并选择主模型。",
            },
          },
        })
      : route.fallback(),
  );
  await page.goto("/");
  await page.getByLabel("学习目标", { exact: true }).fill("学习数学分析");
  await page.getByRole("button", { name: "创建学习计划", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请先导入 API Key");
  await expect(page.getByRole("alert")).not.toContainText("内容已更新");
  await expect(page.getByLabel("学习目标", { exact: true })).toHaveValue(
    "学习数学分析",
  );
  await page.getByRole("link", { name: "导入 API Key", exact: true }).click();
  await expect(page).toHaveURL(/\/models$/);
});

test("lesson generation shows estimates, survives reload and only completes after saving", async ({
  page,
}) => {
  await mock(page);
  let state = "running";
  let phase = "generating";
  const start = new Date().toISOString();
  await page.route("**/lesson-jobs", (route) =>
    route.fulfill({
      status: 202,
      json: { jobId: "test-lesson-progress", state },
    }),
  );
  await page.route("**/jobs/test-lesson-progress/events?*", (route) =>
    route.abort(),
  );
  await page.route("**/jobs/test-lesson-progress", (route) =>
    route.fulfill({
      json: {
        jobId: "test-lesson-progress",
        kind: "lesson",
        subject: "node:13",
        state,
        progress: {
          phase,
          attemptStartedAt: start,
          estimatedModelMs: 60000,
          estimateSource: "history",
          queueMs: 50,
          modelMs: 1200,
          totalMs: 1300,
        },
        error: null,
        updatedAt: start,
      },
    }),
  );
  await page.goto("/study?project=1&chapter=13");
  await page.getByRole("button", { name: "生成本节教材", exact: true }).click();
  const bar = page.getByRole("progressbar", { name: "学习内容生成进度" });
  await expect(bar).toBeVisible();
  await expect(page.locator(".generation-progress")).toContainText(
    "正在编写本节教材",
  );
  expect(Number(await bar.getAttribute("aria-valuenow"))).toBeLessThan(100);
  await page.reload();
  await expect(bar).toBeVisible();
  phase = "saving";
  await expect(bar).toHaveAttribute("aria-valuenow", "96");
  state = "done";
  await expect(bar).toHaveAttribute("aria-valuenow", "100");
});

test("local supplier bridge follows the development or production boundary", async ({
  page,
}) => {
  await mock(page);
  const cid = "123456abcdef";
  const alias = `local.${cid}.qwen-test`;
  const connection = {
    id: cid,
    provider: "custom",
    name: "我的测试模型",
    baseUrl: "https://provider.example/v1",
    models: [alias],
  };
  let added = false;
  let localReads = 0;
  let requests = 0;
  let fail = true;
  let selectedModel = "deepseek-test";
  await page.route("**/api/v2/local-providers", async (route) => {
    if (route.request().method() === "GET") {
      localReads++;
      await route.fulfill({
        json: { enabled: true, connections: added ? [connection] : [] },
      });
      return;
    }
    requests++;
    expect(route.request().postDataJSON().apiKey).toBe("test-only-key");
    if (fail)
      await route.fulfill({
        status: 422,
        json: {
          error: {
            code: "INVALID_ARGUMENT",
            message: "Key 无效或没有模型权限",
          },
        },
      });
    else {
      added = true;
      await route.fulfill({ json: { connection, verifiedMs: 750 } });
    }
  });
  await page.route("**/api/v2/models", (route) =>
    route.fulfill({
      json: {
        items: [
          { id: "deepseek-test", provider: "deepseek" },
          ...(added ? [{ id: alias, provider: cid }] : []),
        ],
        selectedModel,
        selectedAvailable: true,
      },
    }),
  );
  await page.route("**/models/selection", (route) => {
    selectedModel = route.request().postDataJSON().model;
    expect(selectedModel).toBe(alias);
    return route.fulfill({ json: { selectedModel } });
  });
  await page.goto("/models");
  if (process.env.LEARN_WEB_TEST_PREVIEW === "1") {
    // The legacy in-memory bridge is intentionally compiled out of releases.
    // A mocked endpoint must not make a production gateway page accept a Key.
    await page
      .getByRole("button", { name: "自定义添加新模型", exact: true })
      .click();
    await expect(page.getByLabel("API Key", { exact: true })).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "由官网网关管理", exact: true }),
    ).toBeDisabled();
    expect(localReads).toBe(0);
    expect(requests).toBe(0);
    return;
  }
  await expect(
    page.getByText("本机测试供应商 · 生成内容会消耗对应供应商额度。", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "自定义添加新模型", exact: true })
    .click();
  await page.getByLabel("供应商名称", { exact: true }).fill(connection.name);
  await page.getByLabel("API 地址", { exact: true }).fill(connection.baseUrl);
  await page.getByLabel("模型 ID", { exact: true }).fill("qwen-test");
  await page.getByLabel("API Key", { exact: true }).fill("test-only-key");
  await page.getByRole("button", { name: "验证并添加", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Key 无效");
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(requests).toBe(1);
  fail = false;
  await page.getByRole("button", { name: "验证并添加", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".model-status")).toContainText("0.75 秒");
  await expect(page.locator(".primary-model-summary")).toContainText(
    "deepseek-test",
  );
  await expect(
    page.getByRole("combobox", { name: "主模型", exact: true }),
  ).toContainText("qwen-test");
  await page.getByRole("button", { name: "设为主模型", exact: true }).click();
  await expect(page.locator(".primary-model-summary")).toContainText(
    "qwen-test",
  );
  await page.reload();
  await expect(page.locator(".primary-model-summary")).toContainText(
    "qwen-test",
  );
  expect(
    await page.evaluate(() =>
      JSON.stringify({
        local: { ...localStorage },
        session: { ...sessionStorage },
      }),
    ),
  ).not.toContain("test-only-key");
  expect(requests).toBe(2);
});

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`persistent assistant keeps drafts across pages at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/study?project=1&chapter=12");
      await expect(
        page.getByRole("navigation", { name: "主导航" }).getByRole("link"),
      ).toHaveText([
        "学习首页",
        "学习路线",
        "学习工作台",
        "间隔复习",
        "查漏测验",
        "学习看板",
        "知识问答",
        "资料库",
        "学习工具",
        "模型设置",
      ]);
      await page
        .getByRole("button", { name: "打开以太小助", exact: true })
        .click();
      const assistant = page.getByRole("dialog", {
        name: "以太小助",
        exact: true,
      });
      await expect(assistant).toBeVisible();
      const input = assistant.getByRole("textbox", { name: "向以太小助提问" });
      await input.fill("跨页保存的小助草稿");
      if (width < 850)
        await assistant.getByRole("button", { name: "关闭以太小助" }).click();
      if (width < 850)
        await page
          .getByRole("button", { name: "打开导航", exact: true })
          .click();
      await page
        .getByRole("navigation", { name: "主导航" })
        .getByRole("link", { name: "资料库", exact: true })
        .click();
      if (width < 850)
        await page
          .getByRole("button", { name: "打开以太小助", exact: true })
          .click();
      await expect(input).toHaveValue("跨页保存的小助草稿");
      await expect(assistant.locator(".assistant-context")).toContainText(
        "资料库",
      );
      await input.press("Enter");
      await expect(
        assistant.getByText("这是以太小助的本地演示回答。", { exact: false }),
      ).toBeVisible();
      await expect(input).toHaveValue("");
      await page.screenshot({ path: testInfo.outputPath("assistant.png") });
      await assistant
        .getByRole("button", { name: "清空对话", exact: true })
        .click();
      await page
        .getByRole("dialog", { name: "清空小助对话？", exact: true })
        .getByRole("button", { name: "确认清空", exact: true })
        .click();
      await expect(
        assistant.getByText("这是以太小助的本地演示回答。", { exact: false }),
      ).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(assistant).toBeHidden();
      await expect(
        page.getByRole("button", { name: "打开以太小助", exact: true }),
      ).toBeFocused();
    });
  }
}

test("study minutes are recorded only after a full minute on a visible lesson", async ({
  page,
}) => {
  await mock(page);
  let minutes = 0;
  await page.route("**/api/v2/projects/1/progress", async (route) => {
    const body = route.request().postDataJSON();
    expect(body.metric).toBe("minutes");
    expect(body.value).toBe(1);
    expect(body.nodeId).toBe(12);
    minutes++;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: "{}",
    });
  });
  await page.clock.install();
  await page.goto("/study?project=1&chapter=12");
  await expect(
    page.getByRole("heading", { name: "变量，让信息有个名字", exact: true }),
  ).toBeVisible();
  await page.clock.fastForward(59_000);
  expect(minutes).toBe(0);
  await page.clock.fastForward(1_100);
  await expect.poll(() => minutes).toBe(1);
  await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
  await page.clock.fastForward(120_000);
  expect(minutes).toBe(1);
});

test("new users see model setup before creating a paid plan", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/v2/models", (route) =>
    route.fulfill({
      json: { items: [], selectedModel: "", selectedAvailable: false },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("alert").filter({ hasText: "请先到「模型设置」选择主模型" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "前往模型设置", exact: true }).click();
  await expect(page).toHaveURL(/\/models/);
});

test("model markdown blocks external image requests while retaining data images", async ({
  page,
}) => {
  const demo = await mock(page);
  let leaked = false;
  page.on("request", (request) => {
    if (request.url().includes("image-exfil.example")) leaked = true;
  });
  await page.route("**/api/v2/projects/1/nodes", async (route) => {
    const response = await demo.handle(route.request().url());
    const payload = await response.json();
    payload.items.find((n: { id: number }) => n.id === 12).description =
      "## 图片\n\n![外部图片](https://image-exfil.example/?private=content)\n\n![本地数据图片](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jEeUAAAAASUVORK5CYII=)";
    await route.fulfill({ json: payload });
  });
  await page.goto("/study?project=1&chapter=12");
  await expect(
    page.getByText("[外部图片已屏蔽]", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "本地数据图片", exact: true }),
  ).toBeVisible();
  expect(leaked).toBe(false);
});
