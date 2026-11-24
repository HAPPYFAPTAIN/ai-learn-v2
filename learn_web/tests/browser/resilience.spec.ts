import { test, expect, type Page } from "@playwright/test";
import { createDemo } from "../../src/demo/data";
import { navigate } from "./navigation";

async function mock(page: Page) {
  const demo = createDemo();
  await page.route("**/api/v2/**", async (route) => {
    const response = await demo.handle(route.request().url(), {
      method: route.request().method(),
      body: route.request().postData() || undefined,
    });
    await route.fulfill({
      status: response.status,
      contentType: "application/json",
      body: await response.text(),
    });
  });
  return demo;
}
async function notes(page: Page) {
  await page.goto("/study?project=1&chapter=11");
  await page.getByRole("tab", { name: "笔记", exact: true }).click();
  await expect(
    page.getByText("显示 0 / 0 条笔记与批注", { exact: true }),
  ).toBeVisible();
}
const warning = (page: Page) =>
  page.getByRole("dialog", { name: "有内容尚未保存", exact: true });
const discard = (page: Page) =>
  warning(page)
    .getByRole("button", { name: "放弃未保存内容", exact: true })
    .click();

for (const saved of [false, true]) {
  test(`project creation recovers a lost response without a new paid intent (saved=${saved})`, async ({
    page,
  }) => {
    const demo = await mock(page);
    const ids: string[] = [];
    let result: Record<string, unknown> | null = null;
    await page.route("**/api/v2/projects", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      const body = route.request().postDataJSON();
      ids.push(body.requestId);
      if (ids.length === 1) {
        if (saved) {
          const response = await demo.handle(route.request().url(), {
            method: "POST",
            body: route.request().postData()!,
          });
          result = await response.json();
        }
        return route.abort("failed");
      }
      const response = await demo.handle(route.request().url(), {
        method: "POST",
        body: route.request().postData()!,
      });
      result = await response.json();
      return route.fulfill({ json: result });
    });
    await page.route("**/api/v2/projects/creation-requests/*", (route) => {
      expect(route.request().url()).toContain(ids[0]);
      return route.fulfill({ json: result });
    });
    await page.goto("/");
    await page.getByLabel("学习目标", { exact: true }).fill("可恢复的计划");
    const submit = page.getByRole("button", {
      name: "创建学习计划",
      exact: true,
    });
    await submit.click();
    await expect(submit).toBeDisabled();
    await expect(page.getByLabel("学习目标", { exact: true })).toBeDisabled();
    await page
      .getByRole("button", { name: "核对已保存记录", exact: true })
      .click();
    if (!saved) {
      await page
        .getByRole("button", { name: "已核对，允许再次提交", exact: true })
        .click();
      expect(ids).toHaveLength(1);
      await submit.click();
      expect(ids[1]).toBe(ids[0]);
    }
    await expect(page).toHaveURL(/\/study\?project=\d+/);
    expect(ids[0]).toMatch(/^[\da-f-]{36}$/);
    expect(ids).toHaveLength(saved ? 1 : 2);
    const projects = await (await demo.handle("/api/v2/projects")).json();
    expect(
      projects.items.filter(
        (p: { title: string }) => p.title === "可恢复的计划",
      ),
    ).toHaveLength(1);
  });
}

