/**
 * Thin TypeScript wrapper around the installed `bsela` Python CLI.
 *
 * The MCP server shells out to `bsela` via `node:child_process` and
 * parses JSON / text on stdout. The Python core remains the single
 * source of truth; this client exists only to adapt its CLI to the
 * MCP transport without duplicating router / auditor / store logic.
 *
 * Requirements:
 *   * `bsela` must be on `PATH` (same contract the Claude Code Stop
 *     hook already relies on and `bsela doctor` validates).
 *   * Python / bsela errors surface as rejected promises with stderr
 *     in the error message.
 */

import { spawn } from "node:child_process";

export type TaskClass =
  | "judge"
  | "distiller"
  | "planner"
  | "builder"
  | "reviewer"
  | "researcher"
  | "auditor"
  | "debugger"
  | "memory_updater";

export interface RouteDecision {
  task_class: TaskClass;
  model: string;
  confidence: number;
  reason: string;
  matched_keywords: Array<string>;
}

export interface BselaClientOptions {
  binary?: string;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
}

export class BselaClientError extends Error {
  readonly exitCode: number | null;
  readonly stderr: string;

  constructor(message: string, exitCode: number | null, stderr: string) {
    super(message);
    this.name = "BselaClientError";
    this.exitCode = exitCode;
    this.stderr = stderr;
  }
}

const DEFAULT_TIMEOUT_MS = 30_000;

interface RunResult {
  stdout: string;
  stderr: string;
  exitCode: number | null;
}

function runBsela(
  args: Array<string>,
  options: BselaClientOptions | undefined,
): Promise<RunResult> {
  const binary = options?.binary ?? "bsela";
  const timeout = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, {
      cwd: options?.cwd,
      env: options?.env ?? process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(
        new BselaClientError(`bsela ${args.join(" ")} timed out after ${timeout}ms`, null, stderr),
      );
    }, timeout);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new BselaClientError(`failed to spawn ${binary}: ${err.message}`, null, stderr));
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, exitCode: code });
    });
  });
}

function assertSuccess(
  args: Array<string>,
  result: RunResult,
  allowExitCodes: ReadonlyArray<number> = [0],
): void {
  if (result.exitCode === null || !allowExitCodes.includes(result.exitCode)) {
    throw new BselaClientError(
      `bsela ${args.join(" ")} exited ${result.exitCode ?? "null"}`,
      result.exitCode,
      result.stderr,
    );
  }
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new BselaClientError(`bsela output was not valid JSON: ${message}`, 0, raw.slice(0, 200));
  }
}

function isRouteDecision(value: unknown): value is RouteDecision {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.task_class === "string" &&
    typeof v.model === "string" &&
    typeof v.confidence === "number" &&
    typeof v.reason === "string" &&
    Array.isArray(v.matched_keywords) &&
    v.matched_keywords.every((k) => typeof k === "string")
  );
}

export class BselaClient {
  private readonly options: BselaClientOptions;

  constructor(options: BselaClientOptions = {}) {
    this.options = options;
  }

  async route(task: string): Promise<RouteDecision> {
    const args = ["route", task, "--json"];
    const result = await runBsela(args, this.options);
    assertSuccess(args, result);
    const parsed = parseJson(result.stdout.trim());
    if (!isRouteDecision(parsed)) {
      throw new BselaClientError(
        "bsela route returned an unexpected payload shape",
        result.exitCode,
        JSON.stringify(parsed).slice(0, 200),
      );
    }
    return parsed;
  }

  async audit(options: { windowDays?: number } = {}): Promise<string> {
    const args = ["audit", "--stdout"];
    if (options.windowDays !== undefined) {
      args.push("--window-days", String(options.windowDays));
    }
    const result = await runBsela(args, this.options);
    // `bsela audit` exits 1 when any alert is active — that is a
    // signal, not a failure. Accept both exit codes.
    assertSuccess(args, result, [0, 1]);
    return result.stdout;
  }

  async status(): Promise<string> {
    const args = ["status"];
    const result = await runBsela(args, this.options);
    assertSuccess(args, result);
    return result.stdout;
  }
}
