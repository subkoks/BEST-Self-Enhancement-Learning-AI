import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { describe, expect, it } from "vitest";

import {
  BselaClient,
  BselaClientError,
  isErrorItem,
  isLessonItem,
  type LessonItem,
} from "../src/index.js";

/**
 * These are integration tests: they shell out to the `bsela`
 * Python CLI that ships with this repo. `bsela` must be on PATH
 * and `.venv` must be initialised (`uv sync` + `uv tool install -e .`).
 *
 * We prepend `~/.local/bin` to PATH so the uv-installed binary (which
 * tracks the current worktree) wins over pyenv shims, which may point
 * to an older install from the main branch.
 */
function makeClient(): BselaClient {
  const localBin = join(homedir(), ".local", "bin");
  const path = `${localBin}:${process.env["PATH"] ?? ""}`;
  return new BselaClient({ env: { ...process.env, PATH: path } });
}

function sortedKeys(value: Record<string, unknown>): Array<string> {
  return Object.keys(value).sort();
}

const SAMPLE_LESSON_ITEM: LessonItem = {
  id: "00000000-0000-4000-8000-000000000001",
  status: "pending",
  scope: "project",
  confidence: 0.91,
  rule: "Sample rule",
  why: "Sample why",
  how_to_apply: "Sample how",
  hit_count: 0,
  created_at: "2026-05-02T12:00:00+00:00",
};

describe("isLessonItem", () => {
  it("accepts a well-formed lesson row", () => {
    expect(isLessonItem(SAMPLE_LESSON_ITEM)).toBe(true);
  });

  it("accepts null or omitted created_at", () => {
    expect(isLessonItem({ ...SAMPLE_LESSON_ITEM, created_at: null })).toBe(true);
    const { created_at: _c, ...rest } = SAMPLE_LESSON_ITEM;
    expect(isLessonItem(rest)).toBe(true);
  });

  it("rejects created_at when it is not a string, null, or undefined", () => {
    const base = { ...SAMPLE_LESSON_ITEM };
    const numericCa: unknown = { ...base, created_at: 123 };
    const objectCa: unknown = { ...base, created_at: {} };
    const boolCa: unknown = { ...base, created_at: false };
    expect(isLessonItem(numericCa)).toBe(false);
    expect(isLessonItem(objectCa)).toBe(false);
    expect(isLessonItem(boolCa)).toBe(false);
  });
});

describe("BselaClient.route", () => {
  const client = makeClient();

  it("routes a planning task to the planner role", async () => {
    const decision = await client.route("plan the migration to P6");
    expect(decision.task_class).toBe("planner");
    expect(decision.confidence).toBe(1);
    expect(decision.model).toMatch(/opus/);
    expect(decision.matched_keywords).toContain("plan");
  });

  it("routes a refactor task to the builder role", async () => {
    const decision = await client.route("refactor the updater module");
    expect(decision.task_class).toBe("builder");
    expect(decision.confidence).toBe(1);
  });

  it("falls back to the default role for whitespace-only input", async () => {
    const decision = await client.route("   ");
    expect(decision.task_class).toBe("builder");
    expect(decision.confidence).toBe(0.5);
    expect(decision.matched_keywords).toEqual([]);
  });

  it("keeps a stable RouteDecision key set", async () => {
    const decision = await client.route("plan the migration to P6");
    expect(sortedKeys(decision as unknown as Record<string, unknown>)).toEqual([
      "confidence",
      "matched_keywords",
      "model",
      "reason",
      "task_class",
    ]);
  });
});

describe("BselaClient.audit", () => {
  const client = makeClient();

  it("returns markdown starting with the audit header", async () => {
    const markdown = await client.audit({ windowDays: 30 });
    expect(markdown).toContain("# BSELA Weekly Audit");
    expect(markdown).toContain("## Alerts");
  });

  it("returns typed JSON payload from --json mode", async () => {
    const payload = await client.auditData({ windowDays: 30 });
    expect(payload.window_days).toBe(30);
    expect(typeof payload.sessions.total).toBe("number");
    expect(typeof payload.cost.over_budget).toBe("boolean");
    expect(Array.isArray(payload.alerts)).toBe(true);
  });

  it("keeps stable top-level audit JSON keys", async () => {
    const payload = await client.auditData({ windowDays: 30 });
    expect(sortedKeys(payload as unknown as Record<string, unknown>)).toEqual([
      "adrs",
      "alerts",
      "cost",
      "drift",
      "errors_total",
      "generated_at",
      "replay_drift",
      "sessions",
      "window_days",
      "window_end",
      "window_start",
    ]);
  });
});

describe("BselaClient.status", () => {
  const client = makeClient();

  it("returns a typed StatusPayload with numeric counts and bsela_home", async () => {
    const payload = await client.status();
    expect(typeof payload.sessions).toBe("number");
    expect(typeof payload.sessions_quarantined).toBe("number");
    expect(typeof payload.errors).toBe("number");
    expect(typeof payload.lessons).toBe("number");
    expect(typeof payload.lessons_pending).toBe("number");
    expect(typeof payload.lessons_proposed).toBe("number");
    expect(typeof payload.replay_records).toBe("number");
    expect(typeof payload.bsela_home).toBe("string");
    expect(payload.bsela_home.length).toBeGreaterThan(0);
  });

  it("keeps a stable StatusPayload key set", async () => {
    const payload = await client.status();
    expect(sortedKeys(payload as unknown as Record<string, unknown>)).toEqual([
      "bsela_home",
      "errors",
      "lessons",
      "lessons_pending",
      "lessons_proposed",
      "replay_records",
      "sessions",
      "sessions_quarantined",
    ]);
  });
});

