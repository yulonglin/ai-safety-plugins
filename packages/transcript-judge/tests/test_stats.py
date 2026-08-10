"""Agreement statistics, and the null that every one of them ships with.

The load-bearing rule: an unqueried construct x model cell is **missing**, never
negative. Defaulting it to "did not flag" would manufacture agreement out of
work that was never done, in the direction that flatters the result.
"""

from __future__ import annotations

from transcript_judge.models import LabelRow
from transcript_judge.stats import (
    StatsReport,
    agreement,
    chance_agreement,
    cohens_kappa,
    paired_values,
    permutation_p_value,
    wilson_interval,
)

MODEL_A = "claude-sonnet-5"
MODEL_B = "openai/gpt-5.6-sol"


def label(sample: str, construct: str, model: str, value: bool) -> LabelRow:
    return LabelRow(
        label_id=f"{sample}-{construct}-{model}",
        sample_key=sample,
        label=construct,
        evidence_mode="positive_quote",
        value=value,
        judge_name="alpha",
        prompt_sha256="a" * 64,
        model_id=model,
        surface="full",
        judgement_row_id="alpha.jsonl:0",
    )


# --- Wilson intervals --------------------------------------------------------


def test_zero_of_seven_has_a_wide_upper_bound_not_a_point_at_zero():
    interval = wilson_interval(0, 7)
    assert interval.point == 0.0
    assert round(interval.high, 3) == 0.354
    assert round(interval.low, 3) == 0.0
    # The percentage alone would read as "0%" and hide that upper bound.
    assert interval.as_counts() == "0/7"


def test_seven_of_seven_is_bounded_away_from_certainty():
    interval = wilson_interval(7, 7)
    assert interval.point == 1.0
    assert round(interval.low, 3) == 0.646
    assert interval.as_counts() == "7/7"


def test_a_symmetric_interval_at_one_half():
    interval = wilson_interval(5, 10)
    assert interval.point == 0.5
    assert round(interval.low + interval.high, 6) == 1.0


def test_no_observations_gives_the_whole_unit_interval():
    interval = wilson_interval(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)
    assert interval.describe() == "0/0 (no paired observations)"


def test_describe_leads_with_the_counts():
    assert wilson_interval(0, 7).describe().startswith("0/7 = 0.000 [95% Wilson ")


# --- the nulls ---------------------------------------------------------------


def test_two_raters_flagging_ninety_four_percent_agree_by_coincidence():
    assert round(chance_agreement(0.94, 0.94), 3) == 0.887


def test_chance_agreement_bottoms_out_at_one_half_for_balanced_raters():
    assert chance_agreement(0.5, 0.5) == 0.5


def test_kappa_is_zero_when_observed_agreement_is_exactly_chance():
    assert cohens_kappa(0.887, 0.887) == 0.0


def test_kappa_is_one_for_perfect_agreement():
    assert cohens_kappa(1.0, 0.5) == 1.0


def test_kappa_is_negative_below_chance():
    assert cohens_kappa(0.4, 0.5) < 0.0


def test_a_degenerate_chance_of_one_does_not_divide_by_zero():
    assert cohens_kappa(1.0, 1.0) == 0.0


# --- unqueried cells are missing, never negative -----------------------------


def test_a_sample_only_one_model_answered_is_excluded_and_counted():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s2", "flags_x", MODEL_A, False),
        label("s3", "flags_x", MODEL_A, True),
        label("s1", "flags_x", MODEL_B, True),
        label("s2", "flags_x", MODEL_B, False),
    ]
    pairs, excluded = paired_values(labels, "flags_x", MODEL_A, MODEL_B)
    assert pairs == [(True, True), (False, False)]
    assert excluded == 1


