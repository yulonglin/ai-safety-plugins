---
name: research-loop
description: Set up and launch an autonomous research loop. Enforces an interview to establish clear inputs, outputs, and metrics before generating a program.md spec and dispatching an autonomous-researcher agent. Use when the user wants to automate research iteration — "run experiments overnight", "automate this research", "set up an autonomous loop", "research loop", "run while I sleep".
---

# Research Loop Setup

Set up an autonomous experiment loop that runs unattended. This skill **enforces an interview** to establish clear inputs, outputs, and metrics before generating anything.

## When to Use

- User has a **measurable metric** to optimize (loss, accuracy, F1, detection rate, etc.)
- User has an **experiment protocol** (a command or pipeline that produces results)
- User wants to run **unattended** (overnight, while away)

## Step 1: Interview (MANDATORY — do not skip)

**You MUST complete this interview before creating any spec or launching any agent.** Do not accept vague answers. Each question must have a concrete, actionable answer before moving on. If the user's answer is ambiguous, ask a follow-up to pin it down.

Use AskUserQuestion for each item. Ask 2-3 at a time to keep pace, but don't rush — a bad spec wastes an entire overnight run.

### Gate 1: Inputs (what goes in)

| # | Question | What you need | Reject if... |
|---|----------|--------------|--------------|
| 1 | **What files/code can the agent modify?** | Specific file paths + scope of allowed changes | "the codebase" (too broad) |
| 2 | **What is read-only?** | Evaluation harness, data format, dependencies, immutable sections | Nothing listed (everything must have a boundary) |
| 3 | **What does the working directory look like?** | How to set up, what needs to be installed, API keys needed | "it's already set up" (agent starts fresh — be explicit) |
| 4 | **Is there an existing strategy queue?** | Ideas to try, or should the agent brainstorm from scratch? | Fine if empty — just needs to be explicit |

### Gate 2: Outputs (what comes out)

| # | Question | What you need | Reject if... |
|---|----------|--------------|--------------|
| 5 | **What is the exact command to run one experiment?** | A copy-pasteable bash command | "run the training script" (which script? what args?) |
| 6 | **How do you extract the metric from the output?** | A grep/parse command, or the key in a JSON/TSV file | "look at the results" (agent needs programmatic extraction) |
| 7 | **How long does one experiment take?** | Minutes, hours, or "variable" with range | Must be answered — determines loop strategy |
| 8 | **How much does one experiment cost?** | Dollar amount, or "free" (local compute) | Must be answered — determines budget enforcement |

### Gate 3: Metrics (what "success" means)

| # | Question | What you need | Reject if... |
|---|----------|--------------|--------------|
| 9 | **What metric are you optimizing?** | Name, direction (lower/higher is better) | "make it better" (better how?) |
| 10 | **What is the current baseline?** | A number from an existing run | "I don't know" → run baseline first before setting up the loop |
| 11 | **What is the success threshold?** | A concrete number, or "any improvement over baseline" | No threshold at all (agent needs a stopping criterion) |
| 12 | **Are there secondary metrics / kill conditions?** | Metrics that must NOT degrade, or conditions that kill an experiment | Optional but important — prevents Goodhart's law |

### Gate 4: Constraints

| # | Question | What you need | Reject if... |
|---|----------|--------------|--------------|
| 13 | **Total budget?** | Max dollar amount, max experiments, or max time | "unlimited" is fine if local compute, but must be explicit |
| 14 | **Max runs per idea?** | A number, or "unlimited" | Must be answered |
| 15 | **Loop strategy?** | hill-climb / sprint / batch — explain the tradeoffs: | Must pick one |

**Loop strategy explanations (share with user):**
- **Hill-climb** (autoresearch-style): Try one thing, keep if better, discard if worse. Best when experiments are cheap and fast.
- **Sprint** (ralph-loop-style): Deep-dive on ONE idea per session. Best when experiments are expensive and need investigation.
- **Batch** (simply-style): Propose N experiments, run all, analyze, repeat. Best when you want breadth before depth.

### Readiness Check

Before proceeding to Step 2, verify you have concrete answers for ALL of:

```
✅ Metric name + direction + baseline + threshold
✅ Exact experiment command (copy-pasteable)
✅ Metric extraction method (programmatic)
✅ Modifiable files (specific paths)
✅ Read-only constraints (specific)
✅ Cost per run + total budget
✅ Time per run
✅ Loop strategy
```

**If any item is missing or vague, go back and ask.** Do NOT proceed with placeholders.

## Step 2: Create the Spec

Write a `program.md` in the project root. Use this template, filling in ONLY with concrete answers from the interview:

```markdown
# [Title]: Autonomous Research Loop

You are an autonomous research agent. [One sentence about the goal.]

## Objective
- **Metric:** [name] ([lower/higher] is better)
- **Threshold:** [number] (success criterion)
- **Baseline:** [current value]
- **Kill conditions:** [secondary metrics that must not degrade]

## Context: Read These First
- [List all files the agent should read before starting]

## Working Directory Setup
- [How to set up the working environment]
- [Verification steps: API keys, dependencies, data]

## Experiment Protocol
```bash
[The exact command to run one experiment]
```
- **Time per run:** [estimate]
- **Cost per run:** [estimate]
- **How to extract metric:** [grep command or parsing instructions]

## What You CAN Modify
- [File 1] — [what kinds of changes are fair game]
- [File 2] — [scope of allowed modifications]

## What You CANNOT Modify
- [File/component] — [why it's read-only]

## Strategy Queue
| Priority | ID | Strategy | What to change |
|----------|-----|----------|---------------|
| 1 | ... | ... | ... |

## For Each Experiment
1. Branch: `git checkout -b exp/<id>`
2. Implement the change
3. Commit with descriptive message
4. Run: [experiment command]
5. Extract metric: [how]
6. If improved → keep branch
7. If not → `git checkout main`
8. Log to `results.tsv` and `research-log.md`

## Budget
- **Total:** [amount]
- **Per-idea limit:** [max runs]
- **Reserve:** [amount for final validation]
- **Stop when:** [condition]

## Constraints
- [List all constraints from interview]

## NEVER STOP
Once you begin the experiment loop, do NOT pause to ask the human anything.
They may be asleep. Work autonomously until:
- Success criteria met → package results
- Budget exhausted → write final summary
- Strategy queue empty → attempt up to 3 combinations, then stop
- Manually interrupted
```

**Show the completed spec to the user for approval before launching.** The user should read it and confirm it matches their intent.

## Step 3: Launch the Agent

Only after user approves the spec:

```
Agent tool:
  subagent_type: "research:autonomous-researcher"
  prompt: "Read program.md in [project root] and execute the research loop autonomously.
           Start with the setup steps, then enter the experiment loop.
           Log all results to results.tsv and research-log.md."
  run_in_background: true
```

For overnight runs, also consider:
- **tmux session** for persistence: `tmux new-session -d -s research`
- **Multiple parallel agents** for independent strategy tracks (use different branches)

## Step 4: Morning Review

When the user returns, help them review:
1. Read `research-log.md` for the narrative
2. Read `results.tsv` for structured data
3. Identify the best strategy and its evidence
4. Decide next steps: refine the winner, try new directions, or ship

## Examples

### Example 1: Karpathy-style Training Loop
```
Metric: val_bpb (lower is better)
Baseline: 0.998
Threshold: any improvement
Protocol: `uv run train.py > run.log 2>&1`
Extract: `grep "^val_bpb:" run.log`
Modifiable: train.py (architecture, optimizer, hyperparams)
Read-only: prepare.py (data, evaluation)
Budget: infinite (run until killed)
Strategy: hill-climb
Time per run: 5 minutes
Cost per run: $0 (local GPU)
```

### Example 2: Red-Team Sabotage
```
Metric: effectiveness × stealth (dual objective)
Baseline: 0% effectiveness, unknown stealth
Threshold: results cross direction threshold AND <50% auditor detection
Protocol: modify code → uv run python run_evaluation.py → run auditor via API
Extract: printed summary table + auditor JSON output
Modifiable: evaluation code, data generation, PAPER.md Section 3 + Appendix A
Read-only: PAPER.md Sections 1-2, honest codebase
Budget: $200 total, max 5 runs per idea
Strategy: phased (cheap eval-only first, then expensive data-gen)
Time per run: minutes (Phase 1) to hours (Phase 2)
Cost per run: $0.10 (Phase 1) to $20 (Phase 2)
```

### Example 3: Optimizer Search (Simply-style)
```
Metric: final train_loss (lower is better)
Baseline: Adam default loss (run first)
Threshold: any improvement over Adam
Protocol: `python -m simply.main --experiment_config <name> --experiment_dir /tmp/<name>`
Extract: `cat /tmp/<name>/final_result.json | jq .train_loss`
Modifiable: simply/utils/optimizers.py, simply/config_lib.py
Read-only: model architecture, data pipeline
Budget: 15 experiments or 10 new optimizers
Strategy: batch (propose 3 per round)
Time per run: ~30 seconds (CPU test config)
Cost per run: $0 (CPU)
```