describe("BselaClient.lessons", () => {
  const client = makeClient();

  it("returns empty array for lessons on a fresh BSELA_HOME", async () => {
    const home = await mkdtemp(join(tmpdir(), "bsela-lessons-empty-"));
    try {
      const localBin = join(homedir(), ".local", "bin");
      const path = `${localBin}:${process.env["PATH"] ?? ""}`;
      const isolatedClient = new BselaClient({
        env: { ...process.env, PATH: path, BSELA_HOME: home },
        cwd: home,
      });
      const payload = await isolatedClient.lessons({ status: "pending", limit: 5 });
      expect(payload).toEqual([]);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });

  it("returns lesson items from the top-level lessons alias", async () => {
    const payload = await client.lessons({ limit: 1 });
    expect(Array.isArray(payload)).toBe(true);
    expect(payload.length).toBeLessThanOrEqual(1);
    if (payload[0] !== undefined) {
      expect(sortedKeys(payload[0] as unknown as Record<string, unknown>)).toEqual([
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
  });

  it("falls back to `review list` when `lessons` command is unavailable", async () => {
    const dir = await mkdtemp(join(tmpdir(), "bsela-client-fallback-"));
    const binary = join(dir, "bsela-stub");
    const script = `#!/bin/sh
if [ "$1" = "lessons" ]; then
  echo "No such command 'lessons'" 1>&2
  exit 2
fi
if [ "$1" = "review" ] && [ "$2" = "list" ]; then
  cat <<'JSON'
[{"id":"lesson-1","status":"approved","scope":"project","confidence":0.95,"rule":"Use fallback path","why":"legacy compatibility","how_to_apply":"call review list","hit_count":3,"created_at":"2026-05-02T00:00:00+00:00"}]
JSON
  exit 0
fi
echo "unexpected args: $*" 1>&2
exit 1
`;
    await writeFile(binary, script, { encoding: "utf-8" });
    await chmod(binary, 0o755);
    try {
      const stubClient = new BselaClient({ binary });
      const payload = await stubClient.lessons();
      expect(payload).toHaveLength(1);
      expect(payload[0]?.id).toBe("lesson-1");
      expect(payload[0]?.rule).toBe("Use fallback path");
      expect(sortedKeys(payload[0] as unknown as Record<string, unknown>)).toEqual([
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
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("passes status, limit, and track-hits flags to lessons command", async () => {
    const dir = await mkdtemp(join(tmpdir(), "bsela-client-lessons-args-"));
    const binary = join(dir, "bsela-stub");
    const script = `#!/bin/sh
if [ "$1" = "lessons" ] && [ "$2" = "--json" ] && [ "$3" = "--status" ] && [ "$4" = "approved" ] && [ "$5" = "--limit" ] && [ "$6" = "7" ] && [ "$7" = "--track-hits" ]; then
  cat <<'JSON'
[]
JSON
  exit 0
fi
echo "unexpected args: $*" 1>&2
exit 1
`;
    await writeFile(binary, script, { encoding: "utf-8" });
    await chmod(binary, 0o755);
    try {
      const stubClient = new BselaClient({ binary });
      const payload = await stubClient.lessons({
        status: "approved",
        limit: 7,
        trackHits: true,
      });
      expect(payload).toEqual([]);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});

describe("isErrorItem", () => {
  const sample = {
    id: "err-001",
    session_id: "sess-001",
    category: "correction",
    severity: "medium",
    line_number: 42,
    snippet: "user said stop",
    detected_at: "2026-05-02T10:00:00+00:00",
  };

  it("accepts a well-formed error row", () => {
    expect(isErrorItem(sample)).toBe(true);
  });

  it("accepts null line_number and detected_at", () => {
    expect(isErrorItem({ ...sample, line_number: null, detected_at: null })).toBe(true);
  });

  it("rejects if session_id is missing", () => {
    const { session_id: _s, ...rest } = sample;
    expect(isErrorItem(rest)).toBe(false);
  });
});

describe("BselaClient.errors", () => {
  const client = makeClient();

  it("returns an array (possibly empty) of error items", async () => {
    const items = await client.errors({ limit: 5 });
    expect(Array.isArray(items)).toBe(true);
    if (items[0] !== undefined) {
      expect(sortedKeys(items[0] as unknown as Record<string, unknown>)).toEqual([
        "category",
        "detected_at",
        "id",
        "line_number",
        "session_id",
        "severity",
        "snippet",
      ]);
    }
  });

  it("returns empty array on a fresh BSELA_HOME", async () => {
    const home = await mkdtemp(join(tmpdir(), "bsela-errors-empty-"));
    try {
      const localBin = join(homedir(), ".local", "bin");
      const path = `${localBin}:${process.env["PATH"] ?? ""}`;
      const isolatedClient = new BselaClient({
        env: { ...process.env, PATH: path, BSELA_HOME: home },
        cwd: home,
      });
      const items = await isolatedClient.errors({ limit: 5 });
      expect(items).toEqual([]);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });
});

describe("BselaClient error paths", () => {
  it("rejects when the binary is missing", async () => {
    const client = new BselaClient({ binary: "/nonexistent/bsela-does-not-exist" });
    await expect(client.route("plan")).rejects.toBeInstanceOf(BselaClientError);
  });
});
