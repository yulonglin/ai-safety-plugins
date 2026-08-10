"""Canonicalization, complete-link grouping, contradiction recording, cache reuse.

The merge judge is faked, but the fake returns an Anthropic-shaped payload and
that payload goes through the real parser, so a provider-shape change still
breaks these tests.
"""

from __future__ import annotations

import anyio
import pytest
from conftest import anthropic_payload, finding

from transcript_judge.cluster import (
    MERGE_FIELD,
    build_merge_prompt,
    cache_token_totals,
    canonicalize,
    cluster_labels,
    load_cache,
)
from transcript_judge.models import LabelRow
from transcript_judge.persist import append_jsonl, read_jsonl
from transcript_judge.providers import UnsupportedParamError
from transcript_judge.providers.anthropic import parse_raw as anthropic_parse_raw

MERGE_SHA = "m" * 64
MODEL = "claude-sonnet-5"


class FakeMergeClient:
    """Decides equivalence from a table of canonical pairs.

    The shared `FakeClient` keys on a rendered transcript's ``sample:`` line;
    the merge prompt starts with ``Label A:`` instead, so this path needs its
    own fake rather than a special case in the shared one.
    """

    def __init__(self, equivalent_pairs: set[tuple[str, str]], *, malformed: bool = False) -> None:
        self.equivalent_pairs = {tuple(sorted(p)) for p in equivalent_pairs}
        self.malformed = malformed
        self.calls: list[dict] = []

    async def complete(self, *, system: str, user: str, model_id: str, params: dict):
        self.calls.append({"system": system, "user": user, "model_id": model_id, "params": params})
        if self.malformed:
            # Usage is present on purpose: an unreadable response was still billed.
            return anthropic_parse_raw(
                {
                    "content": [{"type": "text", "text": "not json at all"}],
                    "usage": {"input_tokens": 5, "output_tokens": 3},
                }
            )
        lines = user.splitlines()
        a, b = lines[1], lines[4]
        verdict = tuple(sorted((a, b))) in self.equivalent_pairs
        return anthropic_parse_raw(anthropic_payload([finding(MERGE_FIELD, verdict, quote=a)]))


def label(
    text: str,
    *,
    sample: str = "log:0:1",
    judge: str = "alpha",
    model: str = MODEL,
    value: bool = True,
    evidence_mode: str = "positive_quote",
) -> LabelRow:
    return LabelRow(
        label_id=f"{text}|{sample}|{judge}|{model}",
        sample_key=sample,
        label=text,
        evidence_mode=evidence_mode,
        value=value,
        judge_name=judge,
        prompt_sha256="p" * 64,
        model_id=model,
        surface="full",
        judgement_row_id=f"{judge}.jsonl:0",
    )


def run(labels, cache_path, client, **kwargs):
    return anyio.run(
        lambda: cluster_labels(
            labels=labels,
            cache_path=cache_path,
            merge_prompt_text="Decide whether two labels name one construct.",
            merge_prompt_sha256=kwargs.pop("merge_prompt_sha256", MERGE_SHA),
            model_id=kwargs.pop("model_id", MODEL),
            client=client,
            **kwargs,
        )
    )


def test_cluster_labels_refuses_an_unsupported_param_without_calling_the_judge(tmp_path):
    """The guard lives in the library, not only in the CLI that usually calls it.

    Two distinct labels, so the merge judge would otherwise be called: asserting
    ``client.calls == []`` is what makes this a *before any network call* test
    rather than a test that an exception eventually escapes.
    """
    client = FakeMergeClient(set())
    with pytest.raises(UnsupportedParamError) as caught:
        run(
            [label("hedging"), label("unsupported confidence")],
            tmp_path / "cache.jsonl",
            client,
            params={"max_tokens": 512, "top_p": 0.9},
        )

    assert client.calls == []
    message = str(caught.value)
    assert "top_p" in message
    assert "cluster_labels" in message


def test_the_fallback_params_send_no_temperature(tmp_path):
    """The `params=None` default, exercised through a real merge call.

    `claude-sonnet-5` rejects `temperature` outright, and this fallback fires
    only once two distinct labels exist -- that is, after the judge fan-out has
    already been paid for. `max_tokens` is asserted alongside so an empty params
    dict cannot satisfy the temperature assertion vacuously.
    """
    client = FakeMergeClient(set())
    run(
        [label("hedging"), label("unsupported confidence")],
        tmp_path / "cache.jsonl",
        client,
        params=None,
    )

    assert client.calls, "no merge call was made, so this asserts nothing"
    sent = client.calls[0]["params"]
    assert "temperature" not in sent
    assert sent["max_tokens"] == 512


