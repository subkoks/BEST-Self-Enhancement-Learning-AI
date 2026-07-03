# Changelog

All notable changes to BSELA are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Until 1.0, breaking changes are allowed in any minor release; they will be
called out under a `Breaking` heading.

## [Unreleased]

## [0.2.1] - 2026-06-25

### Added

- Externalized lesson status (`externalized`): lessons promoted to production rules in `~/AGENTS.md` are now classified as `externalized` rather than cycling back through `pending` — prevents false-positive DRIFT alerts after a rules update.

### Fixed

- Self-referential guard now covers all BSELA MCP envelope keys, not only `BSELA_HOME` — prevents the session capture from re-ingesting its own running environment.
- Stack-trace detector no longer fires on BSELA's own serialized error output in `stack_trace` fields — reduces false-positive error classification on recursive BSELA runs.

## [0.2.0] - 2026-06-15

Public-readiness hardening release. The default config now ships inside the
installed package, transcript parsing tolerates malformed lines, and the MCP
suite gained a coverage gate. No CLI or MCP contract changes.

### Added

- `RELEASING.md` documenting the version-bump locations and release steps.
- MCP coverage gate: `pnpm check` now runs `vitest --coverage` with ratchet
  thresholds; test files run serially to avoid races on the shared store.

### Fixed

- `pip install bsela` outside a source checkout no longer raises
  `FileNotFoundError`: the default `config/{thresholds,models}.toml` are bundled
  into the wheel (`bsela/_config`) and `find_config_dir()` falls back to the
  packaged copy.
- A single malformed JSONL line in a transcript no longer crashes ingest or
  detection — the bad line is skipped and logged, and surrounding events are
  still processed.

### Changed

- `AnthropicClient` now sends an explicit request `timeout` (default 120s),
  matching the OpenRouter client, so a hung connection can't block a batch.
- The hard-coded `agents-md` repo path lives in one place: `bsela doctor`
  reuses `updater.DEFAULT_AGENTS_MD_REPO`, and the "repo not found" error now
  points to the `BSELA_AGENTS_MD_REPO` override.

## [0.1.1] - 2026-06-07

Maintenance and hardening release: model routing moved to Claude Opus 4.8,
the replay-drift signal was reclassified as informational (no longer a release
gate), and the CI and dependency surface were hardened. No CLI or MCP contract
changes.

### Added

- CONTEXT.md domain glossary pinning the project vocabulary (Session, Error,
  Lesson, Replay drift, Gate, …) for code, commits, and reviews (#63).
- Autonomous next-session runbook (`docs/next-session-autonomous.md`) covering
  Cursor/Codex hosts, skill selection, and the preflight gate sequence (#51).
- Repository community-health files: `SECURITY.md`, `CONTRIBUTING.md`, this
  `CHANGELOG.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant), `.github/CODEOWNERS`,
  `.github/ISSUE_TEMPLATE/*`, and `.github/dependabot.yml` (#68).

### Changed

- Model routing migrated to Claude Opus 4.8 across the role table in
  `config/models.toml` (#56).
- Replay drift is now an informational **warning**, not a blocking **alert**:
  `bsela audit` exits `0` when replay drift is the only signal over threshold.
  On nondeterministic / free-tier models the distiller emits a different lesson
  multiset per run, so replay drift tracks model stability rather than a
  regression (ADR 0010) (#58, #60, #61).

### Fixed

- Replay determinism and signal quality: isolate replay distillation from the
  mutable lesson context, stabilize the replay-drift signal and the SQLite
  connection lifecycle, and pair lessons semantically via Jaccard similarity so
  paraphrase noise no longer inflates the diff (#36, #38, #40).
- Correct the project URLs in `pyproject.toml` to the canonical public repo (#52).

### Security

- Harden GitHub Actions: author-gate the Claude Code workflow, SHA-pin all
  third-party actions, restrict workflow permissions to read-only, and contain
  lesson writes to expected paths (#59, #69).
- Dependency security bumps: `hono` ≥ 4.12.21 (GHSA-3hrh-pfw6-9m5x) (#70),
  transitive `qs` ≥ 6.15.2 (moderate DoS) (#57), plus grouped Python and MCP
  dependency updates.

[Unreleased]: https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/releases/tag/v0.1.0