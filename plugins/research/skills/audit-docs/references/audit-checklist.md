# Documentation Audit Checklist

## CLAUDE.md

- [ ] CLI examples still valid? (run a dry check against current Hydra configs)
- [ ] File paths correct? (`src/`, `docs/`, `configs/` references still exist)
- [ ] Detection methods table up to date?
- [ ] Dataset sample counts match current data?
- [ ] Quick Reference commands work with current config names?
- [ ] Key Results section matches latest paper numbers?
- [ ] Terminology table current?

## CLI_REFERENCE.md

- [ ] All example commands use current config names from `src/detection_game/configs/`?
- [ ] Flag names match current Hydra schema?
- [ ] Output paths in examples match actual output structure?
- [ ] New classifiers or analysis scripts documented?

## Experiment Records (docs/experiments/)

- [ ] Any `status: active` experiments with no log entries in 2+ weeks? → Ask user to update
- [ ] Any `status: planned` experiments that were actually run? → Update status
- [ ] Completed experiments have results and analysis filled in?
- [ ] README.md index (if exists) matches actual experiment files?

## AGENTS.md

- [ ] Reflects current project structure?
- [ ] Agent descriptions match available agents?
- [ ] Delegation patterns still accurate?

## RESEARCH_SPEC.md

- [ ] Priority levels (P0-P3) still reflect current focus?
- [ ] Completed items marked as done?
- [ ] New research directions captured?
- [ ] Timeline/milestones still relevant?

## Detection Method Docs (docs/methods/)

- [ ] Hyperparameters match current code defaults?
- [ ] New methods added since last audit?
- [ ] Removed or deprecated methods cleaned up?

## Other

- [ ] `docs/core/TROUBLESHOOTING.md` — any resolved issues still listed as open?
- [ ] `docs/core/STATISTICAL_ANALYSIS.md` — metrics descriptions match `metrics.py`?
- [ ] `docs/core/REPORTING_CHECKLIST.md` — standards still current?
- [ ] Any new scripts in `scripts/` without documentation?
