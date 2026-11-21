import { test, expect, type Page } from "@playwright/test";
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
}
async function selectParagraph(page: Page) {
  const paragraph = page.locator(".lesson-reading .prose > p").first();
  await paragraph.scrollIntoViewIfNeeded();
  return paragraph.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
    return selection.toString().trim();
  });
}

test("dashboard keeps one trend when reports arrive before summary", async ({
  page,
}) => {
  await mock(page);
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v2/projects/2/summary", async (route) => {
    await waiting;
    await route.fallback();
  });
  await page.goto("/dashboard");
  await expect(
    page.getByRole("region", { name: "学习趋势", exact: true }),
  ).toHaveCount(1);
  await page.getByRole("combobox", { name: "当前学习计划" }).click();
  await page.getByRole("option", { name: "读懂设计的基本语言" }).click();
  await expect(
    page.getByRole("heading", { name: "读懂设计的基本语言 · 阶段学习报告" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "学习趋势", exact: true }),
  ).toHaveCount(1);
  release();
  await expect(
    page.getByRole("heading", { name: "章节完成进度", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "学习趋势", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByText("此时间范围暂无学习记录，整理今日报告后即可查看趋势。", {
      exact: true,
    }),
  ).toHaveCount(1);
});

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`learning charts switch metrics and date ranges at ${width}px / ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/dashboard");
      const chart = page.getByRole("region", { name: "学习趋势", exact: true });
      await expect(
        chart.getByRole("group", { name: "近 7 天学习时长图表" }),
      ).toBeVisible();
      await expect(chart.locator(".chart-bar")).toHaveCount(7);
      await expect(
        page.getByRole("img", { name: /章节状态分布/ }),
      ).toBeVisible();
      await chart
        .getByRole("button", { name: "复习卡片", exact: true })
        .click();
      const last = chart.locator('svg g[role="button"]').last();
      await last.focus();
      await last.press("Enter");
      await expect(chart.locator(".chart-detail")).toContainText(
        "复习卡片 2 张",
      );
      await page.screenshot({
        path: testInfo.outputPath("charts.png"),
        fullPage: true,
      });
      await chart
        .getByRole("button", { name: "近 30 天", exact: true })
        .click();
      await expect(chart.locator('svg g[role="button"]')).toHaveCount(30);
      await expect(chart.locator(".chart-missing")).toHaveCount(16);
      await chart.locator('svg g[role="button"]').first().click();
      await expect(chart.locator(".chart-detail")).toContainText(
        "暂无日报记录",
      );
      await chart.getByText("查看每日数据", { exact: true }).click();
      await expect(chart.getByRole("table")).toBeVisible();
      await expect(
        chart.getByRole("table").getByText("无记录").first(),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.getByRole("combobox", { name: "当前学习计划" }).click();
      await page.getByRole("option", { name: "读懂设计的基本语言" }).click();
      await expect(
        chart.getByText("此时间范围暂无学习记录，整理今日报告后即可查看趋势。"),
      ).toBeVisible();
      await expect(chart.locator("svg")).toHaveCount(0);
    });

    test(`lesson annotations save, edit, locate and delete at ${width}px / ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await mock(page);
      await page.goto("/study?project=1&chapter=11");
      await expect(page.locator(".lesson-reading .prose")).toBeVisible();
      const quoted = await selectParagraph(page);
      const add = page.getByRole("button", { name: "为所选文字添加批注" });
      await expect(add).toBeVisible();
      const actionBox = (await add.boundingBox())!;
      expect(actionBox.x).toBeGreaterThanOrEqual(0);
      expect(actionBox.x + actionBox.width).toBeLessThanOrEqual(width);
      await add.click();
      const dialog = page.getByRole("dialog", {
        name: "添加批注",
        exact: true,
      });
      await expect(dialog.locator("blockquote")).toHaveText(quoted);
      await expect(
        dialog.getByRole("button", { name: "保存批注" }),
      ).toBeDisabled();
      await dialog.getByLabel("我的批注").fill("把大问题拆小，再按顺序执行。");
      await page.screenshot({
        path: testInfo.outputPath("annotation-dialog.png"),
      });
      await dialog.getByRole("button", { name: "保存批注" }).click();
      const card = page.locator(".annotation-card").first();
      await expect(card).toContainText("把大问题拆小，再按顺序执行。");
      await card.getByRole("button", { name: "编辑批注" }).click();
      await page.getByLabel("我的批注").fill("更新：先拆分，再验证每一步。");
      await page.getByRole("button", { name: "保存批注", exact: true }).click();
      await expect(card).toContainText("更新：先拆分，再验证每一步。");
      await card.getByRole("button", { name: "定位原文" }).click();
      await expect
        .poll(() => page.evaluate(() => window.getSelection()?.toString()))
        .toBe(quoted);
      await page.getByRole("tab", { name: "笔记", exact: true }).click();
      await expect(page.locator(".note-card blockquote")).toHaveText(quoted);
      await expect(page.locator(".note-card")).toContainText(
        "更新：先拆分，再验证每一步。",
      );
      await page.reload();
      await page.getByRole("button", { name: "查看本章批注" }).click();
      await expect(card).toContainText("更新：先拆分，再验证每一步。");
      await page.screenshot({
        path: testInfo.outputPath("annotations.png"),
        fullPage: true,
      });
      await card.getByRole("button", { name: "删除批注", exact: true }).click();
      await page
        .getByRole("dialog", { name: "删除批注", exact: true })
        .getByRole("button", { name: "取消", exact: true })
        .click();
      await expect(card).toBeVisible();
      await card.getByRole("button", { name: "删除批注", exact: true }).click();
      await page.getByRole("button", { name: "确认删除", exact: true }).click();
      await expect(page.locator(".annotation-card")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    });
  }

