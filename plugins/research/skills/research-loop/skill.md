---
name: research-loop
description: Set up and launch an autonomous research loop. Creates a program.md spec from user's research goal, then dispatches an autonomous-researcher agent to execute it overnight. Use when the user wants to automate research iteration — "run experiments overnight", "automate this research", "set up an autonomous loop", "research loop", "run while I sleep".
---

# Research Loop Setup

Set up an autonomous experiment loop that runs unattended. This skill creates the spec and launches the agent.

## When to Use

- User has a **measurable metric** to optimize (loss, accuracy, F1, detection rate, etc.)
- User has an **experiment protocol** (a command or pipeline that produces results)
- User wants to run **unattended** (overnight, while away)

## Step 1: Gather Requirements

Before creating the spec, establish these with the user:

### Required
1. **What metric are you optimizing?** (name, direction: lower/higher is better, threshold for "success")
2. **How do you run one experiment?** (the command, time per run, cost per run)
3. **What can the agent modify?** (which files, what kinds of changes)
4. **What is read-only?** (evaluation harness, data format, dependencies)
5. **Budget** (max time, max cost, max experiments)

### Optional (with defaults)
6. **Loop strategy?** hill-climb (default), sprint, or batch
7. **Strategy queue?** Existing ideas to try, or should the agent brainstorm?
8. **Termination?** Infinite until killed (default), or stop after N experiments?
9. **Multi-model brainstorming?** Use `~/writing/brainstorming/` if available?
10. **Git strategy?** Branch-per-experiment (default) or linear commit/revert?

## Step 2: Create the Spec

Write a `program.md` in the project root. Use this template structure:

```markdown
# [Title]: Autonomous Research Loop

You are an autonomous research agent. [One sentence about the goal.]

## Objective
- **Metric:** [name] ([lower/higher] is better)
- **Threshold:** [number] (success criterion)
- **Baseline:** [current value]

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
- **Reserve:** [amount for final validation]
- **Stop when:** [condition]

## Constraints
- [List all constraints: max runs per idea, immutable files, etc.]

## NEVER STOP
[Instructions for autonomous operation — standard from autonomous-researcher agent]
```

## Step 3: Launch the Agent

Dispatch the `autonomous-researcher` agent with the spec:

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
Protocol: `uv run train.py > run.log 2>&1`
Modifiable: train.py (architecture, optimizer, hyperparams)
Read-only: prepare.py (data, evaluation)
Budget: infinite (run until killed)
Strategy: hill-climb
Time per run: 5 minutes
```

### Example 2: Red-Team Sabotage (this session's task)
```
Metric: effectiveness × stealth (dual objective)
Protocol: modify code → run eval → run auditor
Modifiable: evaluation code, data generation, PAPER.md Section 3 + Appendix A
Read-only: PAPER.md Sections 1-2, honest codebase
Budget: $200
Strategy: phased (cheap eval-only first, then expensive data-gen)
Time per run: minutes (Phase 1) to hours (Phase 2)
```

### Example 3: Optimizer Search (Simply-style)
```
Metric: final train_loss (lower is better)
Protocol: `python -m simply.main --experiment_config <name> --experiment_dir /tmp/<name>`
Modifiable: simply/utils/optimizers.py, simply/config_lib.py
Read-only: model architecture, data pipeline
Budget: 15 experiments or 10 new optimizers
Strategy: batch (propose 3 per round)
Time per run: ~30 seconds (CPU test config)
```
