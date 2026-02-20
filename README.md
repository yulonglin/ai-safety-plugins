# ai-safety-plugins

Claude Code plugins for AI safety research: experiment design, academic writing, code review, workflow management, and visualization.

## Quick Start

```bash
# Add the marketplace
/plugin marketplace add yulonglin/ai-safety-plugins

# Install core (recommended for everyone)
/plugin install core@ai-safety-plugins

# Install domain-specific plugins
/plugin install research@ai-safety-plugins
/plugin install code@ai-safety-plugins
/plugin install writing@ai-safety-plugins
/plugin install workflow@ai-safety-plugins
/plugin install viz@ai-safety-plugins
```

## Plugins

### core (recommended: always-on)

Foundational agents and skills that other plugins depend on.

**Agents:**
| Agent | Purpose | External Deps |
|-------|---------|---------------|
| `efficient-explorer` | Context-efficient codebase exploration | None |
| `context-summariser` | Conversation compression | None |
| `claude` | Judgment-heavy delegation via Claude Code CLI | None |
| `codex` | Implementation delegation via Codex CLI | Codex CLI + OpenAI key (optional) |
| `gemini-cli` | Large context delegation via Gemini CLI | Gemini CLI + Google key (optional) |

**Skills:**
| Skill | Purpose |
|-------|---------|
| `/docs-search` | Fast grep-based docs search (`fd` + `rg`) |
| `/fast-cli` | Modern CLI tool mappings (eza, fd, rg, bat, etc.) |
| `/spec-interview` | Interview-based spec development |
| `/task-management` | Timestamped task tracking |

**Hooks (safety guards):**
| Hook | Event | Purpose |
|------|-------|---------|
| `check_destructive_commands` | PreToolUse:Bash | Blocks `sudo rm`, `xargs kill`, etc. |
| `check_secrets` | PreToolUse:Bash | Blocks committing API keys/tokens |
| `check_read_size` | PreToolUse:Read | Warns on reading large files without offset/limit |
| `task_force_background` | PreToolUse:Task | Forces subagent calls to background |
| `truncate_output` | PostToolUse:Bash | Truncates verbose output |
| `pre_plan_create` | PreToolUse:Write | Enforces per-project plans |
| `pre_task_create` | PreToolUse:TaskCreate | Enforces per-project tasks |

### research

AI safety research workflows.

**Agents:** experiment-designer, research-engineer, data-analyst, literature-scout, research-advisor, research-skeptic

**Skills:** `/spec-interview-research`, `/experiment-setup`, `/run-experiment`, `/api-experiments`, `/read-paper`, `/reproducibility-report`, `/generate-research-spec`, `/mats-slurm`, `/audit-docs`, `/new-experiment`, `/reflect`

### writing

Academic writing and presentations.

**Agents:** paper-writer, application-writer, humanizer, writing-clarity, writing-facts, writing-narrative, writing-redteam

**Skills:** `/review-draft`, `/review-paper`, `/research-presentation`, `/slidev`, `/fix-slide`, `/clear-writing`, `/humanize-draft`, `/strategic-communication`

### code

Development workflow, code review, and delegation.

**Agents:** code-reviewer, codex-reviewer, plan-critic, debugger, performance-optimizer, tooling-engineer

**Skills:** `/bulk-edit`, `/fix-merge-conflict`, `/deslop`

**Depends on:** `core` (codex and gemini-cli agents)

### workflow

Agent orchestration and conversation management.

**Skills:** `/agent-teams`, `/custom-compact`, `/externalise-handover`, `/custom-insights`

**Hooks (convenience, opt-out via env var):**
| Hook | Event | Purpose | Disable |
|------|-------|---------|---------|
| `auto_background` | PreToolUse:Bash | Auto-backgrounds long commands | `CLAUDE_AUTOBACKGROUND=0` |
| `check_pipe_buffering` | PreToolUse:Bash | Warns about piping anti-patterns | Warn only |
| `auto_log` | Pre/PostToolUse:Bash | Audit trail of commands | Async, non-blocking |

**Depends on:** `core` (context-summariser, gemini-cli agents)

### viz

TikZ diagrams and Anthropic-style visualization.

**Skills:** `/tikz-diagrams`

**Requires:** LaTeX (pdflatex/xelatex)

## Dependency Matrix

| Dependency | core | research | writing | code | workflow | viz |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Claude Code v2.1+** | REQ | REQ | REQ | REQ | REQ | REQ |
| Codex CLI | opt | — | — | REQ | — | — |
| Gemini CLI | opt | — | — | opt | REQ* | — |
| `fd` + `rg` | opt | — | — | — | — | — |
| `bun`/`bunx` | — | — | opt | — | — | — |
| LaTeX | — | — | opt | — | — | REQ |
| Modern CLI tools** | opt | — | — | — | — | — |
| OpenAI API key | opt | opt | — | opt | — | — |
| Google API key | opt | — | — | opt | opt | — |
| Python 3.9+ | — | REQ | — | — | REQ* | — |

\* For `/custom-insights` skill only.
\** eza, bat, dust, duf, fzf, zoxide, delta, jq.

## Full Setup

```bash
# macOS
brew install codex gemini-cli fd ripgrep
brew install --cask mactex  # Only for viz / presentations

# Auth
codex auth           # OpenAI key (for Codex delegation)
gh auth login        # GitHub token (optional)
```

### Optional Reference Docs

Some agents reference documentation from `~/.claude/docs/` for enhanced functionality. These docs are optional — agents work without them but provide richer output when they're available. If you use the [dotfiles](https://github.com/yulonglin/dotfiles) repo, these are deployed automatically. Otherwise, bundled copies are included in each plugin's `agents/references/` directory.

## Enable Always-On

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "enabledPlugins": {
    "core@ai-safety-plugins": true
  }
}
```

## License

MIT