def test_excluding_the_unqueried_sample_changes_the_answer():
    # Model B never saw s3. Defaulting it to False would score s3 as a
    # disagreement and report 2/3 instead of 2/2.
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s2", "flags_x", MODEL_A, False),
        label("s3", "flags_x", MODEL_A, True),
        label("s1", "flags_x", MODEL_B, True),
        label("s2", "flags_x", MODEL_B, False),
    ]
    result = agreement(labels, "flags_x", MODEL_A, MODEL_B, n_permutations=200)
    assert result.n_paired == 2
    assert result.n_excluded_unqueried == 1
    assert result.observed.as_counts() == "2/2"


def test_a_construct_no_model_pair_shares_reports_zero_rather_than_agreement():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s1", "flags_y", MODEL_B, True),
    ]
    result = agreement(labels, "flags_x", MODEL_A, MODEL_B, n_permutations=200)
    assert result.n_paired == 0
    assert result.observed.as_counts() == "0/0"
    assert result.kappa == 0.0
    assert result.permutation_p is None


def test_labels_from_other_constructs_are_ignored():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s1", "flags_x", MODEL_B, True),
        label("s1", "flags_y", MODEL_A, False),
        label("s1", "flags_y", MODEL_B, True),
    ]
    pairs, excluded = paired_values(labels, "flags_x", MODEL_A, MODEL_B)
    assert pairs == [(True, True)]
    assert excluded == 0


def test_labels_from_a_third_model_are_ignored():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s1", "flags_x", MODEL_B, True),
        label("s1", "flags_x", "some-third-model", False),
    ]
    pairs, _ = paired_values(labels, "flags_x", MODEL_A, MODEL_B)
    assert pairs == [(True, True)]


# --- the full result ---------------------------------------------------------


def test_agreement_reports_both_base_rates_beside_the_agreement():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s2", "flags_x", MODEL_A, True),
        label("s3", "flags_x", MODEL_A, False),
        label("s1", "flags_x", MODEL_B, True),
        label("s2", "flags_x", MODEL_B, False),
        label("s3", "flags_x", MODEL_B, False),
    ]
    result = agreement(labels, "flags_x", MODEL_A, MODEL_B, n_permutations=200)
    assert result.n_paired == 3
    assert result.observed.as_counts() == "2/3"
    assert result.base_rate_a.as_counts() == "2/3"
    assert result.base_rate_b.as_counts() == "1/3"
    assert round(result.chance_agreement, 4) == round(chance_agreement(2 / 3, 1 / 3), 4)


def test_the_description_carries_the_chance_figure_not_only_the_raw_rate():
    labels = [
        label("s1", "flags_x", MODEL_A, True),
        label("s1", "flags_x", MODEL_B, True),
    ]
    text = agreement(labels, "flags_x", MODEL_A, MODEL_B, n_permutations=200).describe()
    assert "chance " in text
    assert "kappa " in text
    assert "1/1" in text


# --- the permutation null ----------------------------------------------------


def test_the_permutation_null_preserves_each_model_marginal():
    pairs = [(True, True), (True, False), (False, False), (False, True)]
    p = permutation_p_value(pairs, seed=0, n_permutations=500)
    assert 0.0 < p <= 1.0


def test_no_pairs_gives_a_p_value_of_one():
    assert permutation_p_value([], seed=0, n_permutations=500) == 1.0


def test_the_add_one_correction_keeps_p_away_from_exactly_zero():
    pairs = [(True, True)] * 8 + [(False, False)] * 8
    p = permutation_p_value(pairs, seed=0, n_permutations=100)
    assert p >= 1 / 101
    assert p > 0.0


def test_the_permutation_is_seeded_and_therefore_reproducible():
    pairs = [(True, True), (True, False), (False, False), (False, True)] * 4
    a = permutation_p_value(pairs, seed=7, n_permutations=300)
    b = permutation_p_value(pairs, seed=7, n_permutations=300)
    assert a == b


# --- what the intervals do not cover ----------------------------------------


def test_the_report_states_which_variation_the_intervals_omit():
    scope = StatsReport().interval_scope
    assert "sampling over transcripts only" in scope
    assert "judge stochasticity" in scope
