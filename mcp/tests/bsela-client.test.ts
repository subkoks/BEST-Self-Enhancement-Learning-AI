import { homedir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { BselaClient, BselaClientError } from "../src/index.js";

/**
 * These are integration tests: they shell out to the `bsela`
 * Python CLI that ships with this repo. `bsela` must be on PATH
 * and `.venv` must be initialised (`uv sync` + `uv tool install -e .`).
 *
 * We prepend `~/.local/bin` to PATH so the uv-installed binary (which
 * tracks the current worktree) wins over pyenv shims, which may point
 * to an older install from the main branch.
 */
function makeClient(): BselaClient {
  const localBin = join(homedir(), ".local", "bin");
  const path = `${localBin}:${process.env["PATH"] ?? ""}`;
  return new BselaClient({ env: { ...process.env, PATH: path } });
}

describe("BselaClient.route", () => {
  const client = makeClient();

  it("routes a planning task to the planner role", async () => {
    const decision = await client.route("plan the migration to P6");
    expect(decision.task_class).toBe("planner");
    expect(decision.confidence).toBe(1);
    expect(decision.model).toMatch(/opus/);
    expect(decision.matched_keywords).toContain("plan");
  });

  it("routes a refactor task to the builder role", async () => {
    const decision = await client.route("refactor the updater module");
    expect(decision.task_class).toBe("builder");
    expect(decision.confidence).toBe(1);
  });

  it("falls back to the default role for whitespace-only input", async () => {
    const decision = await client.route("   ");
    expect(decision.task_class).toBe("builder");
    expect(decision.confidence).toBe(0.5);
    expect(decision.matched_keywords).toEqual([]);
  });
});

describe("BselaClient.audit", () => {
  const client = makeClient();

  it("returns markdown starting with the audit header", async () => {
    const markdown = await client.audit({ windowDays: 30 });
    expect(markdown).toContain("# BSELA Weekly Audit");
    expect(markdown).toContain("## Alerts");
  });
});

describe("BselaClient.status", () => {
  const client = makeClient();

  it("returns a typed StatusPayload with numeric counts and bsela_home", async () => {
    const payload = await client.status();
    expect(typeof payload.sessions).toBe("number");
    expect(typeof payload.sessions_quarantined).toBe("number");
    expect(typeof payload.errors).toBe("number");
    expect(typeof payload.lessons).toBe("number");
    expect(typeof payload.lessons_pending).toBe("number");
    expect(typeof payload.replay_records).toBe("number");
    expect(typeof payload.bsela_home).toBe("string");
    expect(payload.bsela_home.length).toBeGreaterThan(0);
  });
});

describe("BselaClient error paths", () => {
  it("rejects when the binary is missing", async () => {
    const client = new BselaClient({ binary: "/nonexistent/bsela-does-not-exist" });
    await expect(client.route("plan")).rejects.toBeInstanceOf(BselaClientError);
  });
});
