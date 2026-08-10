"""The overlap payload and the self-contained HTML page.

The load-bearing property here is that an *unqueried* construct×model cell is
missing, not negative: a construct one model was never asked about must not be
counted as that model saying "no".
"""

from __future__ import annotations

import json

from transcript_judge.artifact import (
    BLINDING_WARNING,
    TOKENIZER_HINT,
    build_overlap,
    render_html,
)
from transcript_judge.models import LabelRow

MODEL_A = "claude-sonnet-5"
MODEL_B = "openai/gpt-5.6-sol"


def label(
    sample: str,
    construct: str,
    model: str,
    value: bool,
    *,
    evidence_mode: str = "positive_quote",
    judge: str = "alpha",
    quote: str | None = "300 µL",
    source_excerpt: str | None = "300 µL",
    char_start: int | None = 4,
    char_end: int | None = 10,
) -> LabelRow:
    return LabelRow(
        label_id=f"{sample}|{construct}|{model}",
        sample_key=sample,
        label=construct,
        evidence_mode=evidence_mode,
        value=value,
        judge_quote=quote if value else None,
        source_excerpt=source_excerpt if value else None,
        message_index=0 if value else None,
        char_start=char_start if value else None,
        char_end=char_end if value else None,
        occurrence_count=1 if value else 0,
        resolved=bool(value),
        resolution_tier="exact" if value else "unresolved",
        judge_name=judge,
        prompt_sha256="p" * 64,
        model_id=model,
        surface="full",
        judgement_row_id=f"{judge}.jsonl:0",
    )


def two_model_labels() -> list[LabelRow]:
    """Both models judged s1 and s2; only model A was ever asked about s3."""
    return [
        label("s1", "flags_protocol_error", MODEL_A, True),
        label("s1", "flags_protocol_error", MODEL_B, True),
        label("s2", "flags_protocol_error", MODEL_A, True),
        label("s2", "flags_protocol_error", MODEL_B, False),
        label("s3", "flags_protocol_error", MODEL_A, True),
    ]


# --- shape -------------------------------------------------------------------


def test_the_payload_carries_everything_the_page_needs():
    overlap = build_overlap(labels=two_model_labels(), run_id="run-x", blinded=True)

    assert set(overlap) == {
        "run_id",
        "generated_utc",
        "blinded",
        "tokenizer_hint",
        "constructs",
        "models",
        "reliability",
        "exploratory",
        "labels",
        "labels_by_sample",
    }
    assert overlap["run_id"] == "run-x"
    assert overlap["blinded"] is True
    assert overlap["models"] == [MODEL_A, MODEL_B]


def test_v1_stores_no_token_positions():
    """Token indices are derived at render time from the char span."""
    assert TOKENIZER_HINT is None
    assert (
        build_overlap(labels=two_model_labels(), run_id="r", blinded=True)["tokenizer_hint"] is None
    )


def test_hand_validation_constructs_are_not_offered_as_venn_regions():
    labels = [
        *two_model_labels(),
        label("s1", "omits_safety_caveat", MODEL_A, True, evidence_mode="hand_validation"),
    ]

    overlap = build_overlap(labels=labels, run_id="r", blinded=True)

    assert overlap["constructs"] == ["flags_protocol_error"]
    assert overlap["exploratory"] == []


# --- unqueried cells are missing, not negative -------------------------------


def test_a_sample_only_one_model_saw_is_excluded_from_the_paired_count():
    (entry,) = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)["reliability"]

    # s1 and s2 were put to both models; s3 only to model A.
    assert entry["n_paired"] == 2
    assert entry["both"] == ["s1"]
    assert entry["only_a"] == ["s2", "s3"]
    assert entry["only_b"] == []


def test_dropping_the_unqueried_sample_changes_the_paired_count():
    """Guards the failure where `n_paired` is read off the region sizes."""
    with_s3 = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)
    without_s3 = build_overlap(
        labels=[lab for lab in two_model_labels() if lab.sample_key != "s3"],
        run_id="r",
        blinded=True,
    )

    assert with_s3["reliability"][0]["n_paired"] == 2
    assert without_s3["reliability"][0]["n_paired"] == 2
    # The region differs even though the paired count does not.
    assert with_s3["reliability"][0]["only_a"] == ["s2", "s3"]
    assert without_s3["reliability"][0]["only_a"] == ["s2"]


def test_a_construct_only_one_model_was_asked_about_reports_no_paired_samples():
    labels = [*two_model_labels(), label("s1", "eval_awareness", MODEL_A, True)]

    overlap = build_overlap(labels=labels, run_id="r", blinded=True)

    (entry,) = [e for e in overlap["reliability"] if e["construct"] == "eval_awareness"]
    assert entry["n_paired"] == 0
    assert entry["only_a"] == ["s1"]
    assert entry["only_b"] == []
    assert entry["both"] == []


# --- reliability vs exploratory ----------------------------------------------


def test_one_model_yields_no_reliability_panels():
    """A single measurement cannot bound its own reproducibility."""
    labels = [lab for lab in two_model_labels() if lab.model_id == MODEL_A]

    overlap = build_overlap(labels=labels, run_id="r", blinded=True)

    assert overlap["models"] == [MODEL_A]
    assert overlap["reliability"] == []


def test_reliability_panels_name_both_models():
    (entry,) = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)["reliability"]

    assert entry["kind"] == "reliability"
    assert entry["construct"] == "flags_protocol_error"
    assert (entry["model_a"], entry["model_b"]) == (MODEL_A, MODEL_B)
    assert entry["label_a"] == f"flags_protocol_error / {MODEL_A}"
    assert entry["label_b"] == f"flags_protocol_error / {MODEL_B}"


