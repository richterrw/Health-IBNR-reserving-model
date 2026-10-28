"""Valuation assumptions. One place for every selection an actuary would sign off on."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValuationConfig:
    # --- Link-ratio selection -------------------------------------------------
    # Completion factor method: straight average of the most recent N link
    # ratios at each lag, dropping the single high and low (the usual
    # "6-month average ex hi/lo" a health valuation team starts from).
    cf_avg_months: int = 6
    cf_exclude_hi_lo: bool = True
    # Chain ladder: volume-weighted average over this many incurred months
    # (None = all available history, i.e. classic Mack chain ladder).
    cl_avg_months: int | None = None
    # Lags beyond this are treated as fully complete (tail factor = 1.0).
    max_lag: int = 36

    # --- Hybrid selection for immature months ---------------------------------
    # Incurred months younger than this lag (0 = the valuation month itself)
    # are not credible on the completion factor alone; they get a
    # Bornhuetter-Ferguson blend with the PMPM-trended expected:
    #   ultimate = paid + (1 - CF) * expected
    pmpm_lags: int = 3

    # --- PMPM trend / projection ------------------------------------------------
    # Months of completed (lag >= pmpm_lags) experience used to fit trend and
    # seasonality with a log-linear regression.
    trend_fit_months: int = 30
    # Base period for the expected PMPM: the most recent N completed months.
    base_period_months: int = 12
    # If set, overrides the fitted annual trend for every category.
    selected_annual_trend: float | None = None

    # --- Reserve loads ------------------------------------------------------------
    margin_pct: float = 0.075  # provision for adverse deviation on IBNR
    cae_pct: float = 0.025  # claim adjustment expense on IBNR + margin

    # --- Mack range -----------------------------------------------------------------
    range_percentiles: tuple[float, ...] = field(default=(0.75, 0.95))
