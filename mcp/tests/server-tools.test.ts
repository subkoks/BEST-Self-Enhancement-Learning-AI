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
  handleErrors,
  handleLessons,
  handleRoute,
  handleSessions,
  handleStatus,
  toolDefinitions,
  type ErrorItem,
  type LessonItem,
  type RouteDecision,
  type SessionItem,
  type StatusPayload,
} from "../src/index.js";

function stubClient(overrides: Partial<BselaClient> = {}): BselaClient {
  return Object.assign(Object.create(BselaClient.prototype), overrides) as BselaClient;
}

function sortedKeys(value: Record<string, unknown>): Array<string> {
  return Object.keys(value).sort();
}

describe("toolDefinitions", () => {
  it("declares all six tools including bsela_errors", () => {
    expect(Object.keys(toolDefinitions).sort()).toEqual([
      "bsela_audit",
      "bsela_errors",
      "bsela_lessons",
      "bsela_route",
      "bsela_sessions",
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
    const auditData = vi.fn().mockResolvedValue({
      generated_at: "2026-05-02T00:00:00+00:00",
      window_days: 14,
      window_start: "2026-04-18T00:00:00+00:00",
      window_end: "2026-05-02T00:00:00+00:00",
      sessions: { total: 0, quarantined: 0, quarantine_rate: 0 },
      errors_total: 0,
      cost: {
        total_usd: 0,
        prorated_monthly_usd: 0,
        monthly_budget_usd: 50,
        burn_ratio: 0,
        over_budget: false,
      },
      drift: {
        lessons_total: 0,
        lessons_stale: 0,
        threshold: 0.25,
        drift_fraction: 0,
        over_threshold: false,
      },
      replay_drift: {
        sessions_replayed: 0,
        sessions_with_drift: 0,
        threshold: 0.25,
        drift_rate: 0,
        over_threshold: false,
      },
      adrs: { total: 0, missing_status: [], scanned: false },
      alerts: [],
    });
    const client = stubClient({ auditData });

    const result = await handleAudit(client, { window_days: 14 });

    expect(auditData).toHaveBeenCalledWith({ windowDays: 14 });
    expect(result.isError).toBeUndefined();
    expect(result.structuredContent).toMatchObject({ window_days: 14 });
  });

  it("omits windowDays when window_days is undefined", async () => {
    const auditData = vi.fn().mockResolvedValue({
      generated_at: "2026-05-02T00:00:00+00:00",
      window_days: 30,
      window_start: "2026-04-02T00:00:00+00:00",
      window_end: "2026-05-02T00:00:00+00:00",
      sessions: { total: 0, quarantined: 0, quarantine_rate: 0 },
      errors_total: 0,
      cost: {
        total_usd: 0,
        prorated_monthly_usd: 0,
        monthly_budget_usd: 50,
        burn_ratio: 0,
        over_budget: false,
      },
      drift: {
        lessons_total: 0,
        lessons_stale: 0,
        threshold: 0.25,
        drift_fraction: 0,
        over_threshold: false,
      },
      replay_drift: {
        sessions_replayed: 0,
        sessions_with_drift: 0,
        threshold: 0.25,
        drift_rate: 0,
        over_threshold: false,
      },
      adrs: { total: 0, missing_status: [], scanned: false },
      alerts: [],
    });
    const client = stubClient({ auditData });

    await handleAudit(client, {});

    expect(auditData).toHaveBeenCalledWith({});
  });

  it("returns an error result when the client throws", async () => {
    const auditData = vi.fn().mockRejectedValue(new Error("disk full"));
    const client = stubClient({ auditData });

    const result = await handleAudit(client, {});

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("disk full");
  });
});

describe("handleStatus", () => {
  it("returns structured JSON payload with counts and bsela_home", async () => {
    const payload: StatusPayload = {
      sessions: 3,
      sessions_quarantined: 1,
      errors: 5,
      lessons: 2,
      lessons_pending: 1,
      lessons_proposed: 0,
      replay_records: 4,
      bsela_home: "/tmp/.bsela",
    };
    const status = vi.fn().mockResolvedValue(payload);
    const client = stubClient({ status });

    const result = await handleStatus(client);

    expect(status).toHaveBeenCalledWith();
    expect(result.isError).toBeUndefined();
    const text = (result.content[0] as { text: string }).text;
    expect(JSON.parse(text)).toEqual(payload);
    expect(result.structuredContent).toEqual(payload);
  });

  it("returns an error result when the client throws", async () => {
    const status = vi.fn().mockRejectedValue(new Error("nope"));
    const client = stubClient({ status });

    const result = await handleStatus(client);

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("nope");
  });
});

describe("handleLessons", () => {
  const sampleLesson: LessonItem = {
    id: "abc123",
    status: "pending",
    scope: "project",
    confidence: 0.9,
    rule: "Stop retrying Read on ENOENT after first miss",
    why: "Loop detector flagged repeated reads",
    how_to_apply: "Change strategy on second ENOENT",
    hit_count: 0,
    created_at: "2026-04-29T10:00:00+00:00",
  };

  it("returns lessons as JSON text", async () => {
    const lessons = vi.fn().mockResolvedValue([sampleLesson]);
    const client = stubClient({ lessons });

    const result = await handleLessons(client, {});

    expect(lessons).toHaveBeenCalledWith({});
    expect(result.isError).toBeUndefined();
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toHaveLength(1);
    expect((parsed[0] as LessonItem).id).toBe("abc123");
    expect(sortedKeys(parsed[0] as Record<string, unknown>)).toEqual([
      "confidence",
      "created_at",
      "hit_count",
      "how_to_apply",
      "id",
      "rule",
      "scope",
      "status",
      "why",
    ]);
    expect(result.structuredContent).toEqual({ lessons: [sampleLesson] });
  });

  it("returns empty lessons in both text and structured content", async () => {
    const lessons = vi.fn().mockResolvedValue([]);
    const client = stubClient({ lessons });

    const result = await handleLessons(client, {});

    expect(lessons).toHaveBeenCalledWith({});
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toEqual([]);
    expect(result.structuredContent).toEqual({ lessons: [] });
  });

  it("passes status filter through to the client", async () => {
    const lessons = vi.fn().mockResolvedValue([]);
    const client = stubClient({ lessons });

    await handleLessons(client, { status: "rejected" });

    expect(lessons).toHaveBeenCalledWith({ status: "rejected" });
  });

  it("passes limit through to the client", async () => {
    const lessons = vi.fn().mockResolvedValue([sampleLesson]);
    const client = stubClient({ lessons });

    await handleLessons(client, { limit: 5 });

    expect(lessons).toHaveBeenCalledWith({ limit: 5 });
  });

  it("passes status and limit together through to the client", async () => {
    const lessons = vi.fn().mockResolvedValue([]);
    const client = stubClient({ lessons });

    await handleLessons(client, { status: "approved", limit: 10 });

    expect(lessons).toHaveBeenCalledWith({
      status: "approved",
      limit: 10,
      trackHits: true,
    });
  });

  it("returns error result on client failure", async () => {
    const lessons = vi.fn().mockRejectedValue(new BselaClientError("cli failed", 1, "oops"));
    const client = stubClient({ lessons });

    const result = await handleLessons(client, {});

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("cli failed");
  });
});

describe("handleSessions", () => {
  const sampleSession: SessionItem = {
    id: "abc12345-0000-0000-0000-000000000000",
    status: "captured",
    source: "claude_code",
    turn_count: 10,
    tool_call_count: 5,
    ingested_at: "2026-05-01T12:00:00+00:00",
  };

  it("returns sessions as JSON text and structuredContent", async () => {
    const sessions = vi.fn().mockResolvedValue([sampleSession]);
    const client = stubClient({ sessions });

    const result = await handleSessions(client, {});

    expect(sessions).toHaveBeenCalledWith({});
    expect(result.isError).toBeUndefined();
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toHaveLength(1);
    expect((parsed[0] as SessionItem).id).toBe(sampleSession.id);
    expect(sortedKeys(parsed[0] as Record<string, unknown>)).toEqual([
      "id",
      "ingested_at",
      "source",
      "status",
      "tool_call_count",
      "turn_count",
    ]);
    expect(result.structuredContent).toEqual({ sessions: [sampleSession] });
  });

  it("returns empty sessions in both text and structured content", async () => {
    const sessions = vi.fn().mockResolvedValue([]);
    const client = stubClient({ sessions });

    const result = await handleSessions(client, {});

    expect(sessions).toHaveBeenCalledWith({});
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toEqual([]);
    expect(result.structuredContent).toEqual({ sessions: [] });
  });

  it("passes status filter through to the client", async () => {
    const sessions = vi.fn().mockResolvedValue([]);
    const client = stubClient({ sessions });

    await handleSessions(client, { status: "quarantined" });

    expect(sessions).toHaveBeenCalledWith({ status: "quarantined" });
  });

  it("passes limit through to the client", async () => {
    const sessions = vi.fn().mockResolvedValue([sampleSession]);
    const client = stubClient({ sessions });

    await handleSessions(client, { limit: 5 });

    expect(sessions).toHaveBeenCalledWith({ limit: 5 });
  });

  it("returns error result on client failure", async () => {
    const sessions = vi.fn().mockRejectedValue(new BselaClientError("cli failed", 1, "oops"));
    const client = stubClient({ sessions });

    const result = await handleSessions(client, {});

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("cli failed");
  });
});

describe("handleErrors", () => {
  const sampleError: ErrorItem = {
    id: "err-001",
    session_id: "sess-001",
    category: "correction",
    severity: "medium",
    line_number: 42,
    snippet: "user said stop",
    detected_at: "2026-05-02T10:00:00+00:00",
  };

  it("returns error items as JSON text and structuredContent.errors", async () => {
    const errors = vi.fn().mockResolvedValue([sampleError]);
    const client = stubClient({ errors });

    const result = await handleErrors(client, {});

    expect(result.isError).toBeFalsy();
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toEqual([sampleError]);
    expect(result.structuredContent).toEqual({ errors: [sampleError] });
  });

  it("returns empty array when no errors exist", async () => {
    const errors = vi.fn().mockResolvedValue([]);
    const client = stubClient({ errors });

    const result = await handleErrors(client, {});

    expect(result.isError).toBeFalsy();
    expect(errors).toHaveBeenCalledWith({});
    const parsed = JSON.parse((result.content[0] as { text: string }).text) as unknown[];
    expect(parsed).toEqual([]);
    expect(result.structuredContent).toEqual({ errors: [] });
  });

  it("passes session_id filter to the client as sessionId", async () => {
    const errors = vi.fn().mockResolvedValue([]);
    const client = stubClient({ errors });

    await handleErrors(client, { session_id: "sess-abc" });

    expect(errors).toHaveBeenCalledWith({ sessionId: "sess-abc" });
  });

  it("passes limit through to the client", async () => {
    const errors = vi.fn().mockResolvedValue([sampleError]);
    const client = stubClient({ errors });

    await handleErrors(client, { limit: 10 });

    expect(errors).toHaveBeenCalledWith({ limit: 10 });
  });

  it("returns error result on client failure", async () => {
    const errors = vi.fn().mockRejectedValue(new BselaClientError("cli failed", 1, "stderr"));
    const client = stubClient({ errors });

    const result = await handleErrors(client, {});

    expect(result.isError).toBe(true);
    expect((result.content[0] as { text: string }).text).toContain("cli failed");
  });
});
