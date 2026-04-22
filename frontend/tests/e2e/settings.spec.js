import { test, expect } from "@playwright/test";

import { establishAuthState } from "./support/auth";

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("Settings page renders runtime controls", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("الإعدادات").first()).toBeVisible();
  await expect(page.getByText("بيئة التشغيل").first()).toBeVisible();
  await expect(page.getByText("وسيط Alpaca").first()).toBeVisible();
  await expect(page.getByText("المهام الخلفية").first()).toBeVisible();
});
