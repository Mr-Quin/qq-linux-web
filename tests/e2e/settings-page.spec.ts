import { readFileSync, statSync, utimesSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { STATE, WEBHOOK } from "../../playwright.config";

const SETTINGS = `${STATE}/settings.json`;
const SECRET_URL = "https://discord.com/api/webhooks/1234/supersecrettoken";
const MOCK_URL = `json://${WEBHOOK.replace("http://", "")}/`;

type Settings = {
  destinations?: string[];
  forward?: { chats?: string[]; keywords?: string[] };
  ignore?: { chats?: string[]; keywords?: string[] };
};

function writeSettings(settings: Settings) {
  const before = statSync(SETTINGS, { throwIfNoEntry: false })?.mtimeMs ?? 0;
  writeFileSync(SETTINGS, JSON.stringify(settings));
  // The server spots changes by mtime; make sure two writes in one tick still differ.
  const t = new Date(Math.max(Date.now(), before + 1000));
  utimesSync(SETTINGS, t, t);
}

function savedSettings(): Required<Settings> {
  return JSON.parse(readFileSync(SETTINGS, "utf8"));
}

async function posts(): Promise<{ body: { title: string; message: string } }[]> {
  return (await fetch(`${WEBHOOK}/posts`)).json();
}

test.beforeEach(async ({ page }) => {
  await fetch(`${WEBHOOK}/posts`, { method: "DELETE" });
  writeSettings({
    destinations: [SECRET_URL],
    forward: { chats: ["Family"], keywords: ["@我"] },
    ignore: { chats: ["Noisy Group"], keywords: [] },
  });
  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Saved settings loaded.");
});

test("shows saved destinations without their secrets", async ({ page }) => {
  const dests = page.locator("#destinations");
  await expect(dests).toContainText("Discord");
  await expect(page.locator("body")).not.toContainText("supersecrettoken");
});

test("lists recent chats with their rules", async ({ page }) => {
  const rows = page.locator("#chats tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Noisy Group" }).locator("select")).toHaveValue("ignore");
  await expect(rows.filter({ hasText: "Family" }).locator("select")).toHaveValue("forward");
});

test("saves a URL that was typed but never added", async ({ page }) => {
  await page.locator("#new-url").fill(MOCK_URL);
  await expect(page.locator("#status")).toHaveText("Unsaved changes.");
  await page.locator("#save").click();
  await expect(page.locator("#status")).toHaveText(/^Saved\./);
  await expect(page.locator("#new-url")).toHaveValue("");
  expect(savedSettings().destinations).toEqual([SECRET_URL, MOCK_URL]);
});

test("tests a new URL before it is added", async ({ page }) => {
  await page.locator("#new-url").fill(MOCK_URL);
  await page.locator("#test-new").click();
  await expect(page.locator("#test-new")).toHaveText("Sent");
  expect((await posts()).map((p) => p.body.message)).toEqual(["Test message from the QQ settings page."]);
});

test("removes a destination", async ({ page }) => {
  await page.locator("#destinations button", { hasText: "Remove" }).click();
  await expect(page.locator("#destinations")).toContainText("No destinations");
  await page.locator("#save").click();
  await expect(page.locator("#status")).toHaveText(/^Saved\./);
  expect(savedSettings().destinations).toEqual([]);
});

test("changes chat rules and keywords", async ({ page }) => {
  await page.locator("#chats tr", { hasText: "Noisy Group" }).locator("select").selectOption("default");
  await page.locator("#new-chat").fill("Work");
  await page.locator("#add-chat").click();
  await page.locator("#chats tr", { hasText: "Work" }).locator("select").selectOption("ignore");
  await page.locator("#ignore-keywords").fill("广告\n广告\n  ");
  await page.locator("#all-chats").check();
  await page.locator("#save").click();
  await expect(page.locator("#status")).toHaveText(/^Saved\./);

  const saved = savedSettings();
  expect(saved.forward.chats.sort()).toEqual(["*", "Family"]);
  expect(saved.ignore).toEqual({ chats: ["Work"], keywords: ["广告"] });
  expect(saved.destinations).toEqual([SECRET_URL]);
});

test("refuses to overwrite settings changed elsewhere", async ({ page }) => {
  writeSettings({ forward: { chats: ["edited by hand"] } });
  await page.locator("#all-chats").check();
  await page.locator("#save").click();
  await expect(page.locator("#status")).toContainText("Not saved: the settings changed");
  expect(savedSettings().forward.chats).toEqual(["edited by hand"]);

  await page.locator("#revert").click();
  await expect(page.locator("#chats tr", { hasText: "edited by hand" })).toBeVisible();
});

test("tries unsaved rules", async ({ page }) => {
  await page.locator("#forward-keywords").fill("");
  await page.locator("#try-chat").fill("Noisy Group");
  await page.locator("#try-text").fill("[有人@我]");
  await page.locator("#try").click();
  await expect(page.locator("#try-result")).toHaveText("Would be dropped: ignored chat");
});

test("shows a bad URL as an error instead of saving", async ({ page }) => {
  await page.locator("#new-url").fill("nonsense");
  await page.locator("#save").click();
  await expect(page.locator("#status")).toContainText("Not saved: a new destination is not a valid Apprise URL");
  expect(savedSettings().destinations).toEqual([SECRET_URL]);
});
