import { test, expect } from "@playwright/test";

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`model settings layout at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.addInitScript(
        (theme) => localStorage.setItem("learn.theme", theme),
        theme,
      );
      await page.goto("/models");
      await expect(
        page.getByRole("heading", { name: "已导入的模型", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".provider-preset").first()).toHaveText(
        /自定义添加新模型/,
      );
      await expect(
        page.locator(".provider-preset .provider-logo img"),
      ).toHaveCount(32);
      await expect
        .poll(() =>
          page
            .locator(".provider-logo img")
            .evaluateAll((images) =>
              images.every(
                (image) =>
                  (image as HTMLImageElement).complete &&
                  (image as HTMLImageElement).naturalWidth > 0,
              ),
            ),
        )
        .toBe(true);
      await expect(
        page.getByRole("combobox", { name: "主模型", exact: true }),
      ).toContainText("deepseek-flash");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath("models.png"),
        fullPage: false,
      });
      await page.getByRole("combobox", { name: "主模型", exact: true }).click();
      const menu = page.getByRole("listbox", { name: "可选主模型" });
      await expect(menu).toBeVisible();
      const triggerBox = (await page
        .getByRole("combobox", { name: "主模型", exact: true })
        .boundingBox())!;
      expect((await menu.boundingBox())!.y).toBeGreaterThanOrEqual(
        triggerBox.y + triggerBox.height,
      );
      await page
        .getByRole("option", { name: "deepseek-v4-pro", exact: true })
        .click();
      await page
        .getByRole("button", { name: "设为主模型", exact: true })
        .click();
      await expect(page.locator(".primary-model-summary")).toContainText(
        "deepseek-v4-pro",
      );
      await page
        .getByRole("button", { name: "添加 OpenAI", exact: true })
        .click();
      const dialog = page.getByRole("dialog", { name: "添加新供应商" });
      await expect(dialog).toBeVisible();
      const box = (await dialog.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      expect(box.y + box.height).toBeLessThanOrEqual(960);
      const header = (await page
        .locator(".provider-dialog-header")
        .boundingBox())!;
      const footer = (await page
        .locator(".provider-dialog-footer")
        .boundingBox())!;
      await page.locator(".provider-dialog-body").evaluate((element) => {
        element.scrollTop = element.scrollHeight;
      });
      expect(
        (await page.locator(".provider-dialog-header").boundingBox())!.y,
      ).toBe(header.y);
      expect(
        (await page.locator(".provider-dialog-footer").boundingBox())!.y,
      ).toBe(footer.y);
      await page.locator(".provider-dialog-body").evaluate((element) => {
        element.scrollTop = 0;
      });
      await expect(page.getByLabel("API 地址", { exact: true })).toHaveValue(
        "https://api.openai.com/v1",
      );
      await expect(page.getByLabel("API Key", { exact: true })).toBeDisabled();
      await expect(
        page.getByLabel("供应商名称", { exact: true }),
      ).toBeFocused();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath("provider-form.png"),
        fullPage: false,
      });
    });
  }

test("switching supplier filters models and only confirmation changes primary", async ({
  page,
}) => {
  const external: string[] = [];
  page.on("request", (req) => {
    if (!req.url().startsWith("http://127.0.0.1:5174/"))
      external.push(req.url());
  });
  await page.goto("/models");
  await page
    .getByRole("group", { name: "已导入的供应商" })
    .getByRole("button", { name: /阿里云百炼/ })
    .click();
  await expect(page.locator(".primary-model-summary")).toContainText(
    "DeepSeek / deepseek-flash",
  );
  const picker = page.getByRole("combobox", { name: "主模型", exact: true });
  await picker.click();
  await expect(
    page.getByRole("option", { name: "deepseek-flash", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("option", { name: "qwen-flash", exact: true }).click();
  await page.getByRole("button", { name: "设为主模型", exact: true }).click();
  await expect(page.locator(".primary-model-summary")).toContainText(
    "阿里云百炼 / qwen-flash",
  );
  await page.getByRole("link", { name: "资料库", exact: true }).click();
  await page.getByRole("link", { name: "模型设置", exact: true }).click();
  await expect(picker).toContainText("qwen-flash");
  await page.reload();
  await expect(picker).toContainText("deepseek-flash");
  expect(external).toEqual([]);
});

test("provider catalog includes all legacy choices and supports search and categories", async ({
  page,
}) => {
  await page.goto("/models");
  await expect(page.locator(".provider-preset")).toHaveCount(33);
  const search = page.getByRole("searchbox", { name: "搜索模型供应商" });
  await search.fill("opencode");
  await expect(page.locator(".provider-preset")).toHaveCount(2);
  await page
    .getByRole("button", { name: "添加 OpenCode", exact: true })
    .click();
  const profile = page.getByRole("combobox", { name: "接口区域 / 服务方案" });
  await profile.click();
  await page
    .getByRole("option", { name: "Console / Zen · 按量", exact: true })
    .click();
  await expect(page.getByLabel("API 地址", { exact: true })).toHaveValue(
    "https://opencode.ai/inference/openai/v1",
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "清空搜索模型供应商", exact: true })
    .click();
  await page
    .getByRole("group", { name: "供应商分类" })
    .getByRole("button", { name: "本地服务", exact: true })
    .click();
  await expect(page.locator(".provider-preset")).toHaveCount(2);
  await page.getByRole("button", { name: "添加 Ollama", exact: true }).click();
  await expect(page.getByLabel("API 地址", { exact: true })).toHaveValue(
    "http://localhost:11434/v1",
  );
  await page.getByRole("button", { name: "返回模型设置", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await search.fill("不存在的平台");
  await expect(page.locator(".provider-preset")).toHaveCount(1);
  await expect(
    page.getByText("没有找到匹配的供应商，可以使用自定义添加。"),
  ).toBeVisible();
});

test("provider dialog contains keyboard focus and restores it on escape", async ({
  page,
}) => {
  await page.goto("/models");
  const trigger = page.getByRole("button", {
    name: "自定义添加新模型",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "添加新供应商" });
  await expect(page.getByLabel("供应商名称", { exact: true })).toBeFocused();
  for (let index = 0; index < 16; index++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate(
        (element) =>
          element.contains(document.activeElement) ||
          element === document.activeElement,
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  const box = (await dialog.boundingBox())!;
  await page.mouse.click(Math.max(1, box.x - 10), box.y + 10);
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("empty state adds a custom connection with multiple model IDs", async ({
  page,
}) => {
  await page.goto("/models?empty=1");
  await expect(
    page.getByRole("heading", { name: "暂无已导入的模型" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "自定义添加新模型", exact: true })
    .click();
  await page.getByLabel("供应商名称", { exact: true }).fill("我的模型服务");
  await page
    .getByLabel("API 地址", { exact: true })
    .fill("https://example.com/v1/");
  await page
    .getByLabel("模型 ID", { exact: true })
    .fill("model-one\nmodel-two,model-one，model-three");
  await page
    .getByRole("button", { name: "添加到演示列表", exact: true })
    .click();
  await expect(page.locator(".connected-providers")).toContainText("3 个模型");
  await expect(page.getByRole("form")).toHaveCount(0);
  const picker = page.getByRole("combobox", { name: "主模型", exact: true });
  await picker.click();
  await page.getByRole("option", { name: "model-two", exact: true }).click();
  await page.getByRole("button", { name: "设为主模型", exact: true }).click();
  await expect(page.locator(".primary-model-summary")).toContainText(
    "我的模型服务 / model-two",
  );
  await page.getByRole("link", { name: "学习首页", exact: true }).click();
  await page.getByRole("link", { name: "模型设置", exact: true }).click();
  await expect(picker).toContainText("model-two");
});

test("preset validation keeps invalid data out of the list and cancel restores focus", async ({
  page,
}) => {
  await page.goto("/models");
  const trigger = page.getByRole("button", {
    name: "添加 DeepSeek",
    exact: true,
  });
  await trigger.click();
  await page
    .getByRole("button", { name: "添加到演示列表", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("名称已存在");
  await page.getByLabel("供应商名称", { exact: true }).fill("DeepSeek 测试");
  await page
    .getByLabel("API 地址", { exact: true })
    .fill("https://example.com/v1?key=demo");
  await page
    .getByRole("button", { name: "添加到演示列表", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("API 根地址");
  await expect(page.locator(".connected-providers button")).toHaveCount(2);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("form")).toHaveCount(0);
});

test("each preset opens its own editable form", async ({ page }) => {
  await page.goto("/models");
  for (const name of [
    "DeepSeek",
    "OpenAI",
    "阿里云百炼",
    "智谱 BigModel",
    "Kimi · 月之暗面",
    "硅基流动",
    "火山方舟",
  ]) {
    await page
      .getByRole("button", { name: `添加 ${name}`, exact: true })
      .click();
    await expect(page.getByLabel("供应商名称", { exact: true })).toHaveValue(
      name,
    );
    await expect(page.getByLabel("API 地址", { exact: true })).toHaveValue(
      /^https:\/\//,
    );
    await page
      .getByRole("button", { name: "关闭添加模型", exact: true })
      .click();
  }
});
