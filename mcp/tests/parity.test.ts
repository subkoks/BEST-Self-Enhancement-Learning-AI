import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { describe, expect, it } from "vitest";

import { BselaClient, createServer, type AuditPayload, type LessonItem } from "../src/index.js";

/** Sorted keys for each CLI/MCP ``LessonItem`` row (keep aligned with Python contract tests). */
const EXPECTED_LESSON_ROW_KEYS: Array<string> = [
  "confidence",
  "created_at",
  "hit_count",
  "how_to_apply",
  "id",
  "rule",
  "scope",
  "status",
  "why",
];

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function makeClient(): BselaClient {
  const localBin = join(homedir(), ".local", "bin");
  const path = `${localBin}:${process.env["PATH"] ?? ""}`;
  return new BselaClient({ env: { ...process.env, PATH: path }, cwd: tmpdir() });
}

async function makeIsolatedClient(): Promise<{ client: BselaClient; home: string }> {
  const localBin = join(homedir(), ".local", "bin");
  const path = `${localBin}:${process.env["PATH"] ?? ""}`;
  const home = await mkdtemp(join(tmpdir(), "bsela-parity-empty-"));
  const client = new BselaClient({
    env: { ...process.env, PATH: path, BSELA_HOME: home },
    cwd: home,
  });
  return { client, home };
}

async function connectClient(client: BselaClient): Promise<Client> {
  const server = createServer({ client });
  const [serverTransport, clientTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);

  const mcpClient = new Client({ name: "bsela-mcp-parity-test", version: "0.0.0" });
  await mcpClient.connect(clientTransport);
  return mcpClient;
}

function parseTextJson<T>(result: unknown): T {
  const payload = result as { content: Array<{ type: string; text: string }> };
  return JSON.parse(payload.content[0]!.text) as T;
}

function sortedKeys(value: Record<string, unknown>): Array<string> {
  return Object.keys(value).sort();
}

function assertLessonRowKeyset(row: Record<string, unknown>): void {
  expect(sortedKeys(row)).toEqual(EXPECTED_LESSON_ROW_KEYS);
}

function seedOneLesson(home: string, pathEnv: string): void {
  const script = [
    "from bsela.memory.models import Lesson",
    "from bsela.memory.store import save_lesson",
    "save_lesson(Lesson(scope='project', rule='parity-seed', why='parity', how_to_apply='apply', confidence=0.9))",
  ].join("\n");
  execFileSync("uv", ["run", "python", "-c", script], {
    cwd: REPO_ROOT,
    env: { ...process.env, PATH: pathEnv, BSELA_HOME: home },
    stdio: "pipe",
  });
}

function normalizeAudit(
  payload: AuditPayload,
): Omit<AuditPayload, "generated_at" | "window_start" | "window_end"> {
  // Timestamps are generated at call time and can differ across direct vs MCP paths.
  const {
    generated_at: _generatedAt,
    window_start: _windowStart,
    window_end: _windowEnd,
    ...rest
  } = payload;
  return rest;
}

describe("CLI↔MCP parity", () => {
  it("keeps route/audit/status/lessons parity for direct and MCP paths", async () => {
    const client = makeClient();
    const mcp = await connectClient(client);
    try {
      const task = "plan the migration to P6";

      const directRoute = await client.route(task);
      const routeResult = await mcp.callTool({ name: "bsela_route", arguments: { task } });
      const mcpRoute = parseTextJson<typeof directRoute>(routeResult);
      expect(mcpRoute).toEqual(directRoute);
      expect(routeResult.structuredContent).toEqual(directRoute);

      const directAudit = await client.auditData({ windowDays: 30 });
      const auditResult = await mcp.callTool({
        name: "bsela_audit",
        arguments: { window_days: 30 },
      });
      const mcpAudit = parseTextJson<AuditPayload>(auditResult);
      expect(normalizeAudit(mcpAudit)).toEqual(normalizeAudit(directAudit));
      expect(normalizeAudit(auditResult.structuredContent as AuditPayload)).toEqual(
        normalizeAudit(directAudit),
      );

      const directStatus = await client.status();
      const statusResult = await mcp.callTool({ name: "bsela_status", arguments: {} });
      const mcpStatus = parseTextJson<typeof directStatus>(statusResult);
      expect(mcpStatus).toEqual(directStatus);
      expect(statusResult.structuredContent).toEqual(directStatus);

      const directLessons = await client.lessons({ limit: 3 });
      const lessonsResult = await mcp.callTool({ name: "bsela_lessons", arguments: { limit: 3 } });
      const mcpLessons = parseTextJson<typeof directLessons>(lessonsResult);
      expect(mcpLessons).toEqual(directLessons);
      expect(lessonsResult.structuredContent).toEqual({ lessons: directLessons });
      if (directLessons[0] !== undefined) {
        expect(sortedKeys(directLessons[0] as unknown as Record<string, unknown>)).toEqual([
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
      }
    } finally {
      await mcp.close();
    }
  });

  it("keeps empty-lessons parity for direct and MCP paths", async () => {
    const { client, home } = await makeIsolatedClient();
    const mcp = await connectClient(client);
    try {
      const directLessons = await client.lessons({ status: "pending", limit: 3 });
      expect(directLessons).toEqual([]);

      const lessonsResult = await mcp.callTool({
        name: "bsela_lessons",
        arguments: { status: "pending", limit: 3 },
      });
      const mcpLessons = parseTextJson<typeof directLessons>(lessonsResult);
      expect(mcpLessons).toEqual([]);
      expect(lessonsResult.structuredContent).toEqual({ lessons: [] });
    } finally {
      await mcp.close();
      await rm(home, { recursive: true, force: true });
    }
  });
});
