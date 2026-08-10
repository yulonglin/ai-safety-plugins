"""Group equivalent labels across judges, using a dedicated merge judge.

Two design choices worth defending:

**Complete-link, not connected components.** Pairwise LLM equivalence is not
transitive. Under connected components a single generous edge chains unrelated
constructs into one blob, and the blob grows monotonically with corpus size. A
label therefore joins the first existing group only if it is equivalent to
*every* current member.

**Order is fixed, so reruns are byte-identical.** Labels are visited in sorted
canonical order and members are sorted lexicographically, so there is no RNG in
this path and nothing to seed. Combined with the append-only pairwise cache, a
second run over the same labels issues zero API calls and writes the same bytes.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import combinations
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from transcript_judge.models import ClusterAssignment, LabelRow, PairVerdict
from transcript_judge.parse import parse_response
from transcript_judge.persist import append_jsonl, read_jsonl
from transcript_judge.providers import validate_params

MERGE_FIELD = "equivalent"


class ClusterStats(BaseModel):
    """Counters for one `cluster_labels` invocation.

    The token sums cover the calls *this* invocation made, so a fully cached
    rerun reports zero -- correctly, because it spent nothing. They are not the
    merge cost of the run: that is reconstructed by summing `tokens_in` /
    `tokens_out` over the append-only pairwise cache, which is the only record
    that survives a second invocation.
    """

    merge_prompt_sha256: str = ""
    model_id: str = ""
    n_distinct_labels: int = 0
    n_pairs: int = 0
    n_pairs_cached: int = 0
    n_clusters: int = 0
    contradictory_triads: int = 0
    parse_failures: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    contradictions: list[dict[str, str]] = Field(default_factory=list)


class MergeDecision(BaseModel):
    """One merge-judge call's outcome, before it is written as a cache row."""

    equivalent: bool = False
    rationale: str = ""
    quote: str | None = None
    parse_ok: bool = True
    tokens_in: int = 0
    tokens_out: int = 0


def canonicalize(label: str) -> str:
    """Casefold, treat underscores as spaces, collapse internal whitespace.

    Field names arrive as ``mentions_being_evaluated`` and free-text labels as
    ``Mentions  being evaluated``; these are the same construct and should not
    cost an API call to discover.
    """
    return " ".join(label.replace("_", " ").casefold().split())


def _pair_key(a: str, b: str) -> tuple[str, str]:
    """Unordered pairs are stored sorted, so (a,b) and (b,a) share a cache row."""
    return (a, b) if a <= b else (b, a)


def load_cache(path: Path) -> dict[tuple[str, str, str, str], bool]:
    """Read cached verdicts, keyed on the pair plus the prompt sha and model.

    Only `equivalent` is read, because only the verdict feeds the grouping.
    Rows written before verdicts carried their evidence therefore still load --
    they simply cannot be reviewed, which is what `parse_ok`, `rationale` and
    the token fields exist to prevent going forward.
    """
    cache: dict[tuple[str, str, str, str], bool] = {}
    for row in read_jsonl(path):
        cache[(row["canon_a"], row["canon_b"], row["merge_prompt_sha256"], row["model_id"])] = bool(
            row["equivalent"]
        )
    return cache


def cache_token_totals(path: Path, *, merge_prompt_sha256: str, model_id: str) -> dict[str, int]:
    """Merge-path tokens across every call cached for one cell.

    Unlike `ClusterStats`, this survives reruns: a warm invocation issues no
    calls, so only the rows on disk can say what the merge path cost.

    The cell is a required argument rather than an optional filter. One cache
    file holds rows for every prompt sha and model ever run against it, so an
    unfiltered sum would attribute one cell's spend to another -- the same
    pooling defect this project reports elsewhere, reintroduced inside the fix
    for the accounting defect. Rows predating token accounting contribute 0 and
    are counted in `rows_missing` rather than silently reducing the total.
    """
    tokens_in = tokens_out = rows = missing = 0
    for row in read_jsonl(path):
        if row["merge_prompt_sha256"] != merge_prompt_sha256 or row["model_id"] != model_id:
            continue
        rows += 1
        if "tokens_in" not in row:
            missing += 1
        tokens_in += int(row.get("tokens_in", 0))
        tokens_out += int(row.get("tokens_out", 0))
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "rows": rows,
        "rows_missing": missing,
    }


def build_merge_prompt(a: str, b: str) -> str:
    return (
        f"Label A:\n{a}\n\nLabel B:\n{b}\n\nDo these two labels name the same underlying construct?"
    )


