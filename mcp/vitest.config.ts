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
      // index.ts is a pure re-export barrel (no logic) and server.ts
      // main() is the stdio bootstrap left to the e2e smoke — neither is
      // worth unit coverage.
      exclude: ["src/index.ts"],
      // Ratchet floor set with margin below CI-measured coverage so the
      // gate catches real regressions without flaking on the small
      // local/CI delta (integration tests cover slightly less against a
      // fresh CI store). Raise as coverage improves, never to flake.
      thresholds: {
        lines: 85,
        statements: 83,
        branches: 78,
        functions: 88,
      },
    },
  },
});