# --- canonicalization --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("mentions_being_evaluated", "mentions being evaluated"),
        ("Mentions  being evaluated", "mentions being evaluated"),
        ("MENTIONS_BEING_EVALUATED", "mentions being evaluated"),
        ("  mentions being   evaluated  ", "mentions being evaluated"),
        ("flags_protocol_error", "flags protocol error"),
    ],
)
def test_canonicalize_folds_case_underscores_and_whitespace(raw, expected):
    assert canonicalize(raw) == expected


def test_labels_differing_only_by_form_cost_no_api_call(tmp_path):
    client = FakeMergeClient(set())
    assignments, stats = run(
        [label("mentions_being_evaluated"), label("Mentions  being evaluated", sample="log:1:1")],
        tmp_path / "pairwise_cache.jsonl",
        client,
    )

    assert stats.n_distinct_labels == 1
    assert stats.n_pairs == 0
    assert client.calls == []
    assert len(assignments) == 1
    assert assignments[0].canonical_label == "mentions being evaluated"
    assert len(assignments[0].label_ids) == 2


# --- the merge prompt --------------------------------------------------------


def test_the_merge_prompt_carries_both_labels_and_nothing_else():
    prompt = build_merge_prompt("alpha construct", "beta construct")
    assert prompt.splitlines()[0] == "Label A:"
    assert prompt.splitlines()[1] == "alpha construct"
    assert prompt.splitlines()[4] == "beta construct"
    assert "log:" not in prompt
    assert "s0001" not in prompt


def test_the_merge_judge_is_asked_about_sorted_pairs(tmp_path):
    client = FakeMergeClient(set())
    run(
        [label("zeta thing"), label("alpha thing", sample="log:1:1")],
        tmp_path / "cache.jsonl",
        client,
    )

    (call,) = client.calls
    lines = call["user"].splitlines()
    assert (lines[1], lines[4]) == ("alpha thing", "zeta thing")


# --- complete-link grouping --------------------------------------------------


def three_labels():
    return [
        label("aaa first", sample="log:0:1"),
        label("bbb second", sample="log:1:1"),
        label("ccc third", sample="log:2:1"),
    ]


def test_complete_link_refuses_to_chain_through_a_single_generous_edge(tmp_path):
    """a~b and b~c but not a~c: connected components would return one blob."""
    client = FakeMergeClient({("aaa first", "bbb second"), ("bbb second", "ccc third")})

    assignments, stats = run(three_labels(), tmp_path / "cache.jsonl", client)

    assert [a.members for a in assignments] == [["aaa first", "bbb second"], ["ccc third"]]
    assert stats.n_clusters == 2
    assert stats.n_pairs == 3


def test_a_fully_equivalent_triple_becomes_one_cluster(tmp_path):
    client = FakeMergeClient(
        {
            ("aaa first", "bbb second"),
            ("bbb second", "ccc third"),
            ("aaa first", "ccc third"),
        }
    )

    assignments, stats = run(three_labels(), tmp_path / "cache.jsonl", client)

    assert [a.members for a in assignments] == [["aaa first", "bbb second", "ccc third"]]
    assert stats.n_clusters == 1
    assert stats.contradictory_triads == 0


def test_no_equivalence_leaves_every_label_alone(tmp_path):
    assignments, stats = run(three_labels(), tmp_path / "cache.jsonl", FakeMergeClient(set()))

    assert [a.members for a in assignments] == [["aaa first"], ["bbb second"], ["ccc third"]]
    assert stats.n_clusters == 3
    assert [a.cluster_id for a in assignments] == [0, 1, 2]


def test_a_contradictory_triad_is_recorded_not_resolved(tmp_path):
    client = FakeMergeClient({("aaa first", "bbb second"), ("bbb second", "ccc third")})

    _, stats = run(three_labels(), tmp_path / "cache.jsonl", client)

    assert stats.contradictory_triads == 1
    (triad,) = stats.contradictions
    assert (triad["a"], triad["b"], triad["c"]) == ("aaa first", "bbb second", "ccc third")
    assert triad["negative_edge"] == "ac"


