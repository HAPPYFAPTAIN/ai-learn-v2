import { test, expect } from "@playwright/test";
import { navigate } from "./navigation";
import { createDemo } from "../../src/demo/data";

test("production CSP allows formulas, highlighted code, mindmaps and theme switching", async ({
  page,
}) => {
  const violations: string[] = [];
  await page.exposeFunction("recordPolicyViolation", (directive: string) =>
    violations.push(directive),
  );
  await page.addInitScript(() => {
    localStorage.setItem("learn.theme", "dark");
    document.addEventListener("securitypolicyviolation", (event) => {
      void (
        window as unknown as {
          recordPolicyViolation: (directive: string) => Promise<void>;
        }
      ).recordPolicyViolation(event.effectiveDirective);
    });
  });
  const demo = createDemo();
  await page.route("**/api/v2/**", async (route) => {
    const req = route.request();
    const response = await demo.handle(req.url(), {
      method: req.method(),
      body: req.postData() || undefined,
    });
    const payload = await response.json();
    if (new URL(req.url()).pathname.endsWith("/nodes")) {
      payload.items.find((node: { id: number }) => node.id === 11).description =
        "## 公式与代码\n\n$$\n\\int_0^1 x^2\\,dx = \\frac13\n$$\n\n```python\nprint('Hello, learning!')\n```";
    }
    await route.fulfill({ status: response.status, json: payload });
  });
  const response = await page.goto("/study?project=1&chapter=11");
  expect(response?.headers()["content-security-policy"]).toContain(
    "script-src 'self';",
  );
  expect(response?.headers()["x-content-type-options"]).toBe("nosniff");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".katex-display .katex")).toBeVisible();
  await expect(page.locator(".hljs-string")).toContainText("Hello, learning!");
  await page.getByRole("button", { name: "切换浅色主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await navigate(page, "学习路线");
  await page.getByRole("button", { name: "思维导图", exact: true }).click();
  const map = page.getByRole("region", { name: "思维导图", exact: true });
  await expect(map.getByRole("img")).toBeVisible();
  await expect(map.locator("svg")).toContainText(/认识\s*Python/);
  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    const faces = [...document.fonts].filter((face) =>
      /MiSans/i.test(face.family),
    );
    return {
      check: document.fonts.check('500 16px "MiSans VF"'),
      total: faces.length,
      loaded: faces.some((face) => face.status === "loaded"),
    };
  });
  expect(fonts.check).toBe(true);
  expect(fonts.total).toBeGreaterThan(0);
  expect(fonts.loaded).toBe(true);
  expect(violations).toEqual([]);
});
