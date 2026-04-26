/**
 * MCP tool handlers for BSELA. Pure functions (client + args -> result)
 * so they can be unit-tested without the SDK transport.
 *
 * Per ADR 0006 the first MCP surface is read-only and maps 1:1 to
 * existing `bsela` CLI commands:
 *   * bsela_route   -> bsela route <task> --json
 *   * bsela_audit   -> bsela audit --stdout [--window-days N]
 *   * bsela_status  -> bsela status
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import { BselaClientError, type BselaClient } from "./bsela-client.js";

export type ToolTextResult = CallToolResult;

export const routeInputSchema = {
  task: z.string().min(1, "task must be a non-empty string"),
} as const;

export const auditInputSchema = {
  window_days: z.number().int().positive().max(365).optional(),
} as const;

export const statusInputSchema = {} as const;

function errorResult(err: unknown, fallback: string): ToolTextResult {
  const message =
    err instanceof BselaClientError
      ? `${err.message}${err.stderr ? `\n\nstderr:\n${err.stderr}` : ""}`
      : err instanceof Error
        ? err.message
        : fallback;
  return {
    content: [{ type: "text", text: message }],
    isError: true,
  };
}

export async function handleRoute(
  client: BselaClient,
  args: { task: string },
): Promise<ToolTextResult> {
  try {
    const decision = await client.route(args.task);
    return {
      content: [{ type: "text", text: JSON.stringify(decision, null, 2) }],
      structuredContent: decision as unknown as Record<string, unknown>,
    };
  } catch (err) {
    return errorResult(err, "bsela route failed");
  }
}

export async function handleAudit(
  client: BselaClient,
  args: { window_days?: number | undefined },
): Promise<ToolTextResult> {
  try {
    const markdown = await client.audit(
      args.window_days === undefined ? {} : { windowDays: args.window_days },
    );
    return {
      content: [{ type: "text", text: markdown }],
    };
  } catch (err) {
    return errorResult(err, "bsela audit failed");
  }
}

export async function handleStatus(client: BselaClient): Promise<ToolTextResult> {
  try {
    const text = await client.status();
    return {
      content: [{ type: "text", text }],
    };
  } catch (err) {
    return errorResult(err, "bsela status failed");
  }
}

export const toolDefinitions = {
  bsela_route: {
    title: "BSELA route",
    description:
      "Classify a free-form task into one of BSELA's model roles (planner, builder, reviewer, judge, distiller, researcher, auditor, debugger, memory_updater) and return the recommended model.",
    inputSchema: routeInputSchema,
  },
  bsela_audit: {
    title: "BSELA audit",
    description:
      "Run the BSELA weekly auditor and return the markdown digest. Reports cost burn, drift, and ADR hygiene over the last 30 days by default.",
    inputSchema: auditInputSchema,
  },
  bsela_status: {
    title: "BSELA status",
    description:
      "Return BSELA store counts (sessions, errors, lessons, pending lessons) and the bsela home path.",
    inputSchema: statusInputSchema,
  },
} as const;

export type ToolName = keyof typeof toolDefinitions;
