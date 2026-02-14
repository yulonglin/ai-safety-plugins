# ai-safety-plugins

Claude Code plugins for AI safety research: experiment design, academic writing, code review, workflow management, and visualization.

## Quick Start

```bash
# Add the marketplace
/plugin marketplace add yulonglin/ai-safety-plugins

# Install core (recommended for everyone)
/plugin install core-toolkit@ai-safety-plugins

# Install domain-specific plugins
/plugin install research-toolkit@ai-safety-plugins
/plugin install code-toolkit@ai-safety-plugins
/plugin install writing-toolkit@ai-safety-plugins
/plugin install workflow-toolkit@ai-safety-plugins
/plugin install viz-toolkit@ai-safety-plugins
```

## Plugins

### core-toolkit (recommended: always-on)

Foundational agents and skills that other plugins depend on.

**Agents:**
| Agent | Purpose | External Deps |
|-------|---------|---------------|
| `efficient-explorer` | Context-efficient codebase exploration | None |
| `context-summariser` | Conversation compression | None |
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

### research-toolkit

AI safety research workflows.

**Agents:** experiment-designer, research-engineer, data-analyst, literature-scout, research-advisor, research-skeptic

**Skills:** `/spec-interview-research`, `/experiment-setup`, `/run-experiment`, `/api-experiments`, `/read-paper`, `/reproducibility-report`, `/generate-research-spec`, `/mats-slurm`

### writing-toolkit

Academic writing and presentations.

**Agents:** paper-writer, application-writer, humanizer, writing-clarity, writing-facts, writing-narrative, writing-redteam

**Skills:** `/review-draft`, `/review-paper`, `/research-presentation`, `/slidev`, `/fix-slide`, `/clear-writing`, `/humanize-draft`, `/strategic-communication`

### code-toolkit

Development workflow, code review, and delegation.

**Agents:** code-reviewer, codex-reviewer, plan-critic, debugger, performance-optimizer, tooling-engineer, claude

**Skills:** `/codex-cli`, `/claude-code`, `/bulk-edit`, `/fix-merge-conflict`, `/deslop`

**Depends on:** `core-toolkit` (codex and gemini-cli agents)

### workflow-toolkit

Agent orchestration and conversation management.

**Skills:** `/agent-teams`, `/custom-compact`, `/externalise-handover`, `/insights`

**Hooks (convenience, opt-out via env var):**
| Hook | Event | Purpose | Disable |
|------|-------|---------|---------|
| `auto_background` | PreToolUse:Bash | Auto-backgrounds long commands | `CLAUDE_AUTOBACKGROUND=0` |
| `check_pipe_buffering` | PreToolUse:Bash | Warns about piping anti-patterns | Warn only |
| `auto_log` | Pre/PostToolUse:Bash | Audit trail of commands | Async, non-blocking |

**Depends on:** `core-toolkit` (context-summariser, gemini-cli agents)

### viz-toolkit

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

\* For `/insights` skill only.
\** eza, bat, dust, duf, fzf, zoxide, delta, jq.

## Full Setup

```bash
# macOS
brew install codex gemini-cli fd ripgrep
brew install --cask mactex  # Only for viz-toolkit / presentations

# Auth
codex auth           # OpenAI key (for Codex delegation)
gh auth login        # GitHub token (optional)
```

## Enable Always-On

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "enabledPlugins": {
    "core-toolkit@ai-safety-plugins": true
  }
}
```

## License

MIT