test("annotation failures preserve the draft and chapter changes clear it", async ({
  page,
}) => {
  await mock(page);
  let fail = true;
  await page.route("**/api/v2/projects/1/notes", (route) =>
    route.request().method() === "POST" && fail
      ? route.fulfill({
          status: 503,
          json: {
            error: { code: "BUSY", message: "稍后重试", retryable: true },
          },
        })
      : route.fallback(),
  );
  await page.goto("/study?project=1&chapter=11");
  await expect(page.locator(".lesson-reading .prose")).toBeVisible();
  await selectParagraph(page);
  await page.getByRole("button", { name: "为所选文字添加批注" }).click();
  await page.getByLabel("我的批注").fill("失败时也要保留的草稿");
  await page.getByRole("button", { name: "保存批注" }).click();
  await expect(page.getByRole("alert")).toContainText("稍后重试");
  await expect(page.getByLabel("我的批注")).toHaveValue("失败时也要保留的草稿");
  fail = false;
  await page
    .getByRole("button", { name: "核对已保存记录", exact: true })
    .click();
  await page
    .getByRole("button", { name: "已核对，允许再次提交", exact: true })
    .click();
  await page.getByRole("button", { name: "保存批注" }).click();
  await expect(page.locator(".annotation-card")).toHaveCount(1);
  await page.getByRole("link", { name: /返回章节目录/ }).click();
  await page.getByRole("link", { name: /变量，让信息有个名字/ }).click();
  await page.getByRole("button", { name: "查看本章批注" }).click();
  await expect(page.locator(".annotation-card")).toHaveCount(0);
});

test("annotation location refuses missing and ambiguous quotations", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/v2/projects/1/notes", (route) =>
    route.fulfill({
      json: {
        items: ["已不在教材里的文字", "一个"].map((selection, index) => ({
          id: index + 1,
          projectId: 1,
          nodeId: 11,
          selection,
          content: "保留批注",
          updatedAt: new Date().toISOString(),
        })),
      },
    }),
  );
  await page.goto("/study?project=1&chapter=11");
  await page.getByRole("button", { name: "查看本章批注" }).click();
  await page
    .locator(".annotation-card")
    .first()
    .getByRole("button", { name: "定位原文" })
    .click();
  await expect(page.locator(".annotation-notice")).toContainText(
    "当前课文中未找到",
  );
  await page
    .locator(".annotation-card")
    .last()
    .getByRole("button", { name: "定位原文" })
    .click();
  await expect(page.locator(".annotation-notice")).toContainText(
    "存在多处相同原文",
  );
});

