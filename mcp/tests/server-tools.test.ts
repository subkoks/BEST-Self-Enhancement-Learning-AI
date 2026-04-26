/**
 * Unit tests for the MCP tool handlers. These do NOT shell out —
 * they drive `handle*` with a stubbed BselaClient so the assertions
 * stay fast and deterministic. The integration shape (real CLI)
 * is already covered by `bsela-client.test.ts`.
 */

import { describe, expect, it, vi } from "vitest";

import {
  BselaClient,
  BselaClientError,
  handleAudit,
  handleRoute,
  handleStatus,
  toolDefinitions,
  type RouteDecision,
} from "../src/index.js";

function stubClient(overrides: Partial<BselaClient> = {}): BselaClient {
  return Object.assign(Object.create(BselaClient.prototype), overrides) as BselaClient;
}

describe("toolDefinitions", () => {
  it("declares the three read-only tools mandated by ADR 0006", () => {
    expect(Object.keys(toolDefinitions).sort()).toEqual([
      "bsela_audit",
      "bsela_route",
      "bsela_status",
    ]);
  });

  it("requires a non-empty task on bsela_route", () => {
    const schema = toolDefinitions.bsela_route.inputSchema.task;
    expect(schema.safeParse("").success).toBe(false);
    expect(schema.safeParse("plan the migration").success).toBe(true);
  });

  it("rejects negative or zero window_days on bsela_audit", () => {
    const schema = toolDefinitions.bsela_audit.inputSchema.window_days;
    expect(schema.safeParse(0).success).toBe(false);
    expect(schema.safeParse(-7).success).toBe(false);
    expect(schema.safeParse(30).success).toBe(true);
    expect(schema.safeParse(undefined).success).toBe(true);
  });
});

describe("handleRoute", () => {
  it("returns the decision JSON as both text and structured content", async () => {
    const decision: RouteDecision = {
      task_class: "planner",
      model: "claude-opus-4-7",
      confidence: 1,
      reason: "matched keyword",
      matched_keywords: ["plan"],
    };
    const route = vi.fn().mockResolvedValue(decision);
    const client = stubClient({ route });

    const result = await handleRoute(client, { task: "plan the migration" });

    expect(route).toHaveBeenCalledWith("plan the migration");
    expect(result.isError).toBeUndefined();
    expect(result.content[0]).toMatchObject({ type: "text" });
    const text = (result.content[0] as { text: string }).text;
    expect(JSON.parse(text)).toEqual(decision);
    expect(result.structuredContent).toEqual(decision);
  });

  it("surfaces BselaClientError as an isError result with stderr", async () => {
    const route = vi.fn().mockRejectedValue(new BselaClientError("bsela route failed", 2, "boom"));
    const client = stubClient({ route });

    const result = await handleRoute(client, { task: "plan" });

    expect(result.isError).toBe(true);
    const text = (result.content[0] as { text: string }).text;
    expect(text).toContain("bsela route failed");
    expect(text).toContain("boom");
  });
});

describe("handleAudit", () => {
  it("passes window_days through to the client when provided", async () => {
    const audit = vi.fn().mockResolvedValue("# BSELA Weekly Audit\n");
    const client = stubClient({ audit });

    const result = await handleAudit(client, { window_days: 14 });

    expect(audit).toHaveBeenCalledWith({ windowDays: 14 });
    expect(result.isError).toBeUndefined();
    expect((result.content[0] as { text: string }).text).toContain("BSELA Weekly Audit");
  });

  it("omits windowDays when window_days is undefined", async () => {
    const audit = vi.fn().mockResolvedValue("# BSELA Weekly Audit\n");
    const client = stubClient({ audit });

    await handleAudit(client, {});

    expect(audit).toHaveBeenCalledWith({});
  });

  it("returns an error result when the client throws", async () => {
    const audit = vi.fn().mockRejectedValue(new Error("disk full"));
    const client = stubClient({ audit });

    const result = await handleAudit(client, {});

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("disk full");
  });
});

describe("handleStatus", () => {
  it("returns the raw status text", async () => {
    const status = vi.fn().mockResolvedValue("BSELA home: /tmp/.bsela\n");
    const client = stubClient({ status });

    const result = await handleStatus(client);

    expect(status).toHaveBeenCalledWith();
    expect(result.isError).toBeUndefined();
    expect((result.content[0] as { text: string }).text).toContain("BSELA home");
  });

  it("returns an error result when the client throws", async () => {
    const status = vi.fn().mockRejectedValue(new Error("nope"));
    const client = stubClient({ status });

    const result = await handleStatus(client);

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("nope");
  });
});
