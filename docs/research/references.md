# External References

Structured port of `Aditional-research-for-project.txt` — links grouped by what they contribute to BSELA.

## Self-improvement theory

- **LangChain — Continual learning for AI agents** — three layers (weights / harness / context). Foundation for ADR 0001.
  <https://www.langchain.com/blog/continual-learning-for-ai-agents>
- **Beam.ai — Self-learning AI agents** — multi-agent supervisor/worker pattern. Referenced for V2+ sub-agent design.
  <https://beam.ai/agentic-insights/self-learning-ai-agents-transforming-automation-with-continuous-improvement>
- **Medium — Continuous learning and self-enhancement in AI agents** (Nandakishore) — narrative intro to feedback loops.
  <https://medium.com/@nandakishore2001menon/continuous-learning-and-self-enhancement-in-ai-agents-aa8169c1caf1>
- **Swept.ai — AI model drift** — why "silently wrong" is the dominant failure mode; motivates BSELA's drift detection.
  <https://www.swept.ai/ai-model-drift>

## Skills / rules patterns (lesson format inspiration)

- **Anthropic Skills** — canonical skill structure.
  <https://github.com/anthropics/skills>
- **Forrest Chang — Karpathy skills** — working examples of skill packaging.
  <https://github.com/forrestchang/andrej-karpathy-skills>
- **PatrickJS — awesome-cursorrules** — cross-editor rule collection.
  <https://github.com/PatrickJS/awesome-cursorrules>
- **Affaan-m — everything-claude-code** — community patterns.
  <https://github.com/affaan-m/everything-claude-code>
- **ykdojo — claude-code-tips** — reference for CC hook contracts.
  <https://github.com/ykdojo/claude-code-tips>

## Agent platforms (competitive / comparative)

- **Onyx** — custom agents for unique workflows.
  <https://onyx.app/> · <https://github.com/onyx-dot-app/onyx>
- **Beam platform** — multi-agent orchestration.
  <https://beam.ai/platform>
- **BridgeCode (bridgemind.ai)** — "agent-first IDE, vibe-coding native"; multi-panel workspace with Claude-native agents.
  <https://www.bridgemind.ai/products/bridgecode>
- **Windsurf** — editor already in user stack.
  <https://windsurf.com/>
- **opencode.ai** — open-source coding agent.
  <https://opencode.ai/>

## Frameworks (rejected for V1, tracked for V2)

- **LangChain deepagents** — reference only.
  <https://github.com/langchain-ai/deepagents>
- **Model Context Protocol** — selected for V2 MCP server.
  <https://github.com/modelcontextprotocol>

## Browser / automation components (Researcher tool surface)

- **Browserbase agents** — <https://github.com/browserbase/agent-browse>
- **Stagehand** — <https://github.com/browserbase/stagehand>
- **Browserbase MCP** — <https://github.com/browserbase/mcp-server-browserbase>

## Dev tooling (user's environment)

- **Steipete — CodexBar / RepoBar** — macOS integrations the user may extend.
  <https://github.com/steipete/CodexBar> · <https://github.com/steipete/RepoBar>
- **dyoburon — claude-code-workflow-tools** — relevant hooks/skills.
  <https://github.com/dyoburon/claude-code-workflow-tools>
- **dyoburon — greppy** — <https://github.com/dyoburon/greppy>

## Skill marketplaces

- **skillstore.io** — <https://skillstore.io/skills?category=coding&tools=claude-code>
- **skills.sh** — <https://skills.sh/>
- **skillsmp.com** — <https://skillsmp.com/>

## Misc (noted, not yet actionable)

- Supabase — <https://supabase.com/>
- ECNU-ICALK — <https://github.com/orgs/ECNU-ICALK/repositories>
- GitHub search: "Continuous Learning and Self Enhancement" — <https://github.com/search?q=Continuous+Learning+and+Self+Enhancement&type=repositories>
- Thunderbolt — <https://www.thunderbolt.io/announcing-thunderbolt> · <https://github.com/thunderbird/thunderbolt>
- Swept.ai (development) — <https://www.swept.ai/solutions/development>
- Firacode — <https://firacode.com/>

## Model benchmarks / selection

Referenced in `config/models.toml`. Live docs:
- **Anthropic Claude docs** — <https://code.claude.com/docs>
- **OpenAI Codex docs** — check `/status` in Codex CLI.

## Key Takeaways Applied to BSELA

1. **Three-layer framing** (weights / harness / context) → ADR 0001 makes context+harness the sole battlefield.
2. **Persistent memory as shared brain across sessions** → memory taxonomy in `docs/architecture.md`.
3. **Self-reflection / critique cycles** → Distiller + Judge pipeline.
4. **Model drift** → auditor drift-alarm in P7.
5. **Multi-agent caution** → proven-need gate in ADR 0002.
6. **Onyx / Beam / BridgeCode** are competitors for a *product*, not a *personal control plane*. BSELA occupies a different niche: per-user, local, works alongside commercial agents instead of replacing them.