async function exposeUpload(page: Page) {
  await page.addInitScript(() => {
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (body) {
      if (body instanceof FormData)
        (window as unknown as { testUpload: XMLHttpRequest }).testUpload = this;
      return send.call(this, body);
    };
  });
}
async function bytes(page: Page, loaded: number, total: number) {
  await page.evaluate(
    ({ loaded, total }) => {
      (
        window as unknown as { testUpload: XMLHttpRequest }
      ).testUpload.upload.dispatchEvent(
        new ProgressEvent("progress", {
          loaded,
          total,
          lengthComputable: true,
        }),
      );
    },
    { loaded, total },
  );
}
for (const width of [390, 1440]) {
  test(`upload progress waits for acceptance and preserves the selected owner at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await exposeUpload(page);
    await mock(page);
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    let count = 0;
    await page.route("**/api/v2/projects/1/materials", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      count++;
      expect(route.request().headers()["x-learn-expected-user"]).toBe(
        "demo-learner",
      );
      expect(route.request().headers()["content-type"]).toContain(
        "multipart/form-data; boundary=",
      );
      await pending;
      return route.fulfill({
        status: 202,
        json: {
          fileId: "uploaded",
          sha256: "fixture",
          sizeBytes: 10,
          jobId: null,
        },
      });
    });
    await page.goto("/library");
    await page.getByLabel("选择上传资料").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("test"),
    });
    await expect.poll(() => count).toBe(1);
    await bytes(page, 5, 10);
    const transfer = page.getByRole("region", { name: "文件上传进度" });
    await expect(transfer.getByRole("progressbar")).toHaveAttribute(
      "value",
      "50",
    );
    await page.screenshot({ path: testInfo.outputPath("upload-progress.png") });
    await bytes(page, 10, 10);
    await expect(transfer).toContainText("文件已传输，等待服务确认");
    await expect(transfer).not.toContainText("上传已确认");
    release();
    await expect(transfer).toContainText("上传已确认");
    expect(count).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
test("upload cancellation stops the request and a server failure is retried only by the user", async ({
  page,
}) => {
  await exposeUpload(page);
  await mock(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let count = 0;
  await page.route("**/api/v2/projects/1/materials", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    count++;
    if (count === 1) {
      await pending;
      return route.abort().catch(() => {});
    }
    if (count === 2)
      return route.fulfill({
        status: 507,
        json: {
          error: {
            code: "STORAGE_FULL",
            message: "空间不足",
            retryable: false,
          },
        },
      });
    return route.fulfill({
      status: 202,
      json: {
        fileId: "uploaded",
        sha256: "fixture",
        sizeBytes: 10,
        jobId: null,
      },
    });
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("test"),
  });
  await expect.poll(() => count).toBe(1);
  await page.getByRole("button", { name: "停止上传" }).click();
  await expect(
    page.getByRole("region", { name: "文件上传进度" }),
  ).toContainText("上传已停止");
  release();
  await page.getByRole("button", { name: "重新上传" }).click();
  await expect(
    page.getByRole("region", { name: "文件上传进度" }),
  ).toContainText("空间不足");
  expect(count).toBe(2);
  await page.getByRole("button", { name: "重新上传" }).click();
  await expect(
    page.getByRole("region", { name: "文件上传进度" }),
  ).toContainText("上传已确认");
  expect(count).toBe(3);
});

const uploadFiles = (count = 3) =>
  Array.from({ length: count }, (_, i) => ({
    name: `资料${i + 1}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`学习资料 ${i + 1}`),
  }));
