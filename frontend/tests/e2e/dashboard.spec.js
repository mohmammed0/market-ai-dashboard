import { test, expect } from "@playwright/test";

import { establishAuthState } from "./support/auth";

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("Dashboard renders market and status panels", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Broker Account|Legacy Snapshot/).first()).toBeVisible();
  await expect(page.getByText("حالة النظام").first()).toBeVisible();
  await expect(page.getByText("مراقبة التشغيل الحي").first()).toBeVisible();
});
