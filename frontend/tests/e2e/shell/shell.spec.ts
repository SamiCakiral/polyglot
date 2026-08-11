import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/today");
  await expect(
    page.getByRole("heading", { level: 1, name: "Aujourd'hui" }),
  ).toBeVisible();

  if (testInfo.project.name === "browser-zoom-200") {
    await page.evaluate(() => {
      const heading = document.querySelector("h1");
      const accountControl = document.querySelector(".account-nav a");
      if (
        !(heading instanceof HTMLElement) ||
        !(accountControl instanceof HTMLElement)
      ) {
        throw new Error("Missing shell zoom probes");
      }
      document.documentElement.dataset.baselineHeadingHeight = String(
        heading.getBoundingClientRect().height,
      );
      document.documentElement.dataset.baselineControlHeight = String(
        accountControl.getBoundingClientRect().height,
      );
    });
  }
});

test("keeps the shell inside the viewport without truncated mobile labels", async ({
  page,
}, testInfo) => {
  if (testInfo.project.name === "browser-zoom-200") {
    await page.evaluate(() => {
      document.body.style.zoom = "2";
    });
    await expect
      .poll(() => page.evaluate(() => getComputedStyle(document.body).zoom))
      .toBe("2");
    await page.evaluate(() => new Promise(requestAnimationFrame));
  }

  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth);
  if (testInfo.project.name === "reflow-720") {
    expect(testInfo.project.metadata).toMatchObject({
      effectiveViewportWidth: 720,
    });
    expect(metrics.clientWidth).toBe(720);
  }

  const mobileLabels = page.locator(".mobile-navigation__label");
  const labelCount = await mobileLabels.count();
  expect(labelCount).toBe(5);
  if (testInfo.project.name === "shell-320") {
    for (let index = 0; index < labelCount; index += 1) {
      const label = mobileLabels.nth(index);
      await expect(label).toBeVisible();
      const geometry = await label.evaluate((element) => {
        const labelBox = element.getBoundingClientRect();
        const linkBox = element.parentElement?.getBoundingClientRect();
        return {
          clientHeight: element.clientHeight,
          clientWidth: element.clientWidth,
          labelBox: { left: labelBox.left, right: labelBox.right },
          linkBox: linkBox
            ? { left: linkBox.left, right: linkBox.right }
            : null,
          scrollHeight: element.scrollHeight,
          scrollWidth: element.scrollWidth,
        };
      });
      expect(geometry.clientWidth).toBeGreaterThan(1);
      expect(geometry.clientHeight).toBeGreaterThan(1);
      expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
      expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.clientHeight);
      expect(geometry.linkBox).not.toBeNull();
      expect(geometry.labelBox.left).toBeGreaterThanOrEqual(
        geometry.linkBox?.left ?? 0,
      );
      expect(geometry.labelBox.right).toBeLessThanOrEqual(
        geometry.linkBox?.right ?? 0,
      );
    }
  }

  if (
    ["shell-320", "shell-768", "reflow-720"].includes(testInfo.project.name)
  ) {
    const mobileNavigation = page.getByRole("navigation", {
      name: "Navigation mobile",
    });
    for (const label of [
      "Aujourd'hui",
      "Apprendre",
      "S'entraîner",
      "Vocabulaire",
      "Progression",
    ]) {
      await expect(
        mobileNavigation.getByRole("link", { name: label }),
      ).toHaveCount(1);
    }
  }

  if (testInfo.project.name === "browser-zoom-200") {
    const zoomEvidence = await page.evaluate(() => {
      const heading = document.querySelector("h1");
      const accountControl = document.querySelector(".account-nav a");
      if (
        !(heading instanceof HTMLElement) ||
        !(accountControl instanceof HTMLElement)
      ) {
        throw new Error("Missing zoomed shell probes");
      }
      return {
        baselineControlHeight: Number(
          document.documentElement.dataset.baselineControlHeight,
        ),
        baselineHeadingHeight: Number(
          document.documentElement.dataset.baselineHeadingHeight,
        ),
        controlHeight: accountControl.getBoundingClientRect().height,
        headingHeight: heading.getBoundingClientRect().height,
        zoom: getComputedStyle(document.body).zoom,
      };
    });
    expect(zoomEvidence.zoom).toBe("2");
    expect(zoomEvidence.headingHeight).toBeGreaterThanOrEqual(
      zoomEvidence.baselineHeadingHeight * 1.9,
    );
    expect(zoomEvidence.controlHeight).toBeGreaterThanOrEqual(
      zoomEvidence.baselineControlHeight * 1.9,
    );
    await expect(
      page
        .getByRole("navigation", { name: "Navigation principale" })
        .getByRole("link"),
    ).toHaveCount(6);
    await expect(
      page
        .getByRole("navigation", { name: "Actions du compte" })
        .getByRole("link"),
    ).toHaveCount(2);
  }

  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath(`shell-${testInfo.project.name}.png`),
  });
});

