import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
    testTimeout: 10_000,
    // Integration + parity tests shell out to the same live `bsela` CLI
    // and shared `~/.bsela` store; running files in parallel races on
    // those reads/writes (counts shift mid-comparison). Serialize for
    // deterministic results — the suite is small enough that it's cheap.
    fileParallelism: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      // Ratchet floor at current measured coverage. server.ts main()
      // is the stdio bootstrap and is intentionally left to the e2e
      // smoke; raise these as coverage improves, never lower them.
      thresholds: {
        lines: 90,
        statements: 87,
        branches: 85,
        functions: 92,
      },
    },
  },
});
