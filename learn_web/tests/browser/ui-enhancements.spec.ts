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
