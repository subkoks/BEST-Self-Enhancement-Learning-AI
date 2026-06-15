# Releasing BSELA

BSELA ships two artifacts from one repo: the `bsela` Python CLI (PyPI-shaped,
built with hatchling) and the private `@bsela/mcp` TypeScript server. Versions
are kept in lockstep.

## 1. Version locations (bump all four)

The version string is duplicated across Python and TypeScript; there is no
single source of truth, so bump every location to the new `X.Y.Z`:

| File                     | Field                          |
| ------------------------ | ------------------------------ |
| `pyproject.toml`         | `version = "X.Y.Z"`            |
| `src/bsela/__init__.py`  | `__version__ = "X.Y.Z"`        |
| `mcp/package.json`       | `"version": "X.Y.Z"`           |
| `mcp/src/server.ts`      | `const SERVER_VERSION = "X.Y.Z"` |

Sanity check there are no stragglers:

```sh
grep -rn "<previous-version>" pyproject.toml src mcp/src mcp/package.json
```

## 2. Update the CHANGELOG

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

- Move items out of `[Unreleased]` into a new `## [X.Y.Z] - YYYY-MM-DD` section
  under `Added` / `Changed` / `Fixed` / `Security` (and `Breaking` pre-1.0).
- Update the comparison links at the bottom: repoint `[Unreleased]` to
  `vX.Y.Z...HEAD` and add `[X.Y.Z]: …/compare/<prev>...vX.Y.Z`.

## 3. Run the gates (must be green)

```sh
make check       # ruff + mypy + pytest @ ≥99% coverage
make mcp-check    # pnpm check (incl. coverage gate) + pnpm build
```

Verify the wheel actually bundles the default config (regression guard for the
`pip install` path):

```sh
uv build --wheel
unzip -l dist/bsela-X.Y.Z-*.whl | grep _config   # expect bsela/_config/*.toml
```

## 4. Tag and release

Land the version bump + CHANGELOG via PR, then from `main`:

```sh
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --notes-from-tag
```

Publishing to PyPI / npm is not yet automated — `mcp/` is `private` and the
Python package is not yet pushed to PyPI. When that changes, add a
tag-triggered `publish.yml` and document it here.
