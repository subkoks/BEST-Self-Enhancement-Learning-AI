import { describe, expect, it } from "vitest";

import { BselaClient, BselaClientError } from "../src/index.js";

/**
 * These are integration tests: they shell out to the `bsela`
 * Python CLI that ships with this repo. `bsela` must be on PATH
 * and `.venv` must be initialised (`uv sync` + `uv tool install -e .`).
 */
describe("BselaClient.route", () => {
  const client = new BselaClient();

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
  const client = new BselaClient();

  it("returns markdown starting with the audit header", async () => {
    const markdown = await client.audit({ windowDays: 30 });
    expect(markdown).toContain("# BSELA Weekly Audit");
    expect(markdown).toContain("## Alerts");
  });
});

describe("BselaClient.status", () => {
  const client = new BselaClient();

  it("prints the BSELA home and counts", async () => {
    const output = await client.status();
    expect(output).toMatch(/(BSELA home|no store)/);
  });
});

describe("BselaClient error paths", () => {
  it("rejects when the binary is missing", async () => {
    const client = new BselaClient({ binary: "/nonexistent/bsela-does-not-exist" });
    await expect(client.route("plan")).rejects.toBeInstanceOf(BselaClientError);
  });
});
