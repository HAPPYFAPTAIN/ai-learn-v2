import { test, expect } from "@playwright/test";

test("local UI preview simulates upload bytes and indexing without an API", async ({
  page,
}) => {
  const businessRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/v2/")) businessRequests.push(req.url());
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles({
    name: "UI测试资料.txt",
    mimeType: "text/plain",
    buffer: Buffer.alloc(2048, "x"),
  });
  const status = page.getByRole("region", { name: "文件上传进度" });
  await expect(status).toContainText("演示进度");
  await expect(status).toContainText("上传已确认");
  await expect(page.locator(".job-status")).toContainText("资料索引已完成");
  await expect(
    page.locator(".file-row").filter({ hasText: "UI测试资料.txt" }),
  ).toBeVisible();
  expect(businessRequests).toHaveLength(0);
});

test("local UI preview shows sample charts and keeps annotations while navigating", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page.locator(".chart-bar")).toHaveCount(7);
  await page.getByRole("link", { name: "学习工作台", exact: true }).click();
  await page.getByRole("link", { name: /Python 从入门到实践/ }).click();
  await page.getByRole("link", { name: /认识 Python 与第一个程序/ }).click();
  const paragraph = page.locator(".lesson-reading .prose > p").first();
  await expect(paragraph).toBeVisible();
  await paragraph.scrollIntoViewIfNeeded();
  await paragraph.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
  });
  await page.getByRole("button", { name: "为所选文字添加批注" }).click();
  await page.getByLabel("我的批注").fill("本地UI批注测试");
  await page.getByRole("button", { name: "保存批注" }).click();
  await expect(page.locator(".annotation-card")).toContainText(
    "本地UI批注测试",
  );
  await page.getByRole("link", { name: /返回章节目录/ }).click();
  await page.getByRole("link", { name: /认识 Python 与第一个程序/ }).click();
  await page.getByRole("button", { name: "查看本章批注" }).click();
  await expect(page.locator(".annotation-card")).toContainText(
    "本地UI批注测试",
  );
});

test("local UI preview processes a selected batch without a business API", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/v2/")) requests.push(req.url());
  });
  await page.goto("/library");
  await page.getByLabel("选择上传资料").setInputFiles(
    [1, 2].map((i) => ({
      name: `批量演示${i}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(`演示资料${i}`),
    })),
  );
  const dialog = page.getByRole("dialog", { name: "批量上传资料" });
  await dialog.getByRole("button", { name: "开始上传 2 份资料" }).click();
  await expect(dialog).toContainText("已完成 2 份");
  await dialog.getByRole("button", { name: "完成", exact: true }).click();
  await expect(
    page.locator(".file-row").filter({ hasText: "批量演示1.txt" }),
  ).toBeVisible();
  await expect(
    page.locator(".file-row").filter({ hasText: "批量演示2.txt" }),
  ).toBeVisible();
  expect(requests).toHaveLength(0);
});
