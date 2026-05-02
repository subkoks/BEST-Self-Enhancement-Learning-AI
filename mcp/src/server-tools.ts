/**
 * MCP tool handlers for BSELA. Pure functions (client + args -> result)
 * so they can be unit-tested without the SDK transport.
 *
 * Per ADR 0006 the first MCP surface is read-only and maps 1:1 to
 * existing `bsela` CLI commands:
 *   * bsela_route   -> bsela route <task> --json
 *   * bsela_audit   -> bsela audit --json [--window-days N]
 *   * bsela_status  -> bsela status
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import {
  BselaClientError,
  type AuditPayload,
  type BselaClient,
  type LessonItem,
  type SessionItem,
  type StatusPayload,
} from "./bsela-client.js";

export type ToolTextResult = CallToolResult;

export const routeInputSchema = {
  task: z.string().min(1, "task must be a non-empty string"),
} as const;

export const auditInputSchema = {
  window_days: z.number().int().positive().max(365).optional(),
} as const;

export const statusInputSchema = {} as const;

export const lessonsInputSchema = {
  status: z
    .enum(["pending", "proposed", "rejected", "approved", "applied", "rolled_back"])
    .optional(),
  limit: z.number().int().positive().max(200).optional(),
} as const;

export const sessionsInputSchema = {
  status: z.enum(["captured", "quarantined"]).optional(),
  limit: z.number().int().positive().max(200).optional(),
} as const;

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
    const payload: AuditPayload = await client.auditData(
      args.window_days === undefined ? {} : { windowDays: args.window_days },
    );
    return {
      content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
      structuredContent: payload as unknown as Record<string, unknown>,
    };
  } catch (err) {
    return errorResult(err, "bsela audit failed");
  }
}

export async function handleStatus(client: BselaClient): Promise<ToolTextResult> {
  try {
    const payload: StatusPayload = await client.status();
    return {
      content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
      structuredContent: payload as unknown as Record<string, unknown>,
    };
  } catch (err) {
    return errorResult(err, "bsela status failed");
  }
}

export async function handleLessons(
  client: BselaClient,
  args: { status?: string | undefined; limit?: number | undefined },
): Promise<ToolTextResult> {
  try {
    const opts: { status?: string; limit?: number; trackHits?: boolean } = {};
    if (args.status !== undefined) opts.status = args.status;
    if (args.limit !== undefined) opts.limit = args.limit;
    // Track hits when surfacing approved lessons to an editor so usage analytics work.
    if (args.status === "approved" || args.status === "applied") opts.trackHits = true;
    const items: Array<LessonItem> = await client.lessons(opts);
    return {
      content: [{ type: "text", text: JSON.stringify(items, null, 2) }],
      structuredContent: { lessons: items } as unknown as Record<string, unknown>,
    };
  } catch (err) {
    return errorResult(err, "bsela review list failed");
  }
}

export async function handleSessions(
  client: BselaClient,
  args: { status?: string | undefined; limit?: number | undefined },
): Promise<ToolTextResult> {
  try {
    const opts: { status?: string; limit?: number } = {};
    if (args.status !== undefined) opts.status = args.status;
    if (args.limit !== undefined) opts.limit = args.limit;
    const items: Array<SessionItem> = await client.sessions(opts);
    return {
      content: [{ type: "text", text: JSON.stringify(items, null, 2) }],
      structuredContent: { sessions: items } as unknown as Record<string, unknown>,
    };
  } catch (err) {
    return errorResult(err, "bsela sessions list failed");
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
      "Run the BSELA weekly auditor and return a structured JSON digest. Reports cost burn, drift, replay drift, and ADR hygiene over the last 30 days by default.",
    inputSchema: auditInputSchema,
  },
  bsela_status: {
    title: "BSELA status",
    description:
      "Return BSELA store counts (sessions, errors, lessons, pending/proposed lessons, replay records) and the bsela home path.",
    inputSchema: statusInputSchema,
  },
  bsela_lessons: {
    title: "BSELA lessons",
    description:
      "Return stored BSELA lessons as a JSON array plus structuredContent.lessons. Optionally filter by status (pending|proposed|rejected|approved|applied|rolled_back) and cap results with limit. Each item includes id, status, scope, confidence, rule, why, how_to_apply, hit_count, and created_at.",
    inputSchema: lessonsInputSchema,
  },
  bsela_sessions: {
    title: "BSELA sessions",
    description:
      "Return captured BSELA sessions as a JSON array plus structuredContent.sessions. Optionally filter by status (captured|quarantined) and cap results with limit. Each item includes id, status, source, turn_count, tool_call_count, and ingested_at.",
    inputSchema: sessionsInputSchema,
  },
} as const;

export type ToolName = keyof typeof toolDefinitions;
