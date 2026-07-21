# Spec Template

Three sections carry the spec. Everything else is optional — include only if it earns its place, and delete the section entirely if it doesn't apply. Never fill an unused section with "N/A" / "None" / "TBD".

```markdown
# Specification: [Feature Name]

**Created**: [Date] · **Status**: Draft

## Overview
[1-3 sentences: what this does, why it exists, who asked for it]

## Requirements
- **[REQ-001]** The system MUST [required behavior]
- **[REQ-002]** The system SHOULD [recommended behavior]

## Acceptance Criteria
- [ ] **AC-1**: Given [context], when [action], then [expected result]
- [ ] **AC-2**: Given [context], when [action], then [expected result]
```

Add only if it earns its place — a real, non-obvious answer, not a placeholder:

```markdown
## Design
[Architecture, data model, or technical decisions worth recording — only if non-obvious]

## Edge Cases & Non-Functional Requirements
| Scenario | Handling |
|----------|----------|
| [Edge case] | [How handled] |

[Performance/security/reliability targets, only if there's a concrete number — "< 200ms p99", not "fast"]

## Out of Scope
- [Explicitly excluded item — only if scope creep is a real risk]

## Open Questions
- [ ] [Unresolved question — delete this section if there are none]
```

## Writing Guidelines

- The three core sections are mandatory; everything below the divider is opt-in per spec
- Be specific: "< 200ms p99" not "fast"
- Use MUST/SHOULD per RFC 2119 (drop MAY — if it's truly optional, it's not a requirement)
- Enumerable items (edge cases, decisions, errors) → table, not prose
- Don't restate the section heading in prose ("This section describes...")
- Omit a section rather than writing "N/A"
