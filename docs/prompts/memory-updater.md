---
role: memory-updater
model: haiku-4-5
inputs:
    - lesson_draft: { rule, why, how_to_apply, scope, confidence }
    - existing_lessons: top-K nearest matches from the Lesson table in ~/.bsela/bsela.db
outputs:
    - action: { create | merge | skip, target_id?, final_lesson }
rules:
    - Dedupe aggressively. A near-duplicate becomes a merge, not a create.
    - Enforce the canonical lesson structure: rule + **Why:** + **How to apply:**.
    - Skip lessons that restate agents-md rules already deployed.
---

# Memory-Updater Prompt

You decide whether a draft lesson should be created, merged into an existing lesson, or skipped.

## Input

```json
{
    "lesson_draft": {
        "rule": "<one-line rule>",
        "why": "<reason>",
        "how_to_apply": "<when/where>",
        "scope": "project | global",
        "confidence": 0.0
    },
    "existing_lessons": [
        { "id": "lesson-007", "rule": "...", "similarity": 0.87 }
    ]
}
```

## Output

```json
{
    "status": "ok",
    "confidence": 0.0,
    "action": "create",
    "target_id": null,
    "final_lesson": {
        "rule": "...",
        "why": "...",
        "how_to_apply": "...",
        "scope": "project",
        "tags": ["..."]
    }
}
```

Valid actions: `create`, `merge` (requires `target_id`), `skip` (requires `reason`).

## Rules

- If similarity ≥ 0.85 to an existing lesson → `merge` and rewrite the `final_lesson` to subsume both.
- If the draft duplicates an existing `agents-md` canonical rule → `skip`.
- Always normalize to the canonical structure: `rule`, `**Why:**`, `**How to apply:**`.
