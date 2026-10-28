"""Synthetic commercial medical claims, built to look like a warehouse extract.

The generator produces what a valuation team actually pulls each month:

* ``membership.csv``  - member months by incurred month
* ``claims.csv``      - paid dollars and claim counts by incurred month x paid
                        month x service category (data through the valuation
                        month's paid cutoff)
* ``true_ultimate.csv`` - the answer key (true incurred by month/category).
                        A real plan never has this; we keep it only so the
                        model can be validated against known truth.

Features baked in so the methods have something real to deal with:

* Membership growth with January open-enrollment steps.
* Category-specific annual PMPM trend and deductible-driven seasonality
  (low Q1, high Q4).
* Inpatient shock claims (large claimants) on top of lognormal noise.
* Category-specific payment lag patterns (inpatient slow, professional fast).
* Claims processing speeds up over time (auto-adjudication improvements),
  so old link ratios overstate the remaining runout. This is what separates a
  recent-average completion factor from an all-history chain ladder.
* A one-month processing backlog (paid month ``backlog_month``) with
  catch-up the following month - the kind of diagonal distortion an analyst
  has to spot in the triangle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORIES = ("Inpatient", "Outpatient", "Professional")

# Deductible seasonality: Q1 low (members in deductible), Q4 high (met OOP max).
SEASONALITY = np.array([0.93, 0.95, 1.01, 0.99, 1.00, 0.98, 0.97, 1.01, 0.99, 1.03, 1.02, 1.12])
SEASONALITY = SEASONALITY / SEASONALITY.mean()


@dataclass(frozen=True)
class CategorySpec:
    base_pmpm: float  # PMPM in the first incurred month, before seasonality
    annual_trend: float
    noise_sigma: float  # lognormal sigma on monthly incurred
    lag_mean: float  # mean payment lag in months (at the start of history)
    lag_shape: float  # gamma shape; lower = longer tail
    avg_claim_cost: float  # for claim counts
    shock_prob: float = 0.0  # monthly probability of a large-claimant shock
    shock_size: float = 0.0  # shock size as a fraction of expected monthly incurred


SPECS: dict[str, CategorySpec] = {
    "Inpatient": CategorySpec(132.0, 0.065, 0.045, 2.7, 1.3, 21_500.0, 0.10, 0.12),
    "Outpatient": CategorySpec(148.0, 0.080, 0.030, 1.8, 1.5, 1_150.0),
    "Professional": CategorySpec(171.0, 0.050, 0.022, 1.2, 1.6, 165.0),
}


def month_range(start: str, end: str) -> pd.PeriodIndex:
    return pd.period_range(start, end, freq="M")


def lag_pattern(mean: float, shape: float, max_lag: int, shift: float = 0.4) -> np.ndarray:
    """Monthly payment pattern: ``shift + Gamma(shape, mean/shape)`` months, discretised.

    Lag 0 is payment within the incurred month; the shift reflects that
    services are spread across the month and none pay instantly. Mass beyond
    ``max_lag`` is folded back in proportionally so the pattern sums to 1.
    The gamma CDF is integrated numerically to avoid a scipy dependency.
    """
    scale = mean / shape
    edges = np.arange(max_lag + 2, dtype=float) - shift
    grid = np.linspace(0, max_lag + 1, (max_lag + 1) * 200 + 1)
    pdf = grid ** (shape - 1) * np.exp(-grid / scale)
    if shape < 1:
        pdf[0] = pdf[1]
    cdf = np.concatenate([[0.0], np.cumsum((pdf[1:] + pdf[:-1]) / 2 * np.diff(grid))])
    cdf /= cdf[-1]
    pmf = np.diff(np.interp(edges, grid, cdf, left=0.0))
    return pmf / pmf.sum()


def generate(
    start: str = "2023-01",
    valuation_month: str = "2026-09",
    starting_members: int = 185_000,
    backlog_month: str | None = "2026-06",
    backlog_pct: float = 0.12,
    max_lag: int = 36,
    seed: int = 20261028,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (membership, claims, true_ultimate) DataFrames."""
    rng = np.random.default_rng(seed)
    val = pd.Period(valuation_month, "M")
    months = month_range(start, valuation_month)
    n = len(months)

    # Membership: modest organic growth, January open-enrollment steps, noise.
    members = np.empty(n)
    m = float(starting_members)
    for i, p in enumerate(months):
        if p.month == 1 and i > 0:
            m *= 1 + rng.normal(0.045, 0.01)
        else:
            m *= 1 + rng.normal(0.0015, 0.002)
        members[i] = round(m)
    membership = pd.DataFrame({"incurred_month": months.astype(str), "member_months": members.astype(int)})

    t_years = np.arange(n) / 12.0
    # Processing speed: lag means shrink ~12% from the start of history to the end.
    speed = np.linspace(1.08, 0.95, n)

    claim_rows = []
    truth_rows = []
    for cat in CATEGORIES:
        spec = SPECS[cat]
        expected_pmpm = spec.base_pmpm * (1 + spec.annual_trend) ** t_years * SEASONALITY[months.month - 1]
        noise = rng.lognormal(-0.5 * spec.noise_sigma**2, spec.noise_sigma, n)
        shocks = np.where(rng.random(n) < spec.shock_prob, rng.uniform(0.5, 1.0, n) * spec.shock_size, 0.0)
        incurred = members * expected_pmpm * (noise + shocks)

        for i, inc in enumerate(months):
            pattern = lag_pattern(spec.lag_mean * speed[i], spec.lag_shape, max_lag)
            # Cell-level noise around the pattern, renormalised so the cohort
            # still pays exactly its true incurred over max_lag months.
            jitter = rng.lognormal(0, 0.06, len(pattern))
            pattern = pattern * jitter / (pattern * jitter).sum()
            paid = incurred[i] * pattern
            truth_rows.append((str(inc), cat, incurred[i]))
            for lag, amt in enumerate(paid):
                claim_rows.append((str(inc), str(inc + lag), cat, lag, amt))

    claims = pd.DataFrame(claim_rows, columns=["incurred_month", "paid_month", "service_category", "lag", "paid_amount"])

    # Processing backlog: a share of the backlog month's payments slips one month.
    if backlog_month is not None:
        bm = str(pd.Period(backlog_month, "M"))
        nm = str(pd.Period(backlog_month, "M") + 1)
        hit = claims["paid_month"] == bm
        delayed = claims.loc[hit, "paid_amount"] * backlog_pct
        claims.loc[hit, "paid_amount"] -= delayed
        slip = claims.loc[hit, ["incurred_month", "service_category"]].assign(extra=delayed.values)
        key = ["incurred_month", "service_category"]
        target = claims["paid_month"] == nm
        merged = claims.loc[target, key].merge(slip, on=key, how="left")["extra"].fillna(0.0).values
        claims.loc[target, "paid_amount"] += merged

    claims = claims[claims["paid_month"].map(lambda s: pd.Period(s, "M") <= val)].copy()
    claims["claim_count"] = (
        claims["paid_amount"] / claims["service_category"].map(lambda c: SPECS[c].avg_claim_cost)
    ).round().astype(int)
    claims["paid_amount"] = claims["paid_amount"].round(2)
    claims = claims.drop(columns="lag").sort_values(["service_category", "incurred_month", "paid_month"])

    truth = pd.DataFrame(truth_rows, columns=["incurred_month", "service_category", "true_incurred"])
    truth["true_incurred"] = truth["true_incurred"].round(2)
    return membership, claims.reset_index(drop=True), truth


def write(out_dir: str | Path = "data", **kwargs) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    membership, claims, truth = generate(**kwargs)
    membership.to_csv(out / "membership.csv", index=False)
    claims.to_csv(out / "claims.csv", index=False)
    truth.to_csv(out / "true_ultimate.csv", index=False)


if __name__ == "__main__":
    write()
