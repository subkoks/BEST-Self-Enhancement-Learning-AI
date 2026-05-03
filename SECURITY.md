# Security Policy

## Reporting a vulnerability

BSELA is local-first software. Most issues should be reported as normal GitHub
issues. **Do not** open a public issue for security-sensitive findings — for
those, use GitHub's private vulnerability reporting:

- <https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI/security/advisories/new>

If private reporting is unavailable for any reason, contact the maintainer
through the Twitter/X handle linked from <https://github.com/subkoks>.

Please include:

- A description of the issue and the impact.
- Steps to reproduce, ideally with a minimal proof of concept.
- Affected version or commit SHA.
- Your environment (OS, runtime versions, editor / agent host).

## Scope

In scope:

- The `bsela` package and CLI.
- Hooks, MCP server wiring, and adapters shipped from this repo.
- Default configuration and example configs.

Out of scope:

- Third-party agent hosts (Claude Code, Codex, Cursor, Windsurf) themselves.
- User-modified hooks or out-of-tree integrations.
- Vulnerabilities that require a malicious local user with full filesystem
  access, since BSELA is explicitly local-first.

## Disclosure

We aim to acknowledge a report within 7 days and to ship a fix or mitigation
before public disclosure when feasible. Reporters are credited in release
notes unless they request otherwise.

## Supported versions

BSELA is pre-1.0; only the latest `main` branch is actively supported. Older
tags receive fixes only for the most recent release line.
