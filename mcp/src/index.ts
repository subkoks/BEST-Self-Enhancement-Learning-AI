/**
 * Public entry point for the BSELA MCP package.
 *
 * The MCP server itself is added in a follow-up commit once the
 * tool schema stabilises; this file currently exports only the CLI
 * client so downstream packages can exercise the shell-out path.
 */

export {
  BselaClient,
  BselaClientError,
  type BselaClientOptions,
  type RouteDecision,
  type TaskClass,
} from "./bsela-client.js";
