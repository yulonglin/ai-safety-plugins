# Research Interview Guide

**Core — always cover these** (categories 1-4, 8, 9, 12; they map directly to the spec's four mandatory sections: Overview, Research Question & Hypotheses, Requirements, Acceptance Criteria). **Conditional — the rest** (5-7, 10, 11, 13-15): only probe if the answer would be non-obvious for this study. Skip a category outright if it clearly doesn't apply rather than asking a pro-forma question and writing "N/A" in the spec. Categories 13-14 in particular are usually just "see `docs/research-methodology.md` / `docs/async-and-performance.md`" — don't re-derive standard caching/concurrency/retry patterns per spec; only ask if this experiment needs something nonstandard.

## 1. Research Question & Motivation
- What exactly are you investigating?
- Why does this matter?
- What gap in knowledge does this address?
- What are the practical implications if your hypothesis is correct/incorrect?

## 2. Hypotheses & Falsification
- What are your explicit hypotheses?
- What specific results would falsify each hypothesis?
- What results would support (but not prove) your hypothesis?
- Are your hypotheses testable with the available resources?

## 3. Independent Variables
- What are you manipulating or varying?
- What are the levels/values for each variable?
- Why these specific values?
- Which variables are most critical to test? (drill down on these)

## 4. Dependent Variables & Metrics
- What are you measuring?
- What exact metrics? (e.g., "exact_match on MMLU", not just "accuracy")
- How will you operationalize abstract concepts into measurable quantities?
- Are these metrics validated in prior work?

## 5. Control Variables
- What must stay constant across all conditions?
- Which variables could introduce noise if not controlled?
- How will you ensure consistency?

## 6. Confounding Variables
- What alternative explanations could account for your results?
- Which confounds are most plausible?
- How will you rule them out? (experimental controls, statistical methods, etc.)
- What assumptions are you making?

## 7. Models & Hyperparameters
- Which models are you using? Why?
- What hyperparameters? (learning rate, temperature, context length, etc.)
- Have you justified each hyperparameter choice?
- Are you using default values? If so, why are they appropriate?

## 8. Baselines & Comparisons
- What are you comparing against?
- Why are these baselines fair/strong?
- Are you including a naive baseline (random, majority class, etc.)?
- Are you comparing to state-of-the-art?

## 9. Datasets
- Which datasets? Versions?
- Train/val/test split sizes and selection method?
- Any preprocessing steps?
- Are datasets publicly available and reproducible?
- Potential data leakage or contamination concerns?

## 10. Graphs & Visualizations
- What plots will demonstrate the key findings?
- For each plot: X-axis? Y-axis? Grouping/colors? Error bars?
- What story does each visualization tell?
- Are these the minimal sufficient set of plots?

## 11. Resources & Validation
- CPU/GPU/memory requirements?
- Estimated API cost (if using LLM APIs)?
- Time estimate for full run?
- **[INLINE VALIDATION]**: Check system resources, warn if insufficient
  - Run: `sysctl hw.physicalcpu hw.memsize` (macOS) or `nproc && free -h` (Linux)
  - Compare to requirements, show mismatch clearly

## 12. Sample Size & Power
- How many samples/trials?
- What is the minimum detectable effect size?
- Statistical significance threshold (α, typically p<0.05)?
- Statistical power (1-β, typically >0.80)?
- Is the sample size sufficient to detect meaningful differences?

## 13. Performance & Caching Strategy
- Default: standard patterns in `docs/research-methodology.md` / `docs/async-and-performance.md` apply — don't ask this unless the study needs something nonstandard (unusual cache key, atypical concurrency limit)

## 14. Error Handling & Retries
- Default: standard transient/permanent-error handling applies — only ask if this experiment has a failure mode the standard patterns don't cover

## 15. Reproducibility
- Output path is required (→ Acceptance Criteria). Seeds/code version/logging plan only if reproducibility is unusually tight for this study

---

## Interview Flow

1. **Start high-level**: Get the big picture first
2. **Drill down on critical decisions**: Spend time on variables that matter most
3. **Challenge assumptions**: "Why baseline X instead of Y?" "What if confound Z explains results?"
4. **Inline validation**: For resources, check system capabilities during interview
5. **Iterate until complete**: Don't rush; ask 2-4 focused questions per round
