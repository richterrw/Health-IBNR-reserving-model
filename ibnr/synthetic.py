"""Synthetic commercial medical claims, built to look like a warehouse extract.

The generator produces what a valuation team actually pulls each month:

* ``membership.csv``  - member months by incurred month
* ``claims.csv``      - paid dollars and claim counts by incurred month x paid
                        month x service category (data through the valuation
                        month's paid cutoff)
* ``large_claims.csv`` - claimant-level payments for inpatient claimants
                        over the $250k large-claim threshold (already
                        included in ``claims.csv``)
* ``pended_inventory.csv`` - claims operations' report of excess pended
                        (received, not yet paid) dollars at month-end
* ``true_ultimate.csv`` - the answer key (true incurred by month/category).
                        A real plan never has this; we keep it only so the
                        model can be validated against known truth.

Features baked in so the methods have something real to deal with:

* Membership growth with January open-enrollment steps.
* Category-specific annual PMPM trend and deductible-driven seasonality
  (low Q1, high Q4).
* Inpatient large claimants (> $250k): Poisson frequency, Pareto severity,
  slower payment than routine inpatient.
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


SPECS: dict[str, CategorySpec] = {
    "Inpatient": CategorySpec(98.0, 0.060, 0.035, 2.7, 1.3, 21_500.0),
    "Outpatient": CategorySpec(148.0, 0.080, 0.030, 1.8, 1.5, 1_150.0),
    "Professional": CategorySpec(171.0, 0.050, 0.022, 1.2, 1.6, 165.0),
}


# Large claimants: commercial plans see roughly 1-2 claimants per 1,000 members
# a year above $250k (medical + Rx). We attribute medical large claims to
# inpatient at 1.1 per 1,000 per year with a Pareto(alpha) tail above the
# threshold, capped at $4M.
LARGE_THRESHOLD = 250_000.0
LARGE_FREQ_PER_1000_YR = 1.1
LARGE_FREQ_TREND = 0.03
LARGE_SEV_TREND = 0.06
LARGE_PARETO_ALPHA = 2.3
LARGE_CAP = 4_000_000.0
LARGE_LAG = (3.4, 1.3)  # mean, shape: large claims pay slower than routine inpatient


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


def _apply_backlog(df: pd.DataFrame, keys: list[str], month: pd.Period, pct: float) -> tuple[pd.DataFrame, pd.Series]:
    """Slip ``pct`` of ``month``'s payments into the following paid month.

    Returns the adjusted payments and the delayed dollars per row of ``month``.
    """
    df = df.copy()
    bm, nm = str(month), str(month + 1)
    hit = df["paid_month"] == bm
    delayed = df.loc[hit, "paid_amount"] * pct
    df.loc[hit, "paid_amount"] -= delayed
    slip = df.loc[hit, keys].assign(extra=delayed.values)
    target = df["paid_month"] == nm
    df.loc[target, "paid_amount"] += df.loc[target, keys].merge(slip, on=keys, how="left")["extra"].fillna(0.0).values
    return df, delayed


def generate(
    start: str = "2023-01",
    valuation_month: str = "2026-09",
    starting_members: int = 185_000,
    backlog_month: str | None = "2026-06",
    backlog_pct: float = 0.12,
    max_lag: int = 36,
    seed: int = 20261028,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (membership, claims, true_ultimate, large_claims, pended_inventory) DataFrames."""
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
        incurred = members * expected_pmpm * noise

        for i, inc in enumerate(months):
            pattern = lag_pattern(spec.lag_mean * speed[i], spec.lag_shape, max_lag)
            # Cell-level noise around the pattern, renormalised so the cohort
            # still pays exactly its true incurred over max_lag months.
            jitter = rng.lognormal(0, 0.03, len(pattern))
            pattern = pattern * jitter / (pattern * jitter).sum()
            paid = incurred[i] * pattern
            truth_rows.append((str(inc), cat, incurred[i]))
            for lag, amt in enumerate(paid):
                claim_rows.append((str(inc), str(inc + lag), cat, lag, amt))

    claims = pd.DataFrame(claim_rows, columns=["incurred_month", "paid_month", "service_category", "lag", "paid_amount"])

    # Large claimants, generated claim by claim and added to inpatient.
    large_rows = []
    large_truth = np.zeros(n)
    cid = 0
    for i, inc in enumerate(months):
        lam = members[i] / 1000 * LARGE_FREQ_PER_1000_YR / 12 * (1 + LARGE_FREQ_TREND) ** t_years[i]
        for _ in range(rng.poisson(lam)):
            cid += 1
            sev = LARGE_THRESHOLD * rng.random() ** (-1 / LARGE_PARETO_ALPHA)
            sev = min(sev * (1 + LARGE_SEV_TREND) ** t_years[i], LARGE_CAP)
            pattern = lag_pattern(LARGE_LAG[0] * speed[i], LARGE_LAG[1], max_lag)
            pattern = pattern * rng.lognormal(0, 0.25, len(pattern))
            pattern /= pattern.sum()
            large_truth[i] += sev
            for lag, amt in enumerate(sev * pattern):
                if amt >= 0.01:
                    large_rows.append((f"LC{cid:05d}", str(inc), str(inc + lag), amt))
    large = pd.DataFrame(large_rows, columns=["claimant_id", "incurred_month", "paid_month", "paid_amount"])
    truth_rows = [(m, c, v + (large_truth[months.get_loc(pd.Period(m, "M"))] if c == "Inpatient" else 0.0)) for m, c, v in truth_rows]

    # Processing backlog: a share of the backlog month's payments slips one month.
    pended = pd.DataFrame(columns=["paid_month", "service_category", "excess_pended"])
    if backlog_month is not None:
        bm = pd.Period(backlog_month, "M")
        hit = claims["paid_month"] == str(bm)
        claims, delayed = _apply_backlog(claims, ["incurred_month", "service_category"], bm, backlog_pct)
        large, delayed_lc = _apply_backlog(large, ["claimant_id", "incurred_month"], bm, backlog_pct)
        by_cat = delayed.groupby(claims.loc[hit, "service_category"]).sum()
        by_cat["Inpatient"] += delayed_lc.sum()
        pended = pd.DataFrame({"paid_month": str(bm), "service_category": by_cat.index, "excess_pended": by_cat.round(2).values})

    large = large[large["paid_month"].map(lambda s: pd.Period(s, "M") <= val)].copy()
    lc_cells = large.groupby(["incurred_month", "paid_month"], as_index=False)["paid_amount"].sum().assign(service_category="Inpatient")
    claims = claims.merge(lc_cells, on=["incurred_month", "paid_month", "service_category"], how="left", suffixes=("", "_lc"))
    claims["paid_amount"] += claims["paid_amount_lc"].fillna(0.0)
    claims = claims.drop(columns="paid_amount_lc")

    claims = claims[claims["paid_month"].map(lambda s: pd.Period(s, "M") <= val)].copy()
    claims["claim_count"] = (
        claims["paid_amount"] / claims["service_category"].map(lambda c: SPECS[c].avg_claim_cost)
    ).round().astype(int)
    claims["paid_amount"] = claims["paid_amount"].round(2)
    claims = claims.drop(columns="lag").sort_values(["service_category", "incurred_month", "paid_month"])

    truth = pd.DataFrame(truth_rows, columns=["incurred_month", "service_category", "true_incurred"])
    truth["true_incurred"] = truth["true_incurred"].round(2)
    large["paid_amount"] = large["paid_amount"].round(2)
    large = large.sort_values(["claimant_id", "paid_month"]).reset_index(drop=True)
    return membership, claims.reset_index(drop=True), truth, large, pended


def write(out_dir: str | Path = "data", **kwargs) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    membership, claims, truth, large, pended = generate(**kwargs)
    membership.to_csv(out / "membership.csv", index=False)
    claims.to_csv(out / "claims.csv", index=False)
    truth.to_csv(out / "true_ultimate.csv", index=False)
    large.to_csv(out / "large_claims.csv", index=False)
    pended.to_csv(out / "pended_inventory.csv", index=False)


if __name__ == "__main__":
    write()