for (const width of [390, 1440]) {
  test(`drafts survive cancelled tab, route and browser-back navigation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    await notes(page);
    await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
    await page
      .getByRole("main")
      .getByRole("link", { name: /认识 Python 与第一个程序/ })
      .click();
    await page.getByRole("tab", { name: "笔记", exact: true }).click();
    await page.getByLabel("记下你的理解").fill("不能被误丢弃的笔记");
    await page.getByRole("tab", { name: "内容", exact: true }).click();
    await expect(warning(page)).toContainText("新笔记");
    await warning(page).getByRole("button", { name: "继续编辑" }).click();
    await expect(page.getByLabel("记下你的理解")).toHaveValue(
      "不能被误丢弃的笔记",
    );
    await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
    await expect(warning(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/chapter=11/);
    const before = page.url();
    await page.goBack();
    await expect(warning(page)).toBeVisible();
    await warning(page).getByRole("button", { name: "继续编辑" }).click();
    await expect(page).toHaveURL(before);
    const stored = await page.evaluate(() =>
      [
        JSON.stringify({ ...localStorage }),
        JSON.stringify({ ...sessionStorage }),
      ].join(""),
    );
    expect(stored).not.toContain("不能被误丢弃的笔记");
    await page.getByRole("tab", { name: "内容", exact: true }).click();
    await discard(page);
    await page.getByRole("tab", { name: "笔记", exact: true }).click();
    await expect(page.getByLabel("记下你的理解")).toHaveValue("");
  });
}

test("refresh warns only while a draft is unsaved, and saving removes the guard", async ({
  page,
}) => {
  await mock(page);
  await notes(page);
  await page.getByLabel("记下你的理解").fill("刷新保护");
  const prompt = page.waitForEvent("dialog");
  await page.evaluate(() => {
    setTimeout(() => location.reload(), 0);
  });
  const dialog = await prompt;
  expect(dialog.type()).toBe("beforeunload");
  await dialog.dismiss();
  await expect(page.getByLabel("记下你的理解")).toHaveValue("刷新保护");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  await expect(page.getByLabel("记下你的理解")).toHaveValue("");
  const dirty = await page.evaluate(
    () =>
      !window.dispatchEvent(new Event("beforeunload", { cancelable: true })),
  );
  expect(dirty).toBe(false);
  await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
  await expect(page).not.toHaveURL(/chapter=/);
  await expect(warning(page)).toHaveCount(0);
});

test("nested discard confirmation preserves edit focus, escape behavior and scrolling", async ({
  page,
}) => {
  const demo = await mock(page);
  await demo.handle("/api/v2/projects/1/notes", {
    method: "POST",
    body: JSON.stringify({ nodeId: 11, content: "原笔记" }),
  });
  await page.goto("/study?project=1&chapter=11");
  await page.getByRole("tab", { name: "笔记", exact: true }).click();
  await page.getByRole("button", { name: "编辑笔记", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "编辑笔记", exact: true });
  await editor.getByLabel("笔记内容").fill("未保存的修改");
  await editor.getByRole("button", { name: "取消", exact: true }).click();
  await expect(warning(page)).toBeVisible();
  await page.keyboard.press("Tab");
  expect(
    await warning(page).evaluate((el) => el.contains(document.activeElement)),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(warning(page)).toHaveCount(0);
  await expect(editor.getByLabel("笔记内容")).toHaveValue("未保存的修改");
  expect(await page.evaluate(() => document.body.style.overflow)).toBe(
    "hidden",
  );
  await editor.getByRole("button", { name: "关闭对话框" }).click();
  await discard(page);
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("");
  await expect(page.locator(".note-card")).toContainText("原笔记");
  await expect(
    page.getByRole("button", { name: "编辑笔记", exact: true }),
  ).toBeFocused();
});

test("discarding a manual card clears it while cancelling the warning keeps it", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/review");
  await page
    .getByRole("button", { name: "手动添加复习卡", exact: true })
    .click();
  const editor = page.getByRole("dialog", {
    name: "手动添加复习卡",
    exact: true,
  });
  await editor.getByLabel("卡片问题").fill("未保存的卡片");
  const chapter = editor.getByRole("combobox", { name: "关联章节" });
  await chapter.click();
  await expect(chapter).toBeFocused();
  await expect(chapter).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(chapter).toHaveAttribute("aria-expanded", "false");
  await expect(warning(page)).toHaveCount(0);
  await expect(editor).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(warning(page)).toBeVisible();
  await warning(page).getByRole("button", { name: "继续编辑" }).click();
  await expect(editor.getByLabel("卡片问题")).toHaveValue("未保存的卡片");
  await editor.getByRole("button", { name: "取消", exact: true }).click();
  await discard(page);
  await page
    .getByRole("button", { name: "手动添加复习卡", exact: true })
    .click();
  await expect(editor.getByLabel("卡片问题")).toHaveValue("");
  await editor.getByRole("button", { name: "取消", exact: true }).click();
  await expect(warning(page)).toHaveCount(0);
});

test("account changes remove old drafts and discard dialogs immediately", async ({
  page,
}) => {
  await mock(page);
  await notes(page);
  await page.getByLabel("记下你的理解").fill("旧账号的私人草稿");
  await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
  await expect(warning(page)).toBeVisible();
  await page.evaluate(() =>
    window.dispatchEvent(
      new StorageEvent("storage", { key: "aethericai-community-access-token" }),
    ),
  );
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  await expect(warning(page)).toHaveCount(0);
  await expect(page.getByText("旧账号的私人草稿", { exact: true })).toHaveCount(
    0,
  );
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("");
});

test("a note accepted before its response is lost is recovered with a read, preserving newer input", async ({
  page,
}) => {
  const demo = await mock(page);
  await notes(page);
  let writes = 0;
  await page.route("**/api/v2/projects/1/notes", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    writes++;
    await demo.handle(route.request().url(), {
      method: "POST",
      body: route.request().postData()!,
    });
    await route.abort("failed");
  });
  await page.getByLabel("记下你的理解").fill("服务端已经保存");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  const recovery = page.getByRole("region", {
    name: "核对保存结果",
    exact: true,
  });
  await expect(recovery).toBeVisible();
  await expect(
    page.getByRole("button", { name: "保存笔记", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("记下你的理解").fill("下一条尚未保存的新输入");
  await recovery.getByRole("button", { name: "核对已保存记录" }).click();
  await expect(
    page.getByText("已核对，本次笔记已保存，无需再次提交。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("记下你的理解")).toHaveValue(
    "下一条尚未保存的新输入",
  );
  await expect(page.locator(".notes-manager .note-card")).toHaveCount(1);
  expect(writes).toBe(1);
});

test("a failed result check does not unlock a duplicate note submission", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mock(page);
  await notes(page);
  let writes = 0,
    failRead = true;
  await page.route("**/api/v2/projects/1/notes", (route) => {
    if (route.request().method() === "POST") {
      writes++;
      return route.abort("failed");
    }
    if (failRead)
      return route.fulfill({ status: 502, body: "proxy unavailable" });
    return route.fallback();
  });
  await page.getByLabel("记下你的理解").fill("没有送达的笔记");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  const recovery = page.getByRole("region", {
    name: "核对保存结果",
    exact: true,
  });
  await recovery.getByRole("button", { name: "核对已保存记录" }).click();
  await expect(recovery.getByRole("alert")).toBeVisible();
  await expect(
    recovery.getByRole("button", { name: "已核对，允许再次提交" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "保存笔记", exact: true }),
  ).toBeDisabled();
  failRead = false;
  await recovery.getByRole("button", { name: "核对已保存记录" }).click();
  await expect(
    recovery.getByRole("button", { name: "已核对，允许再次提交" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: testInfo.outputPath("write-recovery.png"),
    fullPage: true,
  });
  await recovery.getByRole("button", { name: "已核对，允许再次提交" }).click();
  await expect(
    page.getByRole("button", { name: "保存笔记", exact: true }),
  ).toBeEnabled();
  expect(writes).toBe(1);
});

test("existing identical cards do not falsely confirm a lost creation; a new saved card does", async ({
  page,
}) => {
  const demo = await mock(page);
  const body = {
    projectId: 1,
    nodeId: null,
    front: "相同问题",
    back: "相同答案",
    cardType: "basic",
  };
  await demo.handle("/api/v2/cards", {
    method: "POST",
    body: JSON.stringify(body),
  });
  let writes = 0;
  const requestIds: string[] = [];
  await page.route("**/api/v2/cards", async (route) => {
    writes++;
    requestIds.push(route.request().postDataJSON().requestId);
    if (writes === 2)
      await demo.handle(route.request().url(), {
        method: "POST",
        body: route.request().postData()!,
      });
    return route.abort("failed");
  });
  await page.goto("/review");
  await page
    .getByRole("button", { name: "手动添加复习卡", exact: true })
    .click();
  const editor = page.getByRole("dialog", {
    name: "手动添加复习卡",
    exact: true,
  });
  await editor.getByLabel("卡片问题").fill(body.front);
  await editor.getByLabel("卡片答案").fill(body.back);
  await editor.getByRole("button", { name: "保存复习卡", exact: true }).click();
  await editor.getByRole("button", { name: "核对已保存记录" }).click();
  await expect(editor).toBeVisible();
  await editor.getByRole("button", { name: "已核对，允许再次提交" }).click();
  expect(writes).toBe(1);
  await editor.getByRole("button", { name: "保存复习卡", exact: true }).click();
  await editor.getByRole("button", { name: "核对已保存记录" }).click();
  await expect(editor).toHaveCount(0);
  await expect(
    page.getByText("已核对，复习卡已保存，无需再次提交。", { exact: true }),
  ).toBeVisible();
  expect(writes).toBe(2);
  expect(requestIds[0]).toMatch(/^[\da-f-]{36}$/);
  expect(requestIds[1]).toBe(requestIds[0]);
  const fresh = await (await demo.handle("/api/v2/projects/1/cards")).json();
  expect(
    fresh.items.filter((card: { front: string }) => card.front === body.front),
  ).toHaveLength(2);
});

test("chat guards unsent questions and explicit retries reuse the original request id", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/chat?project=1");
  const ids: string[] = [];
  await page.route("**/api/v2/projects/1/chat-jobs", (route) => {
    ids.push(route.request().postDataJSON().requestId);
    if (ids.length === 1) return route.abort("failed");
    return route.fallback();
  });
  await page.getByLabel("向助教提问").fill("请解释变量");
  await navigate(page, "学习路线");
  await expect(warning(page)).toContainText("问答输入");
  await warning(page).getByRole("button", { name: "继续编辑" }).click();
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await page.getByRole("button", { name: "核对已保存记录" }).click();
  await page.getByRole("button", { name: "已核对，允许再次提交" }).click();
  expect(ids).toHaveLength(1);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByLabel("向助教提问")).toHaveValue("");
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
});

test("offline and restored notices preserve input without submitting it", async ({
  page,
}) => {
  await mock(page);
  await notes(page);
  let writes = 0;
  page.on("request", (req) => {
    if (req.method() === "POST") writes++;
  });
  await page.getByLabel("记下你的理解").fill("断网时的草稿");
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(
    page.getByText(/网络已断开，当前页面的输入仍保留/),
  ).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText(/网络连接已恢复。请核对保存结果/)).toBeVisible();
  await expect(page.getByLabel("记下你的理解")).toHaveValue("断网时的草稿");
  expect(writes).toBe(0);
});

test("finishing an in-flight note save safely releases a pending navigation", async ({
  page,
}) => {
  await mock(page);
  await notes(page);
  let release!: () => void;
  await page.route("**/api/v2/projects/1/notes", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fallback();
  });
  await page.getByLabel("记下你的理解").fill("正在保存的笔记");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存中…", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "返回章节目录", exact: true }).click();
  await expect(warning(page)).toContainText("保存请求仍在进行");
  release();
  await expect(page).not.toHaveURL(/chapter=/);
  await expect(warning(page)).toHaveCount(0);
});
