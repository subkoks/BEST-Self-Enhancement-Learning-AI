/**
 * Public entry point for the BSELA MCP package.
 *
 * Re-exports the CLI client and the MCP server factory. The runnable
 * MCP binary lives at `dist/server.js` (registered as `bsela-mcp`
 * via package.json `bin`).
 */

export {
  BselaClient,
  BselaClientError,
  type BselaClientOptions,
  type RouteDecision,
  type StatusPayload,
  type TaskClass,
} from "./bsela-client.js";

export { createServer, main, type CreateServerOptions } from "./server.js";

export {
  handleAudit,
  handleRoute,
  handleStatus,
  toolDefinitions,
  type ToolName,
  type ToolTextResult,
} from "./server-tools.js";
