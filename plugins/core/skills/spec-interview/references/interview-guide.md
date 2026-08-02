# Interview Guide

## Question Categories

**Core — always cover these** (they map directly to the spec's three mandatory sections):

### 1. Core Functionality (→ Overview)
- What's the primary user action?
- What state changes occur?
- What's the expected output/result?

### 2. Requirements (→ Requirements)
- What must the system do? (MUST)
- What's recommended but not required? (SHOULD)

### 3. Testing (→ Acceptance Criteria)
- How do we verify correctness?
- What's hard to test?

**Conditional — only probe if the answer would be non-obvious for this feature.** Skip a category outright if it clearly doesn't apply rather than asking a pro-forma question and writing "N/A" in the spec.

### 4. User Interactions
- What's the unhappy path UX, if there is one?

### 5. Data Model
- What data is created/modified/deleted, if the schema changes?

### 6. Error Handling & Edge Cases
- What external dependencies can fail? What happens with empty/null inputs or concurrent operations — only if genuinely ambiguous?

### 7. Integration
- What existing systems does this touch, if any?

### 8. Performance & Security
- Only ask for numbers if there's a real target (e.g. "must handle current load ×3") — don't manufacture a latency budget for a feature that doesn't need one

### 9. Rollout
- Migration/feature-flag/rollback plan — only for changes that touch production state or existing users

## Example Non-Obvious Questions

Instead of asking obvious questions, probe deeper:

**Bad**: "What should the feature do?"
**Good**: "When a user is mid-action and loses connection, should we auto-save, discard, or prompt on reconnect?"

**Bad**: "Should it be fast?"
**Good**: "If this call takes >2s, should we show a spinner, optimistic UI, or block interaction?"

**Bad**: "What errors can happen?"
**Good**: "If the downstream API returns a 500 during step 3 of 5, do we rollback steps 1-2 or leave partial state?"

**Bad**: "Who uses this?"
**Good**: "If an admin and regular user try this simultaneously on the same resource, who wins?"

## Completion Checklist

Before writing the spec, the three core sections must be solid:

- [ ] Overview: what + why is unambiguous
- [ ] Requirements: MUST/SHOULD behaviors are concrete, not vague
- [ ] Acceptance Criteria: someone else could verify "done" without asking you

Everything else is judgment-call, not checklist — include a section only where category 4-9 above surfaced a real, non-obvious answer.
