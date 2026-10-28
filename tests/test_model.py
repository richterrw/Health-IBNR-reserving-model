import numpy as np
import pandas as pd
import pytest

from ibnr import synthetic, trend, triangle, valuation
from ibnr.config import ValuationConfig

VAL = pd.Period("2026-09", "M")


@pytest.fixture(scope="module")
def book():
    membership, claims, truth = synthetic.generate(valuation_month=str(VAL))
    claims["incurred_month"] = pd.PeriodIndex(claims["incurred_month"], freq="M")
    claims["paid_month"] = pd.PeriodIndex(claims["paid_month"], freq="M")
    members = pd.Series(membership["member_months"].values, index=pd.PeriodIndex(membership["incurred_month"], freq="M"))
    true_ult = truth.groupby("incurred_month")["true_incurred"].sum()
    true_ult.index = pd.PeriodIndex(true_ult.index, freq="M")
    return claims, members, truth, true_ult


@pytest.fixture(scope="module")
def current(book):
    claims, members, *_ = book
    return valuation.run(claims, members, VAL)


def test_lag_pattern_sums_to_one():
    p = synthetic.lag_pattern(2.0, 1.5, 36)
    assert p.sum() == pytest.approx(1.0)
    assert (p >= 0).all()


def test_triangle_shape_and_totals(book):
    claims, *_ = book
    cum = triangle.build(claims, VAL, "Professional")
    n = cum.shape[0]
    assert cum.shape == (n, n)
    assert cum.iloc[-1].notna().sum() == 1  # valuation month: lag 0 only
    assert cum.iloc[0].notna().all()
    paid = triangle.latest_diagonal(cum).sum()
    assert paid == pytest.approx(claims.loc[claims["service_category"] == "Professional", "paid_amount"].sum())
    # Cumulative must be non-decreasing along each row.
    assert (cum.diff(axis=1).iloc[:, 1:].fillna(0) >= -1e-6).all().all()


def test_as_of_excludes_future_payments(book):
    claims, *_ = book
    earlier = triangle.build(claims, VAL - 3)
    assert earlier.index[-1] == VAL - 3
    assert triangle.ages(earlier).iloc[-1] == 0


def test_selected_ibnr_close_to_truth(book, current):
    *_, true_ult = book
    tm = current.total_monthly
    true_ibnr = (true_ult.reindex(tm.index) - tm["paid"]).sum()
    assert tm["selected_ibnr"].sum() / true_ibnr - 1 == pytest.approx(0, abs=0.05)
    # Mature months are essentially fully paid; IBNR there should be tiny.
    assert tm.loc[tm["age"] >= 12, "selected_ibnr"].sum() < 0.01 * tm["selected_ibnr"].sum()


def test_chain_ladder_overstates_when_claims_speed_up(current):
    s = current.summary().loc["Total"]
    assert s["ibnr_chain_ladder"] > s["ibnr_completion_factor"] > 0


def test_summary_loads(current):
    s = current.summary()
    cfg = current.config
    assert s.loc["Total", "ibnr_selected"] == pytest.approx(s.drop("Total")["ibnr_selected"].sum())
    assert s.loc["Total", "margin"] == pytest.approx(s.loc["Total", "ibnr_selected"] * cfg.margin_pct)
    t = s.loc["Total"]
    assert t["total_liability"] == pytest.approx(t["ibnr_selected"] + t["margin"] + t["cae"])
    assert t["chain_ladder_p75"] < t["chain_ladder_p95"]


def test_rollforward_identity(book, current):
    claims, members, *_ = book
    prior = valuation.run(claims, members, VAL - 1)
    rf = valuation.rollforward(current, prior)
    for _, r in rf.iterrows():
        assert r["expected_remaining"] + r["development"] + r["new_month_ibnr"] == pytest.approx(r["current_ibnr"])
    assert rf.loc["Total", "prior_ibnr"] == pytest.approx(rf.drop("Total")["prior_ibnr"].sum())


def test_trend_fit_recovers_known_trend():
    months = pd.period_range("2023-01", "2026-06", freq="M")
    season = pd.Series(synthetic.SEASONALITY, index=range(1, 13))
    pmpm = pd.Series(400 * 1.07 ** (np.arange(len(months)) / 12) * season.reindex(months.month).to_numpy(), index=months)
    fit = trend.fit(pmpm, pd.Series(True, index=months), fit_months=30, base_months=12)
    assert fit.annual_trend == pytest.approx(0.07, abs=1e-6)
    assert fit.r_squared == pytest.approx(1.0)
    # Projection reproduces the noiseless series.
    np.testing.assert_allclose(fit.expected_pmpm(months[-6:]).to_numpy(), pmpm.iloc[-6:].to_numpy(), rtol=1e-9)


def test_trend_override(book):
    claims, members, *_ = book
    v = valuation.run(claims, members, VAL, ValuationConfig(selected_annual_trend=0.0))
    assert all(r.trend.annual_trend == 0.0 for r in v.categories.values())


def test_paid_month_diagnostic_flags_backlog(current):
    d = valuation.paid_month_diagnostic(current)
    assert d.loc["2026-06", "actual_to_expected"] < 0.95
    assert d.loc["2026-07", "actual_to_expected"] > 1.05
    normal = d.drop(["2026-06", "2026-07"])["actual_to_expected"]
    assert ((normal - 1).abs() < 0.05).all()


def test_hindsight_runs(book, current):
    claims, members, truth, _ = book
    h = valuation.hindsight(claims, members, current, range(6, 4, -1), truth)
    assert list(h.index) == ["2026-03", "2026-04"]
    assert {"true_ibnr", "ibnr_selected_error_pct"} <= set(h.columns)