def test_exploratory_panels_are_the_construct_upper_triangle_over_the_model_union():
    labels = [
        *two_model_labels(),
        label("s2", "eval_awareness", MODEL_B, True),
        label("s3", "eval_awareness", MODEL_A, True),
    ]

    overlap = build_overlap(labels=labels, run_id="r", blinded=True)

    (entry,) = overlap["exploratory"]
    assert entry["kind"] == "exploratory"
    assert (entry["label_a"], entry["label_b"]) == ("eval_awareness", "flags_protocol_error")
    # eval_awareness is positive on s2 and s3 across the model union.
    assert entry["only_a"] == []
    assert entry["both"] == ["s2", "s3"]
    assert entry["only_b"] == ["s1"]


def test_three_constructs_give_three_exploratory_pairs():
    labels = [
        label("s1", "aaa", MODEL_A, True),
        label("s1", "bbb", MODEL_A, True),
        label("s1", "ccc", MODEL_A, True),
    ]

    overlap = build_overlap(labels=labels, run_id="r", blinded=True)

    assert [(e["label_a"], e["label_b"]) for e in overlap["exploratory"]] == [
        ("aaa", "bbb"),
        ("aaa", "ccc"),
        ("bbb", "ccc"),
    ]


# --- reaching the underlying labels ------------------------------------------


def test_every_label_is_reachable_with_its_excerpt_and_span():
    overlap = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)

    entry = overlap["labels"][f"s1|flags_protocol_error|{MODEL_A}"]
    assert entry["sample_key"] == "s1"
    assert entry["judge_quote"] == "300 µL"
    assert entry["source_excerpt"] == "300 µL"
    assert (entry["char_start"], entry["char_end"]) == (4, 10)
    assert entry["resolution_tier"] == "exact"
    assert entry["model_id"] == MODEL_A


def test_rationales_are_attached_by_label_id():
    key = f"s1|flags_protocol_error|{MODEL_A}"

    overlap = build_overlap(
        labels=two_model_labels(),
        run_id="r",
        blinded=True,
        rationales={key: "the stated volume contradicts the protocol"},
    )

    assert overlap["labels"][key]["rationale"] == "the stated volume contradicts the protocol"
    assert overlap["labels"][f"s2|flags_protocol_error|{MODEL_B}"]["rationale"] == ""


def test_negative_labels_are_reachable_but_not_indexed_as_hits():
    overlap = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)

    negative = overlap["labels"][f"s2|flags_protocol_error|{MODEL_B}"]
    assert negative["value"] is False
    assert overlap["labels_by_sample"]["s2"] == [f"s2|flags_protocol_error|{MODEL_A}"]


def test_labels_by_sample_lists_every_positive_hit_on_that_sample():
    overlap = build_overlap(labels=two_model_labels(), run_id="r", blinded=True)

    assert overlap["labels_by_sample"]["s1"] == [
        f"s1|flags_protocol_error|{MODEL_A}",
        f"s1|flags_protocol_error|{MODEL_B}",
    ]


# --- the page ----------------------------------------------------------------


def test_the_page_loads_no_external_resource():
    """A published artifact runs under a CSP that blocks every external host."""
    html = render_html(build_overlap(labels=two_model_labels(), run_id="run-x", blinded=True))

    assert "https://" not in html
    assert "<script src=" not in html
    assert "<link " not in html
    assert "@import" not in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    # The only `http://` permitted is the SVG namespace, which is an identifier
    # rather than a URL the browser ever resolves.
    assert [
        chunk for chunk in html.split("http://") if not chunk.startswith("www.w3.org/2000/svg")
    ] == [html.split("http://")[0]]


def test_the_payload_is_inlined_rather_than_fetched():
    html = render_html(build_overlap(labels=two_model_labels(), run_id="run-x", blinded=True))

    assert "s1|flags_protocol_error|" in html
    assert "300 µL" in html
    assert "overlap.json" not in html


def test_a_label_containing_a_closing_script_tag_cannot_break_out():
    hostile = "says </script><img onerror=alert(1)>"
    html = render_html(
        build_overlap(labels=[label("s1", hostile, MODEL_A, True)], run_id="r", blinded=True)
    )

    assert "<\\/script><img onerror=alert(1)>" in html

    # The data block still terminates where the template put its closer, so the
    # embedded JSON is recoverable and the injected markup never became markup.
    body = html.split('<script id="overlap-data" type="application/json">', 1)[1]
    payload, _, _ = body.partition("</script>")
    assert json.loads(payload)["constructs"] == [hostile]


def test_the_page_defines_its_palette_for_all_three_theme_states():
    html = render_html(build_overlap(labels=two_model_labels(), run_id="r", blinded=True))

    assert ":root {" in html
    assert "prefers-color-scheme: dark" in html
    assert ':root[data-theme="dark"]' in html
    assert ':root:not([data-theme="light"])' in html


def test_the_run_id_titles_the_page():
    html = render_html(build_overlap(labels=two_model_labels(), run_id="run-x", blinded=True))

    assert "<title>Transcript judge overlap — run-x</title>" in html


def test_an_unblinded_run_says_so_on_the_page():
    blinded = render_html(build_overlap(labels=two_model_labels(), run_id="r", blinded=True))
    unblinded = render_html(build_overlap(labels=two_model_labels(), run_id="r", blinded=False))

    assert BLINDING_WARNING not in blinded
    assert BLINDING_WARNING in unblinded


def test_the_inlined_json_round_trips():
    overlap = build_overlap(labels=two_model_labels(), run_id="run-x", blinded=True)

    # The same object the page embeds must survive a JSON round trip.
    assert json.loads(json.dumps(overlap, ensure_ascii=False))["models"] == [MODEL_A, MODEL_B]