def test_cluster_ids_and_members_are_sorted_so_reruns_match(tmp_path):
    client = FakeMergeClient({("aaa first", "ccc third")})

    assignments, _ = run(three_labels(), tmp_path / "cache.jsonl", client)

    assert [a.canonical_label for a in assignments] == ["aaa first", "bbb second"]
    assert assignments[0].members == ["aaa first", "ccc third"]


# --- eligibility -------------------------------------------------------------


def test_negative_labels_are_not_clustered(tmp_path):
    labels = [label("aaa first"), label("bbb second", sample="log:1:1", value=False)]

    _, stats = run(labels, tmp_path / "cache.jsonl", FakeMergeClient(set()))

    assert stats.n_distinct_labels == 1


def test_hand_validation_labels_are_not_clustered(tmp_path):
    """Their absence claims are not quote-grounded, so equivalence is unfounded."""
    labels = [
        label("aaa first"),
        label("bbb second", sample="log:1:1", evidence_mode="hand_validation"),
    ]

    _, stats = run(labels, tmp_path / "cache.jsonl", FakeMergeClient(set()))

    assert stats.n_distinct_labels == 1


def test_no_eligible_labels_yields_no_clusters(tmp_path):
    assignments, stats = run(
        [label("aaa first", value=False)], tmp_path / "cache.jsonl", FakeMergeClient(set())
    )

    assert assignments == []
    assert stats.n_clusters == 0
    assert stats.n_pairs == 0


# --- the pairwise cache ------------------------------------------------------


def test_a_second_run_over_the_same_labels_makes_no_api_calls(tmp_path):
    cache = tmp_path / "pairwise_cache.jsonl"
    pairs = {("aaa first", "bbb second")}

    first_client = FakeMergeClient(pairs)
    first_assignments, first_stats = run(three_labels(), cache, first_client)

    second_client = FakeMergeClient(pairs)
    second_assignments, second_stats = run(three_labels(), cache, second_client)

    assert len(first_client.calls) == 3
    assert second_client.calls == []
    assert second_stats.n_pairs_cached == 3
    assert first_stats.n_pairs_cached == 0
    assert [a.model_dump() for a in second_assignments] == [
        a.model_dump() for a in first_assignments
    ]


def test_the_cache_stores_one_sorted_row_per_pair(tmp_path):
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient({("aaa first", "bbb second")}))

    rows = list(read_jsonl(cache))
    assert len(rows) == 3
    assert all(row["canon_a"] <= row["canon_b"] for row in rows)
    assert all(row["merge_prompt_sha256"] == MERGE_SHA for row in rows)
    assert all(row["model_id"] == MODEL for row in rows)
    assert {(r["canon_a"], r["canon_b"]): r["equivalent"] for r in rows} == {
        ("aaa first", "bbb second"): True,
        ("aaa first", "ccc third"): False,
        ("bbb second", "ccc third"): False,
    }


def test_load_cache_keys_on_the_full_quadruple(tmp_path):
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient(set()))

    loaded = load_cache(cache)
    assert loaded[("aaa first", "bbb second", MERGE_SHA, MODEL)] is False
    assert ("aaa first", "bbb second", MERGE_SHA, "some-other-model") not in loaded


def test_a_different_model_is_a_cache_miss(tmp_path):
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient(set()))

    second = FakeMergeClient(set())
    _, stats = run(three_labels(), cache, second, model_id="openai/gpt-5.6-sol")

    assert len(second.calls) == 3
    assert stats.n_pairs_cached == 0
    # Both models' verdicts now live in the one append-only file.
    assert len(list(read_jsonl(cache))) == 6


def test_a_reworded_merge_prompt_is_a_cache_miss(tmp_path):
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient(set()))

    second = FakeMergeClient(set())
    _, stats = run(three_labels(), cache, second, merge_prompt_sha256="d" * 64)

    assert len(second.calls) == 3
    assert stats.n_pairs_cached == 0


def test_an_absent_cache_file_is_not_an_error(tmp_path):
    assert load_cache(tmp_path / "never-written.jsonl") == {}


# --- parse failures ----------------------------------------------------------


def test_merge_judge_parse_failures_are_counted_and_default_to_not_equivalent(tmp_path):
    client = FakeMergeClient(set(), malformed=True)

    assignments, stats = run(three_labels(), tmp_path / "cache.jsonl", client)

    assert stats.parse_failures == 3
    assert stats.n_clusters == 3
    assert [a.members for a in assignments] == [["aaa first"], ["bbb second"], ["ccc third"]]


