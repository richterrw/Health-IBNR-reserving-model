"""PMPM trend: fitting, reporting, and projecting expected claims for immature months."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TrendFit:
    annual_trend: float  # fitted (or selected) annual PMPM trend
    fitted_annual_trend: float  # regression result before any override
    seasonal_index: pd.Series  # by calendar month 1..12, geometric mean 1.0
    base_pmpm: float  # deseasonalised PMPM at the base-period midpoint
    base_midpoint: pd.Period
    r_squared: float
    fit_months: pd.PeriodIndex

    def expected_pmpm(self, months: pd.PeriodIndex) -> pd.Series:
        dt = np.array([(m - self.base_midpoint).n for m in months]) / 12.0
        season = self.seasonal_index.reindex(months.month).to_numpy()
        return pd.Series(self.base_pmpm * (1 + self.annual_trend) ** dt * season, index=months, name="expected_pmpm")


def fit(pmpm: pd.Series, credible: pd.Series, fit_months: int, base_months: int, override: float | None = None) -> TrendFit:
    """Log-linear PMPM regression with calendar-month seasonality.

    ``log(PMPM_t) = a + b * t + sum_m s_m * 1[month(t) = m]`` over the most
    recent ``fit_months`` credible months. ``b`` is the monthly trend; the
    month effects become a seasonal index. The base PMPM is the deseasonalised
    average over the last ``base_months`` credible months, centred at their
    midpoint, so the expected PMPM for any month is
    ``base * (1 + trend) ** years_from_midpoint * seasonal_index[month]``.
    """
    sample = pmpm[credible].iloc[-fit_months:]
    idx = sample.index
    t = np.array([(m - idx[0]).n for m in idx], dtype=float)
    y = np.log(sample.to_numpy())
    cal = idx.month.to_numpy()
    present = sorted(set(cal))
    ref = present[0]
    dummies = np.column_stack([(cal == m).astype(float) for m in present if m != ref])
    X = np.column_stack([np.ones_like(t), t, dummies])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else 1.0

    effects = {ref: 0.0}
    effects.update({m: beta[2 + j] for j, m in enumerate(m for m in present if m != ref)})
    eff = pd.Series({m: effects.get(m, 0.0) for m in range(1, 13)})
    seasonal = np.exp(eff - eff.mean())

    fitted = float(np.exp(12 * beta[1]) - 1)
    trend = fitted if override is None else override

    base = sample.iloc[-base_months:]
    deseason = base / seasonal.reindex(base.index.month).to_numpy()
    # Average deseasonalised PMPM, placed at the base period's midpoint.
    midpoint = base.index[len(base) // 2]
    dt = np.array([(m - midpoint).n for m in base.index]) / 12.0
    base_pmpm = float((deseason / (1 + trend) ** dt).mean())
    return TrendFit(trend, fitted, seasonal.rename("seasonal_index"), base_pmpm, midpoint, float(r2), idx)


def report(incurred: pd.Series, members: pd.Series) -> pd.DataFrame:
    """Monthly PMPM, rolling-12 PMPM and the 12-over-12 trend."""
    df = pd.DataFrame({"member_months": members.reindex(incurred.index), "incurred": incurred})
    df["pmpm"] = df["incurred"] / df["member_months"]
    r12_claims = df["incurred"].rolling(12).sum()
    r12_mm = df["member_months"].rolling(12).sum()
    df["rolling12_pmpm"] = r12_claims / r12_mm
    df["trend_12_over_12"] = df["rolling12_pmpm"] / df["rolling12_pmpm"].shift(12) - 1
    df["pmpm_yoy"] = df["pmpm"] / df["pmpm"].shift(12) - 1
    return df


def calendar_year(incurred: pd.Series, members: pd.Series) -> pd.DataFrame:
    """PMPM by calendar year (partial years flagged by month count)."""
    df = pd.DataFrame({"incurred": incurred, "member_months": members.reindex(incurred.index)})
    df["year"] = df.index.year
    g = df.groupby("year").agg(months=("incurred", "size"), incurred=("incurred", "sum"), member_months=("member_months", "sum"))
    g["pmpm"] = g["incurred"] / g["member_months"]
    g["pmpm_change"] = g["pmpm"].pct_change()
    return g