test("keeps shell navigation operable from the keyboard", async ({ page }) => {
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", {
    name: "Aller au contenu principal",
  });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();

  const cssViewportWidth = await page.evaluate(() => window.innerWidth);
  if (cssViewportWidth < 1024) {
    const menuButton = page.getByRole("button", { name: "Ouvrir le menu" });
    await menuButton.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("navigation", { name: "Menu secondaire" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menuButton).toBeFocused();
    await expect(
      page.getByRole("navigation", { name: "Menu secondaire" }),
    ).toHaveCount(0);
    return;
  }

  const learnLink = page
    .getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Apprendre" });
  await learnLink.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { level: 1, name: "Apprendre" }),
  ).toBeVisible();
});

test("shows accessible tooltips on compact icon controls", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "shell-compact", "Compact rail only");

  const primaryNavigation = page.getByRole("navigation", {
    name: "Navigation principale",
  });
  const learnLink = primaryNavigation.getByRole("link", { name: "Apprendre" });
  await learnLink.focus();
  await expect(page.getByRole("tooltip", { name: "Apprendre" })).toBeVisible();

  const progressLink = primaryNavigation.getByRole("link", {
    name: "Progression",
  });
  await progressLink.hover();
  await expect(
    page.getByRole("tooltip", { name: "Progression" }),
  ).toBeVisible();

  const accountNavigation = page.getByRole("navigation", {
    name: "Actions du compte",
  });
  const settingsLink = accountNavigation.getByRole("link", {
    name: "Préférences",
  });
  await settingsLink.focus();
  await expect(
    page.getByRole("tooltip", { name: "Préférences" }),
  ).toBeVisible();

  const profileLink = accountNavigation.getByRole("link", {
    name: "Profil de langue",
  });
  await profileLink.hover();
  await expect(
    page.getByRole("tooltip", { name: "Profil de langue" }),
  ).toBeVisible();
});

test("keeps edge tooltips inside the viewport", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-1440",
    "Edge placement is viewport-independent",
  );
  const tooltip = page.locator(".account-nav .control-tooltip").last();
  await tooltip.evaluate((element) => {
    element.textContent = "Préférences utilisateur détaillées";
  });

  const geometry = await tooltip.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return {
      left: box.left,
      right: box.right,
      viewportWidth: document.documentElement.clientWidth,
    };
  });
  expect(geometry.left).toBeGreaterThanOrEqual(0);
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth);
});

test("has no serious, critical, or color contrast axe violation", async ({
  page,
}) => {
  const results = await new AxeBuilder({ page })
    .include(".app-shell")
    .analyze();
  const blockingViolations = results.violations.filter(
    ({ id, impact }) =>
      id === "color-contrast" || impact === "serious" || impact === "critical",
  );

  expect(blockingViolations).toEqual([]);
});

test("does not enable browser mocks without explicit opt-in", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-320",
    "Mock mode is viewport-independent",
  );
  await page.goto("http://127.0.0.1:4176/today");

  await expect(page.getByRole("alert")).toContainText(
    /Votre session (a expiré|ne peut pas être ouverte)/,
  );
  await expect(
    page.getByRole("heading", { level: 1, name: "Aujourd'hui" }),
  ).toHaveCount(0);
});

test("fails closed with a mocked 500 for an unexpected request", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-320",
    "Mock mode is viewport-independent",
  );
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

test("onboards a new French to Italian learner", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-1440",
    "New-user flow is viewport-independent",
  );
  await page.goto("/register");
  await page.getByLabel("Adresse e-mail").fill("nouveau@example.test");
  await page.getByLabel("Mot de passe").fill("mot-de-passe-test-2026");
  await page.getByRole("button", { name: "Créer mon espace" }).click();

  await expect(
    page.getByRole("heading", { name: "Votre profil de langue" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Créer ce profil" }).click();
  await expect(
    page.getByRole("heading", { name: "français → italien" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer et continuer" }).click();
  await expect(
    page.getByRole("heading", { name: "Où en êtes-vous en italien ?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Je pars de zéro/ }).click();
  await expect(page.getByRole("heading", { name: "S'entraîner" })).toBeVisible();
});

test("shows canonical vocabulary and four separate progress axes", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-1440",
    "Product data is viewport-independent",
  );
  await page.goto("/vocabulary");
  await expect(page.getByText("binario", { exact: true })).toBeVisible();
  const vocabularyStats = page.locator(".vocabulary-stats");
  await expect(
    vocabularyStats.getByText("3", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    vocabularyStats.getByText("sens rencontrés", { exact: true }),
  ).toBeVisible();

  await page.goto("/progress");
  for (const label of [
    "Compréhension écrite",
    "Compréhension orale",
    "Expression écrite",
    "Expression orale",
  ]) {
    await expect(page.getByRole("heading", { name: label })).toBeVisible();
  }
  await expect(page.getByText("Non évaluable")).toBeVisible();
});

test("lets the learner close the current session", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "shell-1440",
    "Session closure is viewport-independent",
  );
  await page.goto("/settings");
  await page.getByRole("button", { name: "Se déconnecter" }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByRole("heading", { level: 2, name: "Se connecter" }),
  ).toBeVisible();
});