async def _ask_merge_judge(
    *,
    a: str,
    b: str,
    client: Any,
    prompt_text: str,
    model_id: str,
    params: dict[str, Any],
    stats: ClusterStats,
) -> MergeDecision:
    """Ask whether two labels name one construct, returning the whole finding.

    The rationale and quote come back with the verdict rather than being
    discarded: this decision is about to be cached, and a cached bool with no
    evidence is unreviewable forever after.
    """
    completion = await client.complete(
        system=prompt_text,
        user=build_merge_prompt(a, b),
        model_id=model_id,
        params=params,
    )
    # Counted before parsing: an unreadable response was still billed.
    stats.tokens_in += completion.tokens_in
    stats.tokens_out += completion.tokens_out
    decision = MergeDecision(tokens_in=completion.tokens_in, tokens_out=completion.tokens_out)

    result = parse_response(completion.text)
    if hasattr(result, "findings"):
        for finding in result.findings:
            if finding.field == MERGE_FIELD:
                return decision.model_copy(
                    update={
                        "equivalent": bool(finding.value),
                        "rationale": finding.rationale,
                        "quote": finding.quote,
                    }
                )
    stats.parse_failures += 1
    return decision.model_copy(update={"parse_ok": False})


def _find_triads(canon: list[str], verdicts: dict[tuple[str, str], bool]) -> list[dict[str, str]]:
    """Two positive edges plus a negative edge closing the triangle.

    Recorded rather than resolved: a triad is the merge judge disagreeing with
    itself, and silently picking a winner would hide that.
    """
    found: list[dict[str, str]] = []
    for a, b, c in combinations(canon, 3):
        ab = verdicts.get(_pair_key(a, b), False)
        bc = verdicts.get(_pair_key(b, c), False)
        ac = verdicts.get(_pair_key(a, c), False)
        edges = [ab, bc, ac]
        if edges.count(True) == 2:
            missing = "ac" if not ac else ("bc" if not bc else "ab")
            found.append({"a": a, "b": b, "c": c, "negative_edge": missing})
    return found


async def cluster_labels(
    *,
    labels: list[LabelRow],
    cache_path: Path,
    merge_prompt_text: str,
    merge_prompt_sha256: str,
    model_id: str,
    client: Any = None,
    params: dict[str, Any] | None = None,
    client_factory: Callable[[str], Any] | None = None,
    provider: str = "anthropic",
) -> tuple[list[ClusterAssignment], ClusterStats]:
    """Cluster the positive, quote-grounded labels."""
    # No temperature: `claude-sonnet-5` rejects it outright (HTTP 400), and this
    # fallback fires only after the judge fan-out has already been paid for.
    params = params or {"max_tokens": 512}
    # After the fallback, not before it: the default is a param dict like any
    # other, and the temperature bug lived in exactly this line.
    validate_params(provider, params, source="cluster_labels")

    stats = ClusterStats(merge_prompt_sha256=merge_prompt_sha256, model_id=model_id)

    eligible = [lab for lab in labels if lab.value and lab.evidence_mode == "positive_quote"]
    by_canon: dict[str, list[LabelRow]] = {}
    for label in eligible:
        by_canon.setdefault(canonicalize(label.label), []).append(label)

    canon = sorted(by_canon)
    stats.n_distinct_labels = len(canon)

    cache = load_cache(cache_path)
    verdicts: dict[tuple[str, str], bool] = {}

    if len(canon) > 1:
        if client is None and client_factory is not None:
            client = client_factory(provider)

        for a, b in combinations(canon, 2):
            key = _pair_key(a, b)
            cache_key = (key[0], key[1], merge_prompt_sha256, model_id)
            stats.n_pairs += 1

            if cache_key in cache:
                stats.n_pairs_cached += 1
                verdicts[key] = cache[cache_key]
                continue

            decision = await _ask_merge_judge(
                a=key[0],
                b=key[1],
                client=client,
                prompt_text=merge_prompt_text,
                model_id=model_id,
                params=params,
                stats=stats,
            )
            verdicts[key] = decision.equivalent
            append_jsonl(
                cache_path,
                PairVerdict(
                    canon_a=key[0],
                    canon_b=key[1],
                    merge_prompt_sha256=merge_prompt_sha256,
                    model_id=model_id,
                    equivalent=decision.equivalent,
                    rationale=decision.rationale,
                    quote=decision.quote,
                    parse_ok=decision.parse_ok,
                    tokens_in=decision.tokens_in,
                    tokens_out=decision.tokens_out,
                ).model_dump(),
            )

    triads = _find_triads(canon, verdicts)
    stats.contradictory_triads = len(triads)
    stats.contradictions = triads

    groups: list[list[str]] = []
    for label in canon:
        for group in groups:
            if all(verdicts.get(_pair_key(label, member), False) for member in group):
                group.append(label)
                break
        else:
            groups.append([label])

    ordered = sorted((sorted(g) for g in groups), key=lambda g: g[0])
    assignments = [
        ClusterAssignment(
            cluster_id=i,
            canonical_label=members[0],
            members=members,
            label_ids=sorted(lab.label_id for member in members for lab in by_canon[member]),
        )
        for i, members in enumerate(ordered)
    ]
    stats.n_clusters = len(assignments)
    return assignments, stats
