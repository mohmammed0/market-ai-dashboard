import { expect } from "@playwright/test";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8010";
const PLAYWRIGHT_AUTH_USERNAME = process.env.PLAYWRIGHT_AUTH_USERNAME || "admin";
const PLAYWRIGHT_AUTH_PASSWORD = process.env.PLAYWRIGHT_AUTH_PASSWORD || "";

let authSessionPromise;

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export async function resolveAuthSession(request) {
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

export async function establishAuthState(page, request) {
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
