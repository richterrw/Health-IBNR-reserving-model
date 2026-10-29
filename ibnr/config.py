"""Valuation assumptions. One place for every selection an actuary would sign off on."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path


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

    # --- Large claims -------------------------------------------------------------
    # Claimants above the threshold are removed from the inpatient triangle and
    # reserved separately: B-F on a pooled large-claim PMPM for every month.
    large_claim_threshold: float = 250_000.0
    large_claim_trend: float = 0.09  # frequency + severity trend on the pooled PMPM
    large_claim_experience_months: int = 24  # history used for the pooled PMPM
    large_claim_credible_lag: int = 6  # months younger than this are excluded from the pool

    # --- Reserve loads ------------------------------------------------------------
    margin_pct: float = 0.075  # provision for adverse deviation on IBNR
    cae_pct: float = 0.025  # claim adjustment expense on IBNR + margin

    # --- Mack range -----------------------------------------------------------------
    range_percentiles: tuple[float, ...] = field(default=(0.75, 0.95))

    # --- Actuarial judgment (see selections.json) -------------------------------------
    # Paid-month diagonals whose link ratios are left out of the averages.
    exclude_paid_months: tuple[str, ...] = ()
    # Paid months whose payments are grossed up for a known processing backlog
    # when that month is the valuation month (paid / measured actual-to-expected).
    restate_paid_months: tuple[str, ...] = ()
    # Hard link-ratio overrides: {category: {lag: ratio}}.
    factor_overrides: dict[str, dict[int, float]] = field(default_factory=dict)
    # Rationale for each selection, keyed by a short label. Reported verbatim.
    selection_notes: dict[str, str] = field(default_factory=dict)

    @property
    def has_judgment(self) -> bool:
        return bool(self.exclude_paid_months or self.restate_paid_months or self.factor_overrides)

    def mechanical(self) -> "ValuationConfig":
        """The same assumptions with every judgmental selection removed."""
        return replace(self, exclude_paid_months=(), restate_paid_months=(), factor_overrides={}, selection_notes={})

    def with_selections(self, path: str | Path) -> "ValuationConfig":
        """Apply a selections log (JSON) on top of this config."""
        data = json.loads(Path(path).read_text())
        notes = {}
        for kind in ("exclude_paid_months", "restate_paid_months"):
            for month, why in data.get(kind, {}).items():
                notes[f"{kind}:{month}"] = why
        overrides: dict[str, dict[int, float]] = {}
        for item in data.get("factor_overrides", []):
            overrides.setdefault(item["category"], {})[int(item["lag"])] = float(item["link_ratio"])
            notes[f"factor_override:{item['category']}:lag {item['lag']}"] = item["rationale"]
        return replace(
            self,
            exclude_paid_months=tuple(data.get("exclude_paid_months", {})),
            restate_paid_months=tuple(data.get("restate_paid_months", {})),
            factor_overrides=overrides,
            selection_notes=notes,
        )
