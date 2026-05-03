#!/usr/bin/env node
/**
 * BSELA MCP server entry point.
 *
 * Per ADR 0006 the server exposes read-only tools that shell out to
 * the `bsela` Python CLI. Current surface (six tools):
 *   * bsela_route(task)
 *   * bsela_audit(window_days?)
 *   * bsela_status()
 *   * bsela_lessons(status?, limit?)
 *   * bsela_sessions(status?, limit?)
 *   * bsela_errors(session_id?, limit?)
 *
 * Transport: stdio. Editors launch this binary as a subprocess and
 * speak JSON-RPC over stdin/stdout. `bsela` must be on PATH —
 * `bsela doctor` validates the same prerequisite the Stop hook
 * already relies on.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { BselaClient } from "./bsela-client.js";
import {
  handleAudit,
  handleErrors,
  handleLessons,
  handleRoute,
  handleSessions,
  handleStatus,
  toolDefinitions,
} from "./server-tools.js";

const SERVER_NAME = "bsela";
const SERVER_VERSION = "0.1.0";

export interface CreateServerOptions {
  client?: BselaClient;
  name?: string;
  version?: string;
}

export function createServer(options: CreateServerOptions = {}): McpServer {
  const client = options.client ?? new BselaClient();
  const server = new McpServer({
    name: options.name ?? SERVER_NAME,
    version: options.version ?? SERVER_VERSION,
  });

  server.registerTool(
    "bsela_route",
    {
      title: toolDefinitions.bsela_route.title,
      description: toolDefinitions.bsela_route.description,
      inputSchema: toolDefinitions.bsela_route.inputSchema,
    },
    async (args) => handleRoute(client, args),
  );

  server.registerTool(
    "bsela_audit",
    {
      title: toolDefinitions.bsela_audit.title,
      description: toolDefinitions.bsela_audit.description,
      inputSchema: toolDefinitions.bsela_audit.inputSchema,
    },
    async (args) => handleAudit(client, args),
  );

  server.registerTool(
    "bsela_status",
    {
      title: toolDefinitions.bsela_status.title,
      description: toolDefinitions.bsela_status.description,
      inputSchema: toolDefinitions.bsela_status.inputSchema,
    },
    async () => handleStatus(client),
  );

  server.registerTool(
    "bsela_lessons",
    {
      title: toolDefinitions.bsela_lessons.title,
      description: toolDefinitions.bsela_lessons.description,
      inputSchema: toolDefinitions.bsela_lessons.inputSchema,
    },
    async (args) => handleLessons(client, args),
  );

  server.registerTool(
    "bsela_sessions",
    {
      title: toolDefinitions.bsela_sessions.title,
      description: toolDefinitions.bsela_sessions.description,
      inputSchema: toolDefinitions.bsela_sessions.inputSchema,
    },
    async (args) => handleSessions(client, args),
  );

  server.registerTool(
    "bsela_errors",
    {
      title: toolDefinitions.bsela_errors.title,
      description: toolDefinitions.bsela_errors.description,
      inputSchema: toolDefinitions.bsela_errors.inputSchema,
    },
    async (args) => handleErrors(client, args),
  );

  return server;
}

export async function main(): Promise<void> {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

const isDirectInvocation =
  import.meta.url === `file://${process.argv[1]}` ||
  process.argv[1]?.endsWith("server.js") === true;

if (isDirectInvocation) {
  main().catch((err: unknown) => {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`bsela-mcp: fatal: ${message}\n`);
    process.exit(1);
  });
}
