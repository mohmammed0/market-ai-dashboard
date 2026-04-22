import { test, expect } from "@playwright/test";

import { establishAuthState } from "./support/auth";

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("App boots and renders the top navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("لوحة القيادة").first()).toBeVisible();
  await expect(page.getByTestId("topbar-ai-status")).toBeVisible();
});
