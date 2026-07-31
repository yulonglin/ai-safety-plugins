#!/usr/bin/env python3
"""Build a known-positive/known-negative set from the LLM hook's own log, then ask:
can ANY deterministic pattern separate them?

Validating a detector requires known positives (standard methodology). The hook's
log gives us exactly that: each REVIEWING line records the payload it saw, and the
following verdict line records whether it found something. Payloads are truncated
in the log, so we key them back to the full command text in the transcript corpus.

Output: (a) precision/recall of a broad candidate-signal battery on genuine findings,
(b) the taxonomy of what genuine findings actually are — which is what the skill's
rubric needs to cover.

READ THIS BEFORE QUOTING ANY NUMBER THIS SCRIPT PRINTS. The result is
INCONCLUSIVE and was not used to justify retiring the hook:

  - The positive labels come from the hook's own verdicts, and the `else:`
    branch counts anything that is not literally "OK" as a finding. That
    sweeps in the confusion mode ("I can't execute shell commands"). The
    STRICT set — verdicts naming a recognised failure mode — is roughly an
    order of magnitude smaller, ~19 payloads, far too few to separate signal
    from a ~4.5% base fire rate.
  - The direction of the labelling bias is NOT established, so contamination
    makes the estimate unreliable rather than conservative.
  - The source log self-trims at 500KB, so the corpus shifts between runs.
    One pass gave 213 positives / 528 negatives; a later pass over the trimmed
    log gave 157 / 265. Any figure here is window-dependent.

The decision to drop tripwires rests on `analysis_tripwire_measure.py`, whose
zero-fire result depends on no labelling at all.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

LOG = Path.home() / ".cache" / "claude" / "research-methodology-reviewer.log"
PROJECTS = Path.home() / ".claude" / "projects"
OUT = Path("/tmp/claude/ef9473cf-known-positives.txt")

TS = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
RE_REVIEW = re.compile(rf"^({TS}) REVIEWING: (\w+) — (.*)$")
RE_VERDICT = re.compile(rf"^({TS}) (OK|NUDGE): (.*)$")


def parse_log():
    """Yield (tool, payload_prefix, verdict_kind, verdict_text)."""
    pending = None
    entries = []
    with open(LOG, "r", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = RE_REVIEW.match(line)
            if m:
                pending = (m.group(2), m.group(3))
                continue
            m = RE_VERDICT.match(line)
            if m and pending:
                kind, text = m.group(2), m.group(3)
                # The OK-gate bug: only an EXACT "OK" was suppressed, so a NUDGE
                # whose text merely starts with OK was printed but is a non-finding.
                stripped = text.strip()
                if kind == "OK":
                    label = "suppressed_ok"
                elif stripped.upper() == "OK" or re.match(r"^OK\b", stripped):
                    label = "leaked_ok"          # printed, but no finding
                else:
                    label = "genuine"            # printed, real concern
                entries.append((pending[0], pending[1], label, text))
                pending = None
    return entries


def payload_key(s, n=90):
    """Normalised prefix used to join log lines to full transcript payloads."""
    # log stores the tool input as a JSON-ish blob; pull the command/content value
    m = re.search(r'"(?:command|content|new_string)":\s*"(.*)', s, re.DOTALL)
    body = m.group(1) if m else s
    body = body.replace('\\n', '\n').replace('\\"', '"')
    return " ".join(body.split())[:n]


def index_transcripts():
    """Map normalised payload prefix -> full payload text."""
    idx = {}
    for t in sorted(PROJECTS.glob("*/*.jsonl")):
        try:
            with open(t, "r", errors="replace") as fh:
                for line in fh:
                    if '"tool_use"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    msg = rec.get("message")
                    if not isinstance(msg, dict):
                        continue
                    content = msg.get("content")
                    if not isinstance(content, list):
                        continue
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_use":
                            continue
                        inp = b.get("input")
                        if not isinstance(inp, dict):
                            continue
                        for field in ("command", "content", "new_string"):
                            v = inp.get(field)
                            if isinstance(v, str) and len(v) > 20:
                                k = " ".join(v.split())[:90]
                                idx.setdefault(k, v)
        except OSError:
            continue
    return idx


# A deliberately BROAD battery — if even this can't cover the genuine findings,
# the conclusion is about the signal, not about regex craftsmanship.
SIGNALS = {
    "hardcoded_expected": re.compile(r"\b(?:expected|EXPECTED)[\w_]*\s*=\s*[\[{(]?\s*[-\d'\"]", re.I),
    "outcome_filter": re.compile(r"\b(?:filter|select|where|if)\b[^\n]{0,80}\b(?:stop_reason|status|result|outcome|correct|passed|success)\b", re.I),
    "label_eq_formula": re.compile(r"\b(?:label|y|pass|fail|is_\w+)\s*=\s*[^=\n]*[=<>]=", re.I),
    "score_assign": re.compile(r"\b[a-z_]*(?:score|acc|auc|prob)[a-z_]*\s*=", re.I),
    "threshold_word": re.compile(r"\b(?:threshold|thresh|cutoff|tau)\b", re.I),
    "test_word": re.compile(r"\btest\b", re.I),
    "hardcoded_map": re.compile(r"\{\s*[\"'][\w.-]+[\"']\s*:\s*[\"'][\w.-]+[\"']\s*,", re.I),
    "dropna_or_drop": re.compile(r"\.(?:dropna|drop|query|loc\[)", re.I),
}


def main():
    if not LOG.exists():
        print(f"FATAL: {LOG} missing", file=sys.stderr)
        return 1

    entries = parse_log()
    dist = Counter(e[2] for e in entries)

    print("building transcript index (this is the slow part)...", file=sys.stderr)
    idx = index_transcripts()

    joined = {"genuine": [], "leaked_ok": [], "suppressed_ok": []}
    unmatched = Counter()
    for tool, prefix, label, verdict in entries:
        k = payload_key(prefix)
        full = None
        if k in idx:
            full = idx[k]
        else:
            for ik, iv in idx.items():
                if k and (ik.startswith(k) or k.startswith(ik[:60])):
                    full = iv
                    break
        if full is None:
            unmatched[label] += 1
            continue
        joined[label].append((full, verdict))

    lines = []
    lines.append("=== hook log verdict distribution ===")
    for k, v in dist.most_common():
        lines.append(f"  {k:16s} {v:5d}")
    lines.append(f"  TOTAL            {sum(dist.values()):5d}")
    lines.append("")
    lines.append("=== joined to full transcript payloads ===")
    for k in ("genuine", "leaked_ok", "suppressed_ok"):
        lines.append(f"  {k:16s} matched={len(joined[k]):5d}  unmatched={unmatched[k]}")
    lines.append("")

    pos = [f for f, _ in joined["genuine"]]
    neg = [f for f, _ in joined["leaked_ok"]] + [f for f, _ in joined["suppressed_ok"]]
    lines.append(f"known positives: {len(pos)}   known negatives: {len(neg)}")
    lines.append("")
    lines.append("=== can a deterministic signal separate them? ===")
    lines.append(f"{'signal':22s} {'hit@pos':>8s} {'hit@neg':>8s} {'recall':>8s} {'precision':>10s}")
    for name, rx in SIGNALS.items():
        tp = sum(1 for p in pos if rx.search(p))
        fp = sum(1 for n in neg if rx.search(n))
        rec = (100.0 * tp / len(pos)) if pos else 0.0
        prec = (100.0 * tp / (tp + fp)) if (tp + fp) else 0.0
        lines.append(f"{name:22s} {tp:8d} {fp:8d} {rec:7.1f}% {prec:9.1f}%")

    if pos:
        covered = sum(1 for p in pos if any(rx.search(p) for rx in SIGNALS.values()))
        cov_n = sum(1 for n in neg if any(rx.search(n) for rx in SIGNALS.values()))
        lines.append("")
        lines.append(f"UNION of all signals: covers {covered}/{len(pos)} positives "
                     f"({100.0*covered/len(pos):.1f}% recall), "
                     f"fires on {cov_n}/{len(neg)} negatives "
                     f"({100.0*cov_n/max(1,len(neg)):.1f}% of non-findings)")

    lines.append("")
    lines.append("=== taxonomy of GENUINE findings (what the skill rubric must cover) ===")
    themes = Counter()
    theme_pats = {  # also used below to build the strict positive set
        "circular reasoning / outcome->label": r"circular|outcome[- ]to[- ]label|outcome-based",
        "hardcoded expected values": r"hardcoded|hard-coded|expected value",
        "post-hoc filtering / cherry-pick": r"post[- ]hoc|cherry[- ]pick|filtering",
        "data leakage": r"leakage|leak\b",
        "confounded comparison": r"confound",
        "p-hacking / threshold shopping": r"p-hack|multiple compar|threshold",
        "reporting bias": r"reporting bias|selectiv",
    }
    for _, v in joined["genuine"]:
        for theme, pat in theme_pats.items():
            if re.search(pat, v, re.I):
                themes[theme] += 1
    for theme, n in themes.most_common():
        lines.append(f"  {n:5d}  {theme}")

    # --- STRICT positive set -------------------------------------------------
    # The `else:` branch above labels anything that isn't an exact/prefix "OK" as
    # genuine, which sweeps in the confusion mode ("I can't execute shell
    # commands", "I don't see the output"). Those are NOT methodological
    # findings, so the loose set inflates the denominator and makes the recall
    # number unreliable — NOT conservative, since the direction of the bias
    # depends on whether the union's hits sit inside the real findings.
    # Re-run the same battery against only verdicts that name a known failure
    # mode, and report both numbers.
    pos_strict = [f for f, v in joined["genuine"]
                  if any(re.search(p, v, re.I) for p in theme_pats.values())]
    lines.append("")
    lines.append("=== STRICT positive set (verdict names a known failure mode) ===")
    lines.append(f"strict positives: {len(pos_strict)}  (of {len(pos)} loose)")
    if pos_strict:
        lines.append(f"{'signal':22s} {'hit@pos':>8s} {'recall':>8s}")
        for name, rx in SIGNALS.items():
            tp = sum(1 for p in pos_strict if rx.search(p))
            lines.append(f"{name:22s} {tp:8d} {100.0*tp/len(pos_strict):7.1f}%")
        cov_s = sum(1 for p in pos_strict if any(rx.search(p) for rx in SIGNALS.values()))
        lines.append("")
        lines.append(f"UNION on STRICT positives: {cov_s}/{len(pos_strict)} "
                     f"({100.0*cov_s/len(pos_strict):.1f}% recall), "
                     f"against {100.0*cov_n/max(1,len(neg)):.1f}% fire rate on negatives")

    lines.append("")
    lines.append("=== 8 sample GENUINE verdicts (verbatim, for rubric design) ===")
    for _, v in joined["genuine"][:8]:
        lines.append(f"  - {' '.join(v.split())[:260]}")

    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
