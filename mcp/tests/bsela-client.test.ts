import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { describe, expect, it } from "vitest";

import { BselaClient, BselaClientError } from "../src/index.js";

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
});

describe("BselaClient.lessons", () => {
  const client = makeClient();

  it("returns lesson items from the top-level lessons alias", async () => {
    const payload = await client.lessons({ limit: 1 });
    expect(Array.isArray(payload)).toBe(true);
    expect(payload.length).toBeLessThanOrEqual(1);
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
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});

describe("BselaClient error paths", () => {
  it("rejects when the binary is missing", async () => {
    const client = new BselaClient({ binary: "/nonexistent/bsela-does-not-exist" });
    await expect(client.route("plan")).rejects.toBeInstanceOf(BselaClientError);
  });
});
