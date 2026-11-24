import { expect, type Page } from "@playwright/test";

const groupByLink: Record<string, string> = {
  学习首页: "开始学习",
  学习路线: "开始学习",
  学习工作台: "当前学习计划",
  间隔复习: "练习与复习",
  查漏测验: "练习与复习",
  学习看板: "练习与复习",
  知识问答: "知识与资料",
  资料库: "知识与资料",
  学习工具: "知识与资料",
  模型设置: "设置",
};

export async function openNavigation(page: Page) {
  const drawer = page.locator("#primary-nav");
  const trigger = page.locator('button[aria-label="打开导航"]:visible');
  for (let attempt = 0; attempt < 3; attempt++) {
    if ((await drawer.getAttribute("inert")) === null) {
      await expect(drawer).toBeVisible();
      return;
    }
    await trigger.click();
    try {
      await expect(drawer).not.toHaveAttribute("inert", "", {
        timeout: 1000,
      });
      await expect(drawer).toBeVisible();
      return;
    } catch {
      await page.waitForTimeout(400);
    }
  }
  await expect(drawer).not.toHaveAttribute("inert", "");
  await expect(drawer).toBeVisible();
}

export async function openNavigationGroup(page: Page, title: string) {
  await openNavigation(page);
  const group = page.getByRole("button", {
    name: new RegExp(title),
  });
  if ((await group.getAttribute("aria-expanded")) !== "true") {
    await group.click();
  }
  await expect(group).toHaveAttribute("aria-expanded", "true");
}

export async function navigate(page: Page, label: string) {
  const group = groupByLink[label];
  if (group) await openNavigationGroup(page, group);
  else await openNavigation(page);
  await page
    .locator("#primary-nav")
    .getByRole("link", { name: label, exact: true })
    .click();
}
