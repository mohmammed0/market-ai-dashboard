import { test, expect } from "@playwright/test";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8010";
const PLAYWRIGHT_AUTH_USERNAME = process.env.PLAYWRIGHT_AUTH_USERNAME || "admin";
const PLAYWRIGHT_AUTH_PASSWORD = process.env.PLAYWRIGHT_AUTH_PASSWORD || "";
let authSessionPromise;

async function resolveAuthSession(request) {
  if (authSessionPromise) {
    return authSessionPromise;
  }
  authSessionPromise = (async () => {
  const statusResponse = await request.get(`${API_BASE_URL}/auth/status`);
  expect(statusResponse.ok()).toBeTruthy();
  const statusPayload = await statusResponse.json();

  if (statusPayload?.auth_enabled === false) {
    return {
      authEnabled: false,
      token: null,
      username: null,
      role: null,
      headers: {},
    };
  }

  if (!PLAYWRIGHT_AUTH_PASSWORD) {
    throw new Error("PLAYWRIGHT_AUTH_PASSWORD must be set when authentication is enabled.");
  }

  const loginResponse = await request.post(`${API_BASE_URL}/auth/login`, {
    data: {
      username: PLAYWRIGHT_AUTH_USERNAME,
      password: PLAYWRIGHT_AUTH_PASSWORD,
    },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const loginPayload = await loginResponse.json();
    return {
      authEnabled: true,
      token: loginPayload.access_token,
      username: loginPayload.username,
      role: loginPayload.role,
      headers: { Authorization: `Bearer ${loginPayload.access_token}` },
    };
  })();
  return authSessionPromise;
}

async function establishAuthState(page, request) {
  const authSession = await resolveAuthSession(request);
  if (!authSession.authEnabled) {
    await page.addInitScript(() => {
      localStorage.removeItem("market_ai_token");
      localStorage.removeItem("market_ai_user");
    });
    return;
  }
  await page.addInitScript(
    ({ token, username, role }) => {
      localStorage.setItem("market_ai_token", token);
      localStorage.setItem(
        "market_ai_user",
        JSON.stringify({
          username,
          role,
        }),
      );
    },
    {
      token: authSession.token,
      username: authSession.username,
      role: authSession.role,
    },
  );
}

test.beforeEach(async ({ page, request }) => {
  await establishAuthState(page, request);
});

test("Dashboard renders current source and topbar AI status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("لوحة القيادة").first()).toBeVisible();
  await expect(page.getByText(/Broker Paper|Internal Simulated Paper/).first()).toBeVisible();
  await expect(page.getByText("حالة النظام").first()).toBeVisible();
  await expect(page.getByTestId("topbar-ai-status")).toBeVisible();
});

test("Settings shows unified runtime labels", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("الإعدادات").first()).toBeVisible();
  await expect(page.getByText("بيئة التشغيل").first()).toBeVisible();
  await expect(page.getByText("وسيط Alpaca").first()).toBeVisible();
  await expect(page.getByText("المهام الخلفية").first()).toBeVisible();
});

test("Live market page loads current terminal shell", async ({ page }) => {
  await page.goto("/live-market");
  await expect(page.getByText("طرفية السوق").first()).toBeVisible();
  await expect(page.getByText("سير عمل السوق").first()).toBeVisible();
});

test("Portfolio snapshot contract is available and paper trading page renders", async ({ page, request }) => {
  const authSession = await resolveAuthSession(request);
  const response = await page.request.get(`${API_BASE_URL}/api/portfolio/snapshot`, { headers: authSession.headers });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.contract_version).toBe("v1");
  expect(typeof payload.source_label).toBe("string");
  expect(payload.summary).toBeTruthy();

  await page.goto("/paper-trading");
  await expect(page.getByText("التداول الورقي").first()).toBeVisible();
  await expect(page.getByText("المراكز المفتوحة").first()).toBeVisible();
});

test("AI status contract is reflected in the top bar", async ({ page, request }) => {
  const authSession = await resolveAuthSession(request);
  const response = await page.request.get(`${API_BASE_URL}/api/ai/status`, { headers: authSession.headers });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload).toHaveProperty("effective_status");
  expect(payload).toHaveProperty("effective_provider");

  await page.goto("/");
  await expect(page.getByTestId("topbar-ai-status")).toHaveAttribute("title", /AI:/);
});
