"""Agreement statistics, each shipped with its null.

The rule this module exists to enforce: **an unqueried construct x model cell is
missing, never negative.** If model B was never asked about a construct, its
answer is absent -- scoring it as "did not flag" would manufacture agreement out
of work that was never done, and would do so in the direction that flatters the
result. So `paired_values` includes a sample only when *both* cells answered it,
and reports the excluded count rather than absorbing it.

Every proportion carries a Wilson interval (never the normal approximation,
which misbehaves at 0 and 1) and, next to it, the count -- ``0/7`` rather than
``0%``, because the Wilson upper bound on 0/7 is 35.4% and the percentage alone
hides that.
"""

from __future__ import annotations

import math
import random

from pydantic import BaseModel, Field

from transcript_judge.models import LabelRow

Z_95 = 1.959963984540054
DEFAULT_PERMUTATIONS = 10_000


class Interval(BaseModel):
    k: int
    n: int
    point: float
    low: float
    high: float

    def as_counts(self) -> str:
        """Small denominators are stated as counts, never bare percentages."""
        return f"{self.k}/{self.n}"

    def describe(self) -> str:
        if self.n == 0:
            return "0/0 (no paired observations)"
        return f"{self.as_counts()} = {self.point:.3f} [95% Wilson {self.low:.3f}, {self.high:.3f}]"


class AgreementResult(BaseModel):
    construct: str
    model_a: str
    model_b: str
    n_paired: int
    n_excluded_unqueried: int
    observed: Interval
    base_rate_a: Interval
    base_rate_b: Interval
    chance_agreement: float
    kappa: float
    permutation_p: float | None = None
    permutation_seed: int | None = None
    n_permutations: int = 0

    def describe(self) -> str:
        return (
            f"{self.construct} [{self.model_a} vs {self.model_b}]: "
            f"observed agreement {self.observed.describe()}; "
            f"chance {self.chance_agreement:.3f} (from base rates "
            f"{self.base_rate_a.as_counts()} and {self.base_rate_b.as_counts()}); "
            f"kappa {self.kappa:.3f}"
        )


class StatsReport(BaseModel):
    results: list[AgreementResult] = Field(default_factory=list)
    permutation_seed: int = 0
    n_permutations: int = 0
    #: Which sources of variation the intervals cover, stated where the numbers live.
    interval_scope: str = (
        "Wilson intervals cover sampling over transcripts only. They do NOT cover "
        "judge stochasticity across repeated calls on the same transcript, which is "
        "unmeasured in this run."
    )


def wilson_interval(k: int, n: int, z: float = Z_95) -> Interval:
    if n == 0:
        return Interval(k=0, n=0, point=0.0, low=0.0, high=1.0)
    p = k / n
    denom = n + z * z
    center = (k + z * z / 2) / denom
    half = (z / denom) * math.sqrt(k * (n - k) / n + z * z / 4)
    return Interval(
        k=k,
        n=n,
        point=p,
        low=max(0.0, center - half),
        high=min(1.0, center + half),
    )


def chance_agreement(p_a: float, p_b: float) -> float:
    """What two raters would agree at by coincidence, given their base rates.

    Two raters flagging 94% each agree ~89% of the time with no signal at all,
    which is why this number belongs beside every agreement figure rather than
    in a footnote.
    """
    return p_a * p_b + (1 - p_a) * (1 - p_b)


def cohens_kappa(observed: float, chance: float) -> float:
    if chance >= 1.0:
        return 0.0
    return (observed - chance) / (1 - chance)


def paired_values(
    labels: list[LabelRow], construct: str, model_a: str, model_b: str
) -> tuple[list[tuple[bool, bool]], int]:
    """Samples where both cells answered `construct`, plus the excluded count.

    A sample answered by only one model is excluded and counted -- never
    defaulted to False.
    """
    by_model: dict[str, dict[str, bool]] = {model_a: {}, model_b: {}}
    for label in labels:
        if label.label != construct or label.model_id not in by_model:
            continue
        by_model[label.model_id][label.sample_key] = label.value

    keys_a, keys_b = set(by_model[model_a]), set(by_model[model_b])
    both = sorted(keys_a & keys_b)
    excluded = len(keys_a ^ keys_b)
    return [(by_model[model_a][k], by_model[model_b][k]) for k in both], excluded


def permutation_p_value(
    pairs: list[tuple[bool, bool]], *, seed: int, n_permutations: int = DEFAULT_PERMUTATIONS
) -> float:
    """Permutation null: shuffle within each model, preserving its marginals.

    The same claim as the closed-form chance agreement, demonstrated rather than
    asserted -- it destroys the sample-to-sample correspondence while leaving
    each model's flag rate exactly as observed.
    """
    if not pairs:
        return 1.0
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    observed = sum(x == y for x, y in pairs)

    rng = random.Random(seed)
    shuffled_a, shuffled_b = list(a), list(b)
    at_least = 0
    for _ in range(n_permutations):
        rng.shuffle(shuffled_a)
        rng.shuffle(shuffled_b)
        if sum(x == y for x, y in zip(shuffled_a, shuffled_b, strict=True)) >= observed:
            at_least += 1
    # Add-one correction: a p-value of exactly 0 is not attainable from a finite
    # number of draws and should not be reported as though it were.
    return (at_least + 1) / (n_permutations + 1)


def agreement(
    labels: list[LabelRow],
    construct: str,
    model_a: str,
    model_b: str,
    *,
    seed: int = 0,
    n_permutations: int = DEFAULT_PERMUTATIONS,
) -> AgreementResult:
    pairs, excluded = paired_values(labels, construct, model_a, model_b)
    n = len(pairs)
    agreed = sum(x == y for x, y in pairs)

    k_a = sum(1 for x, _ in pairs if x)
    k_b = sum(1 for _, y in pairs if y)
    rate_a = wilson_interval(k_a, n)
    rate_b = wilson_interval(k_b, n)
    observed = wilson_interval(agreed, n)
    chance = chance_agreement(rate_a.point, rate_b.point) if n else 0.0

    return AgreementResult(
        construct=construct,
        model_a=model_a,
        model_b=model_b,
        n_paired=n,
        n_excluded_unqueried=excluded,
        observed=observed,
        base_rate_a=rate_a,
        base_rate_b=rate_b,
        chance_agreement=chance,
        kappa=cohens_kappa(observed.point, chance) if n else 0.0,
        permutation_p=permutation_p_value(pairs, seed=seed, n_permutations=n_permutations)
        if n
        else None,
        permutation_seed=seed,
        n_permutations=n_permutations if n else 0,
    )
