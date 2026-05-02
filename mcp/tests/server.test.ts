/**
 * End-to-end test for the MCP server. Uses InMemoryTransport so the
 * test does not spawn a real subprocess; the BselaClient is replaced
 * with a stub so no Python CLI runs either.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { describe, expect, it, vi } from "vitest";

import { BselaClient, createServer, type RouteDecision, type StatusPayload } from "../src/index.js";

function stubClient(overrides: Partial<BselaClient>): BselaClient {
  return Object.assign(Object.create(BselaClient.prototype), overrides) as BselaClient;
}

async function connectClient(client: BselaClient): Promise<Client> {
  const server = createServer({ client });
  const [serverTransport, clientTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);

  const mcpClient = new Client({ name: "bsela-mcp-test", version: "0.0.0" });
  await mcpClient.connect(clientTransport);
  return mcpClient;
}

describe("createServer", () => {
  it("advertises all four BSELA tools via list_tools", async () => {
    const decision: RouteDecision = {
      task_class: "planner",
      model: "claude-opus-4-7",
      confidence: 1,
      reason: "matched keyword",
      matched_keywords: ["plan"],
    };
    const statusPayload: StatusPayload = {
      sessions: 0,
      sessions_quarantined: 0,
      errors: 0,
      lessons: 0,
      lessons_pending: 0,
      lessons_proposed: 0,
      replay_records: 0,
      bsela_home: "/tmp/.bsela",
    };
    const client = stubClient({
      route: vi.fn().mockResolvedValue(decision),
      auditData: vi.fn().mockResolvedValue({
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
      }),
      status: vi.fn().mockResolvedValue(statusPayload),
      lessons: vi.fn().mockResolvedValue([]),
    });

    const mcp = await connectClient(client);
    try {
      const { tools } = await mcp.listTools();
      const names = tools.map((t) => t.name).sort();
      expect(names).toEqual(["bsela_audit", "bsela_lessons", "bsela_route", "bsela_status"]);
    } finally {
      await mcp.close();
    }
  });

  it("dispatches bsela_route to the underlying BselaClient", async () => {
    const decision: RouteDecision = {
      task_class: "builder",
      model: "claude-sonnet-4-6",
      confidence: 1,
      reason: "matched keyword",
      matched_keywords: ["refactor"],
    };
    const route = vi.fn().mockResolvedValue(decision);
    const client = stubClient({
      route,
      audit: vi.fn(),
      status: vi.fn(),
    });

    const mcp = await connectClient(client);
    try {
      const result = await mcp.callTool({
        name: "bsela_route",
        arguments: { task: "refactor the updater module" },
      });
      expect(route).toHaveBeenCalledWith("refactor the updater module");
      expect(result.isError).toBeFalsy();
      const content = result.content as Array<{ type: string; text: string }>;
      expect(JSON.parse(content[0]!.text)).toEqual(decision);
    } finally {
      await mcp.close();
    }
  });

  it("dispatches bsela_audit with the requested window_days", async () => {
    const auditData = vi.fn().mockResolvedValue({
      generated_at: "2026-05-02T00:00:00+00:00",
      window_days: 7,
      window_start: "2026-04-25T00:00:00+00:00",
      window_end: "2026-05-02T00:00:00+00:00",
      sessions: { total: 1, quarantined: 0, quarantine_rate: 0 },
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
    const client = stubClient({
      route: vi.fn(),
      auditData,
      status: vi.fn(),
    });

    const mcp = await connectClient(client);
    try {
      const result = await mcp.callTool({
        name: "bsela_audit",
        arguments: { window_days: 7 },
      });
      expect(auditData).toHaveBeenCalledWith({ windowDays: 7 });
      const content = result.content as Array<{ type: string; text: string }>;
      expect(JSON.parse(content[0]!.text)).toMatchObject({ window_days: 7 });
    } finally {
      await mcp.close();
    }
  });

  it("dispatches bsela_lessons with status + limit filters", async () => {
    const lessons = vi.fn().mockResolvedValue([
      {
        id: "lesson-1",
        status: "approved",
        scope: "project",
        confidence: 0.95,
        rule: "Use typed audit payload",
        why: "Avoid shape drift",
        how_to_apply: "consume structuredContent",
        hit_count: 2,
        created_at: "2026-05-02T00:00:00+00:00",
      },
    ]);
    const client = stubClient({
      route: vi.fn(),
      auditData: vi.fn(),
      status: vi.fn(),
      lessons,
    });

    const mcp = await connectClient(client);
    try {
      const result = await mcp.callTool({
        name: "bsela_lessons",
        arguments: { status: "approved", limit: 1 },
      });
      expect(lessons).toHaveBeenCalledWith({ status: "approved", limit: 1, trackHits: true });
      const content = result.content as Array<{ type: string; text: string }>;
      const payload = JSON.parse(content[0]!.text) as Array<{ id: string }>;
      expect(payload[0]!.id).toBe("lesson-1");
    } finally {
      await mcp.close();
    }
  });
});
