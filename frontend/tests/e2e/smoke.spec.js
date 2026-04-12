import { test, expect } from "@playwright/test";

test("Analyze page loads", async ({ page }) => {
  await page.goto("/analyze");
  await expect(page.getByRole("heading", { name: "Analysis Result" })).toBeVisible();
});

test("Dashboard page loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Platform Readiness" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Readiness Cards" })).toBeVisible();
});

test("Scan page loads", async ({ page }) => {
  await page.goto("/scan");
  await expect(page.getByRole("heading", { name: "Ranked Scan Results" })).toBeVisible();
});

test("Ranking page loads", async ({ page }) => {
  await page.goto("/ranking");
  await expect(page.getByRole("heading", { name: "Top Long Candidates Today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top Short Candidates Today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Overall Ranked Candidates" })).toBeVisible();
});

test("Backtest and Settings pages load", async ({ page }) => {
  await page.goto("/backtest");
  await expect(page.getByRole("heading", { name: "Backtest Summary" })).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Runtime Info" })).toBeVisible();
});

test("Model Lab and Live Market pages load", async ({ page }) => {
  await page.goto("/model-lab");
  await expect(page.getByRole("heading", { name: "Training Summary" })).toBeVisible();

  await page.goto("/ai-news");
  await expect(page.getByRole("heading", { name: "Structured Analysis" })).toBeVisible();

  await page.goto("/live-market");
  await expect(page.getByRole("heading", { name: "Market Overview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Universe Table" })).toBeVisible();
});

test("Paper Trading page loads", async ({ page }) => {
  await page.goto("/paper-trading");
  await expect(page.getByRole("heading", { name: "Paper Portfolio" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent Alerts" })).toBeVisible();
});

test("Risk and Automation pages load", async ({ page }) => {
  await page.goto("/risk");
  await expect(page.getByRole("heading", { name: "Risk Limits" })).toBeVisible();

  await page.goto("/broker");
  await expect(page.getByRole("heading", { name: "Broker Connection" })).toBeVisible();

  await page.goto("/automation");
  await expect(page.getByRole("heading", { name: "Automation Status" })).toBeVisible();
});
