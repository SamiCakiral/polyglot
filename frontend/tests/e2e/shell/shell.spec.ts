import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/today");
  await expect(page.getByRole("heading", { level: 1, name: "Aujourd'hui" })).toBeVisible();
});

test("keeps the shell inside the viewport without truncated mobile labels", async ({
  page,
}, testInfo) => {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth);
  if (testInfo.project.name === "zoom-200") {
    expect(testInfo.project.metadata).toMatchObject({
      physicalViewportWidth: 1440,
      zoomPercent: 200,
    });
    expect(metrics.clientWidth).toBe(720);
  }

  const mobileLabels = page.locator(".mobile-navigation__label");
  const labelCount = await mobileLabels.count();
  expect(labelCount).toBe(5);
  for (let index = 0; index < labelCount; index += 1) {
    const style = await mobileLabels.nth(index).evaluate((element) => {
      const computed = getComputedStyle(element);
      return {
        overflow: computed.overflow,
        textOverflow: computed.textOverflow,
        whiteSpace: computed.whiteSpace,
      };
    });
    expect(style.textOverflow).not.toBe("ellipsis");
  }

  if (metrics.clientWidth < 1024) {
    const mobileNavigation = page.getByRole("navigation", { name: "Navigation mobile" });
    for (const label of [
      "Aujourd'hui",
      "Apprendre",
      "S'entraîner",
      "Vocabulaire",
      "Progression",
    ]) {
      await expect(mobileNavigation.getByRole("link", { name: label })).toHaveCount(1);
    }
  }

  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath(`shell-${testInfo.project.name}.png`),
  });
});

test("keeps shell navigation operable from the keyboard", async ({ page }) => {
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Aller au contenu principal" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();

  const cssViewportWidth = await page.evaluate(() => window.innerWidth);
  if (cssViewportWidth < 1024) {
    const menuButton = page.getByRole("button", { name: "Ouvrir le menu" });
    await menuButton.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("navigation", { name: "Menu secondaire" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menuButton).toBeFocused();
    await expect(page.getByRole("navigation", { name: "Menu secondaire" })).toHaveCount(0);
    return;
  }

  const learnLink = page
    .getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Apprendre" });
  await learnLink.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Apprendre" })).toBeVisible();
});

test("has no serious, critical, or color contrast axe violation", async ({ page }) => {
  const results = await new AxeBuilder({ page }).include(".app-shell").analyze();
  const blockingViolations = results.violations.filter(
    ({ id, impact }) => id === "color-contrast" || impact === "serious" || impact === "critical",
  );

  expect(blockingViolations).toEqual([]);
});

test("does not enable browser mocks without explicit opt-in", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "shell-320", "Mock mode is viewport-independent");
  await page.goto("http://127.0.0.1:4176/today");

  await expect(page.getByRole("alert")).toContainText("Connexion interrompue");
  await expect(page.getByRole("heading", { level: 1, name: "Aujourd'hui" })).toHaveCount(0);
});

test("rejects unexpected requests while contract mocks are enabled", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "shell-320", "Mock mode is viewport-independent");
  const result = await page.evaluate(async () => {
    try {
      const response = await fetch("/api/v1/unexpected-w17-request");
      return { rejected: false, status: response.status };
    } catch {
      return { rejected: true, status: null };
    }
  });

  expect(result).toEqual({ rejected: false, status: 500 });
});