# --- cached verdicts carry their own evidence --------------------------------


def test_a_cached_verdict_records_the_rationale_and_quote_it_was_decided_on(tmp_path):
    """Read back off disk, not off the in-memory object that was just populated.

    A cache row replays forever, so ``equivalent: true`` on its own is a verdict
    nobody can review. The strings are asserted verbatim against what the judge
    returned and *together with* `equivalent`, because a row carrying the
    rationale for the opposite decision would satisfy either assertion alone.
    """
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient({("aaa first", "bbb second")}))

    rows = {(r["canon_a"], r["canon_b"]): r for r in read_jsonl(cache)}
    positive = rows[("aaa first", "bbb second")]
    assert (positive["equivalent"], positive["rationale"], positive["quote"]) == (
        True,
        "deliberating about equivalent",
        "aaa first",
    )
    negative = rows[("bbb second", "ccc third")]
    assert (negative["equivalent"], negative["rationale"], negative["quote"]) == (
        False,
        "deliberating about equivalent",
        "bbb second",
    )


def test_a_judged_negative_is_not_confusable_with_an_unreadable_response(tmp_path):
    """Both cache ``equivalent: false``; only `parse_ok` says which is a decision."""
    judged = tmp_path / "judged.jsonl"
    failed = tmp_path / "failed.jsonl"
    run(three_labels(), judged, FakeMergeClient(set()))
    run(three_labels(), failed, FakeMergeClient(set(), malformed=True))

    assert [(r["equivalent"], r["parse_ok"], r["rationale"]) for r in read_jsonl(judged)] == [
        (False, True, "deliberating about equivalent")
    ] * 3
    assert [(r["equivalent"], r["parse_ok"], r["rationale"]) for r in read_jsonl(failed)] == [
        (False, False, "")
    ] * 3


# --- merge-path token accounting ---------------------------------------------


def test_merge_tokens_are_recorded_per_pair_and_summed_for_the_invocation(tmp_path):
    cache = tmp_path / "cache.jsonl"
    _, stats = run(three_labels(), cache, FakeMergeClient(set()))

    assert [(r["tokens_in"], r["tokens_out"]) for r in read_jsonl(cache)] == [(11, 22)] * 3
    assert (stats.tokens_in, stats.tokens_out) == (33, 66)
    assert cache_token_totals(cache) == {
        "tokens_in": 33,
        "tokens_out": 66,
        "rows": 3,
        "rows_missing": 0,
    }


def test_an_unparseable_response_still_counts_the_tokens_it_was_billed_for(tmp_path):
    cache = tmp_path / "cache.jsonl"
    _, stats = run(three_labels(), cache, FakeMergeClient(set(), malformed=True))

    assert [(r["tokens_in"], r["tokens_out"]) for r in read_jsonl(cache)] == [(5, 3)] * 3
    assert (stats.tokens_in, stats.tokens_out) == (15, 9)


def test_a_warm_rerun_spends_nothing_while_the_cache_still_reports_the_cost(tmp_path):
    """The two scopes disagree by design, and only one of them survives a rerun.

    `ClusterStats` describes this invocation, so a fully cached run correctly
    reports zero. The cache rows are what let the run dir still say what the
    merge path cost -- which is why the manifest names both.
    """
    cache = tmp_path / "cache.jsonl"
    run(three_labels(), cache, FakeMergeClient(set()))
    before = cache.read_bytes()

    second = FakeMergeClient(set())
    _, stats = run(three_labels(), cache, second)

    assert second.calls == []
    assert cache.read_bytes() == before, "a warm rerun rewrote rows instead of appending none"
    assert (stats.tokens_in, stats.tokens_out) == (0, 0)
    assert cache_token_totals(cache)["tokens_in"] == 33


def test_a_row_written_before_evidence_fields_still_loads(tmp_path):
    """Older caches keep working, and their absent tokens are counted, not assumed zero."""
    cache = tmp_path / "cache.jsonl"
    append_jsonl(
        cache,
        {
            "canon_a": "aaa first",
            "canon_b": "bbb second",
            "merge_prompt_sha256": MERGE_SHA,
            "model_id": MODEL,
            "equivalent": True,
        },
    )

    assert load_cache(cache)[("aaa first", "bbb second", MERGE_SHA, MODEL)] is True
    assert cache_token_totals(cache) == {
        "tokens_in": 0,
        "tokens_out": 0,
        "rows": 1,
        "rows_missing": 1,
    }
