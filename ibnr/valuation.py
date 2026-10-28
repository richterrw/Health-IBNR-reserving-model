"""Run a monthly valuation: per-category reserves, totals, roll-forward and hindsight."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import methods, trend, triangle
from .config import ValuationConfig


@dataclass
class CategoryResult:
    category: str
    triangle: pd.DataFrame
    link_ratios: pd.DataFrame
    cf_link: pd.Series  # completion-factor-method selected link ratios
    cl_link: pd.Series  # chain-ladder volume-weighted link ratios
    completion: pd.DataFrame  # by lag: CF method CF, chain ladder CF
    trend: trend.TrendFit
    monthly: pd.DataFrame  # by incurred month: paid, ultimates by method, IBNR
    mack: pd.DataFrame


@dataclass
class Valuation:
    valuation_month: pd.Period
    config: ValuationConfig
    categories: dict[str, CategoryResult]
    total_mack: pd.DataFrame
    members: pd.Series
    monthly: pd.DataFrame = field(init=False)  # all categories, long format
    total_monthly: pd.DataFrame = field(init=False)

    def __post_init__(self) -> None:
        frames = [r.monthly.assign(service_category=c) for c, r in self.categories.items()]
        self.monthly = pd.concat(frames)
        num = self.monthly.drop(columns=["service_category", "age", "completion_factor", "method"])
        tot = num.groupby(level=0).sum()
        tot["member_months"] = self.members.reindex(tot.index)
        tot["age"] = [(self.valuation_month - m).n for m in tot.index]
        tot["selected_pmpm"] = tot["selected_ultimate"] / tot["member_months"]
        tot["completion_factor"] = tot["paid"] / tot["selected_ultimate"]
        self.total_monthly = tot

    def summary(self) -> pd.DataFrame:
        """Reserve summary by category: paid, IBNR by method, margin, CAE, liability."""
        cfg = self.config
        rows = []
        for cat, r in list(self.categories.items()) + [("Total", None)]:
            m = self.total_monthly if r is None else r.monthly
            mk = self.total_mack if r is None else r.mack
            ibnr = m["selected_ibnr"].sum()
            margin = ibnr * cfg.margin_pct
            cae = (ibnr + margin) * cfg.cae_pct
            total_se = mk.loc["Total", "se"]
            row = {
                "service_category": cat,
                "paid_to_date": m["paid"].sum(),
                "ibnr_completion_factor": m["cf_ibnr"].sum(),
                "ibnr_chain_ladder": m["cl_ibnr"].sum(),
                "ibnr_selected": ibnr,
                "margin": margin,
                "cae": cae,
                "total_liability": ibnr + margin + cae,
                "chain_ladder_se": total_se,
            }
            for p in cfg.range_percentiles:
                row[f"chain_ladder_p{int(p * 100)}"] = methods.lognormal_percentile(mk.loc["Total", "reserve"], total_se, p)
            rows.append(row)
        return pd.DataFrame(rows).set_index("service_category")


def run_category(claims: pd.DataFrame, members: pd.Series, val: pd.Period, category: str, cfg: ValuationConfig) -> CategoryResult:
    cum = triangle.build(claims, val, category)
    n = cum.shape[1]
    lr = methods.link_ratios(cum)
    cf_link = methods.select_straight_average(lr, cfg.cf_avg_months, cfg.cf_exclude_hi_lo, cfg.max_lag)
    cl_link = methods.select_volume_weighted(cum, cfg.cl_avg_months, cfg.max_lag)
    cf = methods.completion_factors(cf_link, n)
    cl_cf = methods.completion_factors(cl_link, n)

    paid = triangle.latest_diagonal(cum)
    age = triangle.ages(cum)
    mm = members.reindex(cum.index)
    cf_by_month = cf.reindex(age.to_numpy()).to_numpy()
    cf_ult = paid / cf_by_month
    cl_ult = paid / cl_cf.reindex(age.to_numpy()).to_numpy()

    # Trend is fitted on the completion-factor estimates of credible months.
    credible = age >= cfg.pmpm_lags
    fit = trend.fit(cf_ult / mm, credible, cfg.trend_fit_months, cfg.base_period_months, cfg.selected_annual_trend)
    expected = fit.expected_pmpm(cum.index) * mm
    bf_ult = paid + (1 - cf_by_month) * expected

    selected = np.where(credible, cf_ult, bf_ult)
    monthly = pd.DataFrame(
        {
            "member_months": mm,
            "age": age,
            "paid": paid,
            "completion_factor": cf_by_month,
            "cf_ultimate": cf_ult,
            "expected_claims": expected,
            "bf_ultimate": bf_ult,
            "cl_ultimate": cl_ult,
            "selected_ultimate": selected,
            "method": np.where(credible, "Completion factor", "PMPM / B-F"),
        }
    )
    monthly["cf_ibnr"] = monthly["cf_ultimate"] - paid
    monthly["cl_ibnr"] = monthly["cl_ultimate"] - paid
    monthly["selected_ibnr"] = monthly["selected_ultimate"] - paid
    monthly["selected_pmpm"] = monthly["selected_ultimate"] / mm

    completion = pd.DataFrame(
        {
            "cf_link_ratio": cf_link.reindex(range(n), fill_value=1.0),
            "cf_completion": cf,
            "cl_link_ratio": cl_link.reindex(range(n), fill_value=1.0),
            "cl_completion": cl_cf,
        }
    )
    completion.index.name = "lag"
    return CategoryResult(category, cum, lr, cf_link, cl_link, completion, fit, monthly, methods.mack(cum, cl_link, cfg.max_lag))


def run(claims: pd.DataFrame, members: pd.Series, valuation_month: str | pd.Period, cfg: ValuationConfig | None = None) -> Valuation:
    cfg = cfg or ValuationConfig()
    val = pd.Period(valuation_month, "M")
    cats = sorted(claims["service_category"].unique())
    results = {c: run_category(claims, members, val, c, cfg) for c in cats}
    total_cum = triangle.build(claims, val)
    total_mack = methods.mack(total_cum, methods.select_volume_weighted(total_cum, cfg.cl_avg_months, cfg.max_lag), cfg.max_lag)
    return Valuation(val, cfg, results, total_mack, members)


def rollforward(current: Valuation, prior: Valuation) -> pd.DataFrame:
    """Reserve roll-forward from the prior valuation to the current one.

    For incurred months already open at the prior valuation:
        prior IBNR - paid this month = expected remaining IBNR
        current IBNR - expected remaining = development (+ adverse / - favourable)
    The new incurred month enters as a separate line.
    """
    rows = []
    for cat in list(current.categories) + ["Total"]:
        cur = current.total_monthly if cat == "Total" else current.categories[cat].monthly
        pri = prior.total_monthly if cat == "Total" else prior.categories[cat].monthly
        old = pri.index
        prior_ibnr = pri["selected_ibnr"].sum()
        paid_in_month = (cur.loc[old, "paid"] - pri["paid"]).sum()
        expected_remaining = prior_ibnr - paid_in_month
        current_old = cur.loc[old, "selected_ibnr"].sum()
        new = cur.index.difference(old)
        rows.append(
            {
                "service_category": cat,
                "prior_ibnr": prior_ibnr,
                "paid_on_prior_months": paid_in_month,
                "expected_remaining": expected_remaining,
                "current_ibnr_prior_months": current_old,
                "development": current_old - expected_remaining,
                "development_pct_of_prior": (current_old - expected_remaining) / prior_ibnr,
                "new_month_ibnr": cur.loc[new, "selected_ibnr"].sum(),
                "current_ibnr": cur["selected_ibnr"].sum(),
            }
        )
    return pd.DataFrame(rows).set_index("service_category")


def hindsight(claims: pd.DataFrame, members: pd.Series, current: Valuation, lookbacks: range, truth: pd.DataFrame | None = None) -> pd.DataFrame:
    """Re-run prior valuations on the data as it looked then; compare IBNR to hindsight.

    Hindsight IBNR at valuation ``v`` = current selected ultimate for months
    <= v, minus what had been paid at ``v``. When a synthetic answer key is
    supplied, the true IBNR at ``v`` is reported as well.
    """
    if truth is not None:
        true_ult = truth.groupby("incurred_month")["true_incurred"].sum()
        true_ult.index = pd.PeriodIndex(true_ult.index, freq="M")
    rows = []
    for back in lookbacks:
        v = current.valuation_month - back
        past = run(claims, members, v, current.config)
        tm = past.total_monthly
        paid_then = tm["paid"]
        months = tm.index
        row = {
            "valuation_month": str(v),
            "months_of_runout": back,
            "ibnr_completion_factor": tm["cf_ibnr"].sum(),
            "ibnr_chain_ladder": tm["cl_ibnr"].sum(),
            "ibnr_selected": tm["selected_ibnr"].sum(),
            "hindsight_ibnr": (current.total_monthly.loc[months, "selected_ultimate"] - paid_then).sum(),
        }
        if truth is not None:
            row["true_ibnr"] = (true_ult.reindex(months) - paid_then).sum()
        rows.append(row)
    df = pd.DataFrame(rows).set_index("valuation_month")
    basis = "true_ibnr" if truth is not None else "hindsight_ibnr"
    for col in ("ibnr_completion_factor", "ibnr_chain_ladder", "ibnr_selected"):
        df[f"{col}_error_pct"] = df[col] / df[basis] - 1
    return df


def paid_month_diagnostic(v: Valuation, months: int = 12, max_dev_lag: int = 12) -> pd.DataFrame:
    """Actual vs expected payments by paid (calendar) month.

    For each recent paid month, expected payments on incurred months already
    open at the start of the month are ``C[i, k] * (f[k] - 1)`` using the
    selected completion-factor link ratios. A ratio well below 1 followed by
    one well above 1 is the signature of a processing backlog and catch-up;
    such diagonals distort the link ratios they sit in.
    """
    rows = []
    for back in range(months - 1, -1, -1):
        p = v.valuation_month - back
        actual = expected = 0.0
        for r in v.categories.values():
            C = r.triangle
            for i, inc in enumerate(C.index):
                k = (p - inc).n - 1  # lag at the start of paid month p
                if k < 0 or k + 1 >= C.shape[1] or k >= max_dev_lag:
                    continue
                prev, cur = C.iat[i, k], C.iat[i, k + 1]
                actual += cur - prev
                expected += prev * (r.cf_link.get(k, 1.0) - 1)
        rows.append({"paid_month": str(p), "actual_paid": actual, "expected_paid": expected, "actual_to_expected": actual / expected})
    return pd.DataFrame(rows).set_index("paid_month")
