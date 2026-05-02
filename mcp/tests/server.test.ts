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
      audit: vi.fn().mockResolvedValue("# BSELA Weekly Audit\n"),
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
    const audit = vi.fn().mockResolvedValue("# BSELA Weekly Audit\n## Alerts\nnone\n");
    const client = stubClient({
      route: vi.fn(),
      audit,
      status: vi.fn(),
    });

    const mcp = await connectClient(client);
    try {
      const result = await mcp.callTool({
        name: "bsela_audit",
        arguments: { window_days: 7 },
      });
      expect(audit).toHaveBeenCalledWith({ windowDays: 7 });
      const content = result.content as Array<{ type: string; text: string }>;
      expect(content[0]!.text).toContain("BSELA Weekly Audit");
    } finally {
      await mcp.close();
    }
  });
});
