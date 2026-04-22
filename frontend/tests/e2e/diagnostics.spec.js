import { test, expect } from "@playwright/test";

import { establishAuthState } from "./support/auth";

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("Auto-trading diagnostics page renders", async ({ page }) => {
  await page.goto("/diagnostics/auto-trading");
  await expect(page.getByText("تشخيص قرارات التداول الآلي").first()).toBeVisible();
  await expect(page.getByText("اختيار الدورة").first()).toBeVisible();
});
