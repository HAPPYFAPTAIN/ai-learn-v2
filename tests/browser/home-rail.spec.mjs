import { test, expect } from '@playwright/test';

for (const width of [390, 1280, 1920]) {
  test(`home rail preserves numbering and link styling at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors=[];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    const steps=page.locator('#le-home-rail .le-rail-steps');
    await expect(steps).toHaveCSS('list-style-position','outside');
    const geometry=await steps.locator('li').evaluateAll(items=>items.map(item=>({
      top:item.getBoundingClientRect().top,
      titleTop:item.querySelector('b').getBoundingClientRect().top,
    })));
    expect(geometry).toHaveLength(3);
    for (const item of geometry) expect(Math.abs(item.top-item.titleTop)).toBeLessThan(1);
    const links=page.locator('#le-home-rail .le-rail-links a');
    await expect(links).toHaveCount(4);
    for (const link of await links.all()) await expect(link).toHaveCSS('text-decoration-line','none');
    await expect(page.locator('#le-home-wide')).toHaveCSS('display',width>=1800?'grid':'flex');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    expect(errors).toEqual([]);
  });
}
