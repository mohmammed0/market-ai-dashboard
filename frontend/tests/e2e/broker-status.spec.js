import { test, expect } from "@playwright/test";

import { establishAuthState, getApiBaseUrl, resolveAuthSession } from "./support/auth";

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("Portfolio snapshot contract and trading desk render", async ({ page, request }) => {
  const authSession = await resolveAuthSession(request);
  const response = await page.request.get(`${getApiBaseUrl()}/api/portfolio/snapshot`, { headers: authSession.headers });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.contract_version).toBe("v1");
  expect(typeof payload.source_label).toBe("string");
  expect(payload.summary).toBeTruthy();

  await page.goto("/trading");
  await expect(page.getByText("مكتب التداول").first()).toBeVisible();
  await expect(page.getByText("المراكز المفتوحة").first()).toBeVisible();
});
