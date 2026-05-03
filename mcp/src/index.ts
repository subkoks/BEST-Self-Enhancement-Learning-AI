/**
 * Public entry point for the BSELA MCP package.
 *
 * Re-exports the CLI client and the MCP server factory. The runnable
 * MCP binary lives at `dist/server.js` (registered as `bsela-mcp`
 * via package.json `bin`).
 */

export {
  type AuditPayload,
  BselaClient,
  BselaClientError,
  type BselaClientOptions,
  type ErrorItem,
  isErrorItem,
  isLessonItem,
  isSessionItem,
  type LessonItem,
  type RouteDecision,
  type SessionItem,
  type StatusPayload,
  type TaskClass,
} from "./bsela-client.js";

export { createServer, main, type CreateServerOptions } from "./server.js";

export {
  handleAudit,
  handleErrors,
  handleLessons,
  handleRoute,
  handleSessions,
  handleStatus,
  toolDefinitions,
  type ToolName,
  type ToolTextResult,
} from "./server-tools.js";
