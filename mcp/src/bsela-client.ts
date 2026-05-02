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
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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

export interface StatusPayload {
  sessions: number;
  sessions_quarantined: number;
  errors: number;
  lessons: number;
  lessons_pending: number;
  lessons_proposed: number;
  replay_records: number;
  bsela_home: string;
}

export interface AuditPayload {
  generated_at: string;
  window_days: number;
  window_start: string;
  window_end: string;
  sessions: {
    total: number;
    quarantined: number;
    quarantine_rate: number;
  };
  errors_total: number;
  cost: {
    total_usd: number;
    prorated_monthly_usd: number;
    monthly_budget_usd: number;
    burn_ratio: number;
    over_budget: boolean;
  };
  drift: {
    lessons_total: number;
    lessons_stale: number;
    threshold: number;
    drift_fraction: number;
    over_threshold: boolean;
  };
  replay_drift: {
    sessions_replayed: number;
    sessions_with_drift: number;
    threshold: number;
    drift_rate: number;
    over_threshold: boolean;
  };
  adrs: {
    total: number;
    missing_status: Array<string>;
    scanned: boolean;
  };
  alerts: Array<string>;
}

export interface LessonItem {
  id: string;
  status: string;
  scope: string;
  confidence: number;
  rule: string;
  why: string;
  how_to_apply: string;
  hit_count: number;
  created_at: string | null;
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
const MODULE_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_BSELA_CONFIG_DIR = resolve(MODULE_DIR, "..", "..", "config");

interface RunResult {
  stdout: string;
  stderr: string;
  exitCode: number | null;
}

function resolveEnv(env: NodeJS.ProcessEnv | undefined): NodeJS.ProcessEnv {
  const merged = { ...process.env, ...(env ?? {}) };
  if (!merged["BSELA_CONFIG_DIR"]) {
    merged["BSELA_CONFIG_DIR"] = DEFAULT_BSELA_CONFIG_DIR;
  }
  return merged;
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
      env: resolveEnv(options?.env),
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

function isStatusPayload(value: unknown): value is StatusPayload {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.sessions === "number" &&
    typeof v.sessions_quarantined === "number" &&
    typeof v.errors === "number" &&
    typeof v.lessons === "number" &&
    typeof v.lessons_pending === "number" &&
    typeof v.lessons_proposed === "number" &&
    typeof v.replay_records === "number" &&
    typeof v.bsela_home === "string"
  );
}

function isAuditPayload(value: unknown): value is AuditPayload {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const sessions = v.sessions;
  const cost = v.cost;
  const drift = v.drift;
  const replayDrift = v.replay_drift;
  const adrs = v.adrs;
  return (
    typeof v.generated_at === "string" &&
    typeof v.window_days === "number" &&
    typeof v.window_start === "string" &&
    typeof v.window_end === "string" &&
    typeof v.errors_total === "number" &&
    Array.isArray(v.alerts) &&
    v.alerts.every((item) => typeof item === "string") &&
    typeof sessions === "object" &&
    sessions !== null &&
    typeof (sessions as Record<string, unknown>).total === "number" &&
    typeof (sessions as Record<string, unknown>).quarantined === "number" &&
    typeof (sessions as Record<string, unknown>).quarantine_rate === "number" &&
    typeof cost === "object" &&
    cost !== null &&
    typeof (cost as Record<string, unknown>).total_usd === "number" &&
    typeof (cost as Record<string, unknown>).prorated_monthly_usd === "number" &&
    typeof (cost as Record<string, unknown>).monthly_budget_usd === "number" &&
    typeof (cost as Record<string, unknown>).burn_ratio === "number" &&
    typeof (cost as Record<string, unknown>).over_budget === "boolean" &&
    typeof drift === "object" &&
    drift !== null &&
    typeof (drift as Record<string, unknown>).lessons_total === "number" &&
    typeof (drift as Record<string, unknown>).lessons_stale === "number" &&
    typeof (drift as Record<string, unknown>).threshold === "number" &&
    typeof (drift as Record<string, unknown>).drift_fraction === "number" &&
    typeof (drift as Record<string, unknown>).over_threshold === "boolean" &&
    typeof replayDrift === "object" &&
    replayDrift !== null &&
    typeof (replayDrift as Record<string, unknown>).sessions_replayed === "number" &&
    typeof (replayDrift as Record<string, unknown>).sessions_with_drift === "number" &&
    typeof (replayDrift as Record<string, unknown>).threshold === "number" &&
    typeof (replayDrift as Record<string, unknown>).drift_rate === "number" &&
    typeof (replayDrift as Record<string, unknown>).over_threshold === "boolean" &&
    typeof adrs === "object" &&
    adrs !== null &&
    typeof (adrs as Record<string, unknown>).total === "number" &&
    Array.isArray((adrs as Record<string, unknown>).missing_status) &&
    ((adrs as Record<string, unknown>).missing_status as Array<unknown>).every(
      (item) => typeof item === "string",
    ) &&
    typeof (adrs as Record<string, unknown>).scanned === "boolean"
  );
}

function isLessonItem(value: unknown): value is LessonItem {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    typeof v.status === "string" &&
    typeof v.scope === "string" &&
    typeof v.confidence === "number" &&
    typeof v.rule === "string" &&
    typeof v.why === "string" &&
    typeof v.how_to_apply === "string" &&
    typeof v.hit_count === "number"
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

  async auditData(options: { windowDays?: number } = {}): Promise<AuditPayload> {
    const args = ["audit", "--json"];
    if (options.windowDays !== undefined) {
      args.push("--window-days", String(options.windowDays));
    }
    const result = await runBsela(args, this.options);
    // `bsela audit` exits 1 when any alert is active — that is a
    // signal, not a failure. Accept both exit codes.
    assertSuccess(args, result, [0, 1]);
    const parsed = parseJson(result.stdout.trim());
    if (!isAuditPayload(parsed)) {
      throw new BselaClientError(
        "bsela audit returned an unexpected payload shape",
        result.exitCode,
        JSON.stringify(parsed).slice(0, 200),
      );
    }
    return parsed;
  }

  async status(): Promise<StatusPayload> {
    const args = ["status", "--json"];
    const result = await runBsela(args, this.options);
    assertSuccess(args, result);
    const parsed = parseJson(result.stdout.trim());
    if (!isStatusPayload(parsed)) {
      throw new BselaClientError(
        "bsela status returned an unexpected payload shape",
        result.exitCode,
        JSON.stringify(parsed).slice(0, 200),
      );
    }
    return parsed;
  }

  async lessons(
    options: { status?: string; limit?: number; trackHits?: boolean } = {},
  ): Promise<Array<LessonItem>> {
    const suffixArgs: Array<string> = ["--json"];
    if (options.status !== undefined) suffixArgs.push("--status", options.status);
    if (options.limit !== undefined) suffixArgs.push("--limit", String(options.limit));
    if (options.trackHits === true) suffixArgs.push("--track-hits");

    const preferredArgs = ["lessons", ...suffixArgs];
    const fallbackArgs = ["review", "list", ...suffixArgs];

    let result = await runBsela(preferredArgs, this.options);
    if (result.exitCode !== 0 && /No such command ['"]lessons['"]/i.test(result.stderr)) {
      result = await runBsela(fallbackArgs, this.options);
      assertSuccess(fallbackArgs, result);
    } else {
      assertSuccess(preferredArgs, result);
    }

    const parsed = parseJson(result.stdout.trim());
    if (!Array.isArray(parsed) || !parsed.every(isLessonItem)) {
      throw new BselaClientError(
        "bsela lessons returned an unexpected payload shape",
        result.exitCode,
        JSON.stringify(parsed).slice(0, 200),
      );
    }
    return parsed;
  }
}