const uploadReply = (jobId: string | null = null) => ({
  status: 202,
  json: { fileId: "uploaded", sha256: "fixture", sizeBytes: 10, jobId },
});
for (const width of [390, 1440]) {
  test(`batch upload confirms before sending and waits for indexing at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await mock(page);
    let count = 0;
    let release!: () => void;
    const indexing = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v2/projects/1/materials", (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      count++;
      return route.fulfill(uploadReply(count === 1 ? "batch-index" : null));
    });
    await page.route("**/api/v2/jobs/batch-index", async (route) => {
      await indexing;
      await route.fulfill({
        json: {
          jobId: "batch-index",
          state: "done",
          progress: { done: 1, total: 1 },
        },
      });
    });
    await page.goto("/library");
    await page.getByLabel("选择上传资料").setInputFiles(uploadFiles());
    const dialog = page.getByRole("dialog", { name: "批量上传资料" });
    await expect(dialog).toContainText("资料3.txt");
    expect(count).toBe(0);
    await dialog.getByRole("button", { name: "开始上传 3 份资料" }).click();
    await expect(dialog).toContainText("已接收，正在索引");
    expect(count).toBe(1);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("batch-upload.png") });
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    release();
    await expect(dialog).toContainText("已完成 3 份");
    expect(count).toBe(3);
    await dialog.getByRole("button", { name: "完成", exact: true }).click();
    await expect(dialog).toHaveCount(0);
  });
}

test("batch upload stops after the current file and resumes without uploading accepted files again", async ({
  page,
}) => {
  await mock(page);
  let count = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v2/projects/1/materials", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    count++;
    if (count === 1) await pending;
    await route.fulfill(uploadReply());
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles(uploadFiles());
  const dialog = page.getByRole("dialog", { name: "批量上传资料" });
  await dialog.getByRole("button", { name: "开始上传 3 份资料" }).click();
  await expect.poll(() => count).toBe(1);
  await dialog.getByRole("button", { name: "停止后续上传" }).click();
  await expect(dialog).toContainText("正在等待当前文件处理结束");
  release();
  await expect(dialog).toContainText("已完成 1 份");
  const retry = dialog.getByRole("button", { name: "核对后重试未接收的 2 份" });
  await expect(retry).toBeEnabled();
  expect(count).toBe(1);
  await retry.click();
  await expect(dialog).toContainText("已完成 3 份");
  expect(count).toBe(3);
});

test("batch upload pauses on quota failure and retries only unaccepted files", async ({
  page,
}) => {
  await mock(page);
  const names: string[] = [];
  await page.route("**/api/v2/projects/1/materials", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    names.push(
      route
        .request()
        .postData()!
        .match(/filename="([^"]+)"/)![1],
    );
    if (names.length === 2)
      return route.fulfill({
        status: 507,
        json: {
          error: {
            code: "STORAGE_FULL",
            message: "空间不足",
            retryable: false,
          },
        },
      });
    return route.fulfill(uploadReply());
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles(uploadFiles());
  const dialog = page.getByRole("dialog", { name: "批量上传资料" });
  await dialog.getByRole("button", { name: "开始上传 3 份资料" }).click();
  await expect(dialog).toContainText("空间不足");
  const retry = dialog.getByRole("button", { name: "核对后重试未接收的 2 份" });
  await expect(retry).toBeEnabled();
  expect(names).toEqual(["资料1.txt", "资料2.txt"]);
  await retry.click();
  await expect(dialog).toContainText("已完成 3 份");
  expect(names).toEqual(["资料1.txt", "资料2.txt", "资料2.txt", "资料3.txt"]);
});

test("batch indexing failure never reuploads an accepted file or starts the next file", async ({
  page,
}) => {
  await mock(page);
  let count = 0;
  await page.route("**/api/v2/projects/1/materials", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    count++;
    return route.fulfill(uploadReply("failed-batch-index"));
  });
  await page.route("**/api/v2/jobs/failed-batch-index", (route) =>
    route.fulfill({
      json: { jobId: "failed-batch-index", state: "failed", progress: {} },
    }),
  );
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles(uploadFiles());
  const dialog = page.getByRole("dialog", { name: "批量上传资料" });
  await dialog.getByRole("button", { name: "开始上传 3 份资料" }).click();
  await expect(dialog).toContainText("请在资料列表重试索引");
  await expect(dialog.getByRole("button", { name: /核对后重试/ })).toHaveCount(
    0,
  );
  expect(count).toBe(1);
  await dialog.getByRole("button", { name: "完成", exact: true }).click();
  await expect(page.locator(".job-status")).toContainText("索引失败");
});

test("batch upload rejects invalid selections and session changes stop the remaining batch", async ({
  page,
}) => {
  await mock(page);
  let count = 0;
  await page.route("**/api/v2/projects/1/materials", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    count++;
    return route.fulfill({
      status: 409,
      json: { error: { code: "ACCOUNT_CHANGED", message: "登录账号已变化" } },
    });
  });
  await page.goto("/library");
  const input = page.getByLabel("选择上传资料");
  await input.setInputFiles(uploadFiles(11));
  await expect(page.getByRole("alert")).toContainText("每批最多上传 10 份");
  await input.setInputFiles([
    uploadFiles(1)[0],
    { name: "empty.txt", mimeType: "text/plain", buffer: Buffer.alloc(0) },
  ]);
  await expect(page.getByRole("alert")).toContainText("非空且不超过 50 MB");
  await input.setInputFiles([
    uploadFiles(1)[0],
    {
      name: "program.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("data"),
    },
  ]);
  await expect(page.getByRole("alert")).toContainText("仅支持 TXT");
  expect(count).toBe(0);
  await input.setInputFiles(uploadFiles());
  await page.getByRole("button", { name: "开始上传 3 份资料" }).click();
  await expect(
    page.getByRole("heading", { name: "请重新进入学习应用" }),
  ).toBeVisible();
  expect(count).toBe(1);
});

for (const width of [390, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`learning flow prioritizes studying and stable dialogs at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (value) => localStorage.setItem("learn.theme", value),
        theme,
      );
      await mock(page);
      let deletes = 0;
      page.on("request", (request) => {
        if (request.method() === "DELETE") deletes++;
      });
      await page.goto("/study");
      const trigger = page.getByRole("button", {
        name: "删除学习计划：Python 从入门到实践",
        exact: true,
      });
      await trigger.click();
      const dialog = page.getByRole("dialog", {
        name: "删除学习计划",
        exact: true,
      });
      await expect(dialog).toBeVisible();
      expect(
        await dialog.evaluate((element) => element.closest(".project-card")),
      ).toBeNull();
      const first = (await dialog.boundingBox())!;
      await page.mouse.move(width - 10, 20);
      await expect
        .poll(async () => Math.round((await dialog.boundingBox())!.width))
        .toBe(Math.round(first.width));
      expect(first.x).toBeGreaterThanOrEqual(0);
      expect(first.x + first.width).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: testInfo.outputPath("delete-confirmation.png"),
      });
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(trigger).toBeFocused();
      expect(deletes).toBe(0);

      await page.goto("/study?project=1&chapter=12");
      await expect(
        page.getByRole("link", { name: "前往下一节", exact: true }),
      ).toHaveCount(0);
      await page
        .getByRole("button", { name: "标记为已学完", exact: true })
        .click();
      const next = page.getByRole("link", { name: "前往下一节", exact: true });
      await expect(next).toHaveAttribute("href", "/study?project=1&chapter=13");
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      const back = page.getByRole("link", {
        name: "返回章节目录",
        exact: true,
      });
      await expect(back).toBeInViewport();
      await next.click();
      await expect(page).toHaveURL(/chapter=13/);
      await page
        .getByRole("button", { name: "标记为已学完", exact: true })
        .click();
      await expect(
        page.getByRole("link", {
          name: "已完成最后一节，返回目录",
          exact: true,
        }),
      ).toBeVisible();

      await page.goto("/review");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator(".review-panel")).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("review-first.png"),
        fullPage: true,
      });
      await page
        .getByRole("button", { name: "新建复习卡", exact: true })
        .click();
      const cardDialog = page.getByRole("dialog", {
        name: "创建复习卡",
        exact: true,
      });
      await expect(cardDialog).toBeVisible();
      await cardDialog.getByLabel("生成数量").fill("3");
      await page.keyboard.press("Escape");
      await page
        .getByRole("button", { name: "新建复习卡", exact: true })
        .click();
      await expect(cardDialog.getByLabel("生成数量")).toHaveValue("3");
      await page.screenshot({
        path: testInfo.outputPath("card-generator.png"),
      });
      await page.keyboard.press("Escape");
      await page
        .getByRole("button", { name: "手动添加复习卡", exact: true })
        .click();
      await page.screenshot({
        path: testInfo.outputPath("manual-card-spacing.png"),
      });
      await page.keyboard.press("Escape");
      await page.goto("/quiz");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(
        page.getByRole("heading", { name: "我的测验", exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("quiz-first.png"),
        fullPage: true,
      });
      await page.getByRole("button", { name: "新建测验", exact: true }).click();
      await expect(
        page.getByRole("dialog", { name: "创建新测验", exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("quiz-generator.png"),
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    });

    test(`lesson diagrams and compact reading controls at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (value) => localStorage.setItem("learn.theme", value),
        theme,
      );
      await mock(page);
      await page.route("**/api/v2/projects/1/nodes", async (route) => {
        const response = await createDemo().handle(route.request().url(), {});
        const data = await response.json();
        data.items[0].description =
          '## 从数数到进位\n\n理解十进制的组成。\n\n```learning-diagram\n{"title":"0到20的数位结构","nodes":[{"id":"zero","label":"0：一个也没有"},{"id":"one","label":"1到9：逐个计数"},{"id":"ten","label":"10：十个一合成一个十"},{"id":"twenty","label":"20：两个十"}],"edges":[["zero","one"],["one","ten"],["ten","twenty"]]}\n```\n\n' +
          "理解个位与十位之间的关系。\n\n".repeat(30);
        await route.fulfill({ json: data });
      });
      await page.goto("/study?project=1&chapter=11");
      const diagram = page.getByRole("img", {
        name: "0到20的数位结构",
        exact: true,
      });
      await expect(diagram).toBeVisible();
      // Keep knowledge diagrams at their intended reading size on wide screens.
      // Stretching this narrow chain to the whole lesson makes its text enormous.
      const diagramBox = (await diagram.boundingBox())!;
      expect(diagramBox.width).toBeLessThanOrEqual(400);
      await expect(page.locator(".learning-diagram .diagram-node")).toHaveCount(
        4,
      );
      await expect(page.locator(".learning-diagram")).not.toContainText(
        '"nodes"',
      );
      await page.screenshot({ path: testInfo.outputPath("reading-tools.png") });
      await page.locator(".learning-diagram").scrollIntoViewIfNeeded();
      await page.screenshot({
        path: testInfo.outputPath("knowledge-diagram.png"),
      });
      await page.getByText("文字版知识关系", { exact: true }).click();
      await expect(page.locator(".learning-diagram li").first()).toContainText(
        "0：一个也没有 → 1到9：逐个计数",
      );
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await expect(
        page.getByRole("link", { name: "返回章节目录", exact: true }),
      ).toBeInViewport();
      const backBox = (await page
        .getByRole("link", { name: "返回章节目录", exact: true })
        .boundingBox())!;
      expect(backBox.y).toBeGreaterThanOrEqual(0);
      expect(backBox.y).toBeLessThan(77);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    });
  }
}

test("lesson practice generation is explicit and opens the generated quiz", async ({
  page,
}) => {
  await mock(page);
  let calls = 0;
  await page.route("**/api/v2/projects/1/quiz-jobs", async (route) => {
    calls++;
    expect(route.request().postDataJSON()).toEqual({
      nodeIds: [12],
      count: 5,
      qtype: "practice",
    });
    await route.fulfill({
      status: 202,
      json: { jobId: "practice-ui", state: "queued" },
    });
  });
  await page.route("**/api/v2/jobs/practice-ui", (route) =>
    route.fulfill({
      json: {
        jobId: "practice-ui",
        state: "done",
        progress: { count: 5, quizId: 61 },
      },
    }),
  );
  await page.goto("/study?project=1&chapter=12");
  await page.getByRole("tab", { name: "练习", exact: true }).click();
  await page.getByRole("button", { name: "生成本节练习", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "生成本节练习",
    exact: true,
  });
  await expect(dialog.getByRole("checkbox", { name: /A2 变量/ })).toBeChecked();
  expect(calls).toBe(0);
  await dialog.getByRole("button", { name: "生成练习", exact: true }).click();
  await dialog.getByRole("link", { name: "开始作答", exact: true }).click();
  await expect(page).toHaveURL(/quiz\?project=1&quiz=61/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "提交答案", exact: true }),
  ).toBeVisible();
  expect(calls).toBe(1);
});

test("resource search only constructs an external keyword link", async ({
  page,
}) => {
  await mock(page);
  const outside: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:"))
      outside.push(request.url());
  });
  await page.goto("/library");
  await page.getByRole("button", { name: "联网查资料", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "联网查资料", exact: true });
  await expect(
    dialog.getByRole("button", { name: "搜索资料", exact: true }),
  ).toBeDisabled();
  await dialog
    .getByRole("searchbox", { name: "搜索关键词", exact: true })
    .fill("微积分 & PDF");
  let link = dialog.getByRole("link", { name: "搜索资料", exact: true });
  await expect(link).toHaveAttribute("target", "_blank");
  expect(
    new URL((await link.getAttribute("href"))!).searchParams.get("q"),
  ).toBe("微积分 & PDF");
  await dialog.getByRole("combobox", { name: "搜索引擎", exact: true }).click();
  await page.getByRole("option", { name: "百度", exact: true }).click();
  link = dialog.getByRole("link", { name: "搜索资料", exact: true });
  const url = new URL((await link.getAttribute("href"))!);
  expect(url.hostname).toBe("www.baidu.com");
  expect([...url.searchParams.keys()]).toEqual(["wd"]);
  expect(url.searchParams.get("wd")).toBe("微积分 & PDF");
  expect(outside).toEqual([]);
});

test("closing a generator keeps tracking the task and refreshes the quiz list", async ({
  page,
}) => {
  await mock(page);
  let generated = false;
  let calls = 0;
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v2/projects/1/quizzes", (route) =>
    route.fulfill({
      json: {
        items: generated
          ? [
              {
                id: 61,
                title: "关闭窗口后保存的测验",
                createdAt: new Date().toISOString(),
              },
            ]
          : [],
      },
    }),
  );
  await page.route("**/api/v2/projects/1/quiz-jobs", (route) => {
    calls++;
    return route.fulfill({
      status: 202,
      json: { jobId: "dialog-background", state: "queued" },
    });
  });
  await page.route("**/api/v2/jobs/dialog-background", (route) =>
    route.fulfill({
      json: { jobId: "dialog-background", state: "running", progress: {} },
    }),
  );
  await page.route(
    "**/api/v2/jobs/dialog-background/events?*",
    async (route) => {
      await waiting;
      generated = true;
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: progress\ndata: ${JSON.stringify({
          jobId: "dialog-background",
          state: "done",
          progress: { quizId: 61, count: 5 },
        })}\n\n`,
      });
    },
  );
  await page.goto("/quiz");
  await page.getByRole("button", { name: "新建测验", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "创建新测验", exact: true });
  await dialog.getByRole("checkbox", { name: /A1 认识 Python/ }).check();
  await dialog.getByRole("button", { name: "生成测验", exact: true }).click();
  await expect(
    dialog.getByText("正在生成学习内容", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  release();
  await expect(
    page.getByRole("button", { name: /关闭窗口后保存的测验/ }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "新建测验", exact: true }).click();
  await expect(
    dialog.getByRole("checkbox", { name: /A1 认识 Python/ }),
  ).toBeChecked();
  await expect(dialog.getByText("生成已完成", { exact: true })).toBeVisible();
  expect(calls).toBe(1);
});
