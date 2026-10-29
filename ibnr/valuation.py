"""Run a monthly valuation: per-category reserves, totals, roll-forward and hindsight."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import methods, trend, triangle
from .config import ValuationConfig
from .triangle import Book

LARGE = "Large claims"
COLUMNS = ["incurred_month", "paid_month", "service_category", "paid_amount"]


@dataclass
class CategoryResult:
    category: str
    triangle: pd.DataFrame
    link_ratios: pd.DataFrame
    cf_link: pd.Series  # selected link ratios used for reserving (after judgment)
    cl_link: pd.Series  # chain-ladder volume-weighted link ratios (mechanical benchmark)
    completion: pd.DataFrame  # by lag: selected CF, chain ladder CF
    trend: trend.TrendFit | None  # None for the large-claim pool
    monthly: pd.DataFrame  # by incurred month: paid, ultimates by method, IBNR
    mack: pd.DataFrame
    exclude_mask: pd.DataFrame | None  # link ratios left out of the averages
    used_cells: dict[int, list] = field(default_factory=dict)  # incurred months feeding each average
    restate_ratio: float = 1.0  # backlog gross-up applied to the latest diagonal


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
        num = self.monthly.drop(columns=["service_category", "age", "completion_factor", "method", "member_months"])
        tot = num.groupby(level=0).sum()
        tot.insert(0, "member_months", self.members.reindex(tot.index))
        tot.insert(1, "age", [(self.valuation_month - m).n for m in tot.index])
        tot["selected_pmpm"] = tot["selected_ultimate"] / tot["member_months"]
        tot["completion_factor"] = tot["paid"] / tot["selected_ultimate"]
        self.total_monthly = tot

    @property
    def has_large(self) -> bool:
        return LARGE in self.categories

    def label(self, category: str) -> str:
        if category == "Inpatient" and self.has_large:
            return "Inpatient (ex. large)"
        if category == LARGE:
            return f"Large claims (>${self.config.large_claim_threshold / 1000:,.0f}k)"
        return category

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
                "service_category": "Total" if r is None else self.label(cat),
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


# --------------------------------------------------------------------------- factors

def _select(cum: pd.DataFrame, category: str, cfg: ValuationConfig, volume_weighted: bool):
    lr = methods.link_ratios(cum)
    mask = methods.paid_month_mask(lr, cfg.exclude_paid_months) if cfg.exclude_paid_months else None
    if volume_weighted:
        sel = methods.select_volume_weighted(cum, None, cfg.max_lag, mask)
        # Every month observed at both lags feeds a volume-weighted average.
        used = {}
        for k in lr.columns:
            ok = cum[k].notna() & cum[k + 1].notna()
            if mask is not None:
                ok &= ~mask[k]
            used[k] = list(cum.index[ok])
    else:
        sel = methods.select_straight_average(lr, cfg.cf_avg_months, cfg.cf_exclude_hi_lo, cfg.max_lag, mask)
        used = methods.used_cells(lr, cfg.cf_avg_months, mask)
    for lag, value in cfg.factor_overrides.get(category, {}).items():
        sel[lag] = value
    cl = methods.select_volume_weighted(cum, cfg.cl_avg_months, cfg.max_lag)
    return lr, mask, used, sel, cl


def diagonal_actual_expected(pairs: list[tuple[pd.DataFrame, pd.Series]], paid_month: pd.Period, max_dev_lag: int = 12) -> tuple[float, float]:
    """Actual and expected payments in one paid month on already-open incurred months.

    Expected for incurred month i at lag k (start of month) is ``C[i,k] * (f[k] - 1)``.
    """
    actual = expected = 0.0
    for C, f in pairs:
        for i, inc in enumerate(C.index):
            k = (paid_month - inc).n - 1
            if k < 0 or k + 1 >= C.shape[1] or k >= max_dev_lag:
                continue
            prev, cur = C.iat[i, k], C.iat[i, k + 1]
            if np.isnan(cur):
                continue
            actual += cur - prev
            expected += prev * (f.get(k, 1.0) - 1)
    return actual, expected


def _restated_paid(cum: pd.DataFrame, ratio: float) -> pd.Series:
    """Paid to date with the latest diagonal's payments grossed up by ``1 / ratio``."""
    paid = triangle.latest_diagonal(cum)
    if ratio == 1.0:
        return paid
    prev = _restated_paid_prev(cum)
    return prev + (paid - prev) / ratio


def _completion(cf_link: pd.Series, cl_link: pd.Series, n: int) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "cf_link_ratio": cf_link.reindex(range(n), fill_value=1.0),
            "cf_completion": methods.completion_factors(cf_link, n),
            "cl_link_ratio": cl_link.reindex(range(n), fill_value=1.0),
            "cl_completion": methods.completion_factors(cl_link, n),
        }
    )
    df.index.name = "lag"
    return df


def _frame(mm, age, paid, cf_by_month, cf_ult, expected, bf_ult, cl_ult, selected, method) -> pd.DataFrame:
    df = pd.DataFrame(
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
            "method": method,
        }
    )
    df["cf_ibnr"] = df["cf_ultimate"] - paid
    df["cl_ibnr"] = df["cl_ultimate"] - paid
    df["selected_ibnr"] = df["selected_ultimate"] - paid
    df["selected_pmpm"] = df["selected_ultimate"] / mm
    return df


# --------------------------------------------------------------------------- estimation

def _estimate_category(category, cum, sel, members, cfg, ratio) -> CategoryResult:
    lr, mask, used, cf_link, cl_link = sel
    n = cum.shape[1]
    comp = _completion(cf_link, cl_link, n)
    paid = triangle.latest_diagonal(cum)
    paid_est = _restated_paid(cum, ratio)
    age = triangle.ages(cum)
    mm = members.reindex(cum.index)
    cf_by_month = comp["cf_completion"].reindex(age.to_numpy()).to_numpy()
    cf_ult = paid_est / cf_by_month
    cl_ult = paid / comp["cl_completion"].reindex(age.to_numpy()).to_numpy()

    # Trend is fitted on the completion-factor estimates of credible months.
    credible = age >= cfg.pmpm_lags
    fit = trend.fit(cf_ult / mm, credible, cfg.trend_fit_months, cfg.base_period_months, cfg.selected_annual_trend)
    expected = fit.expected_pmpm(cum.index) * mm
    bf_ult = paid_est + (1 - cf_by_month) * expected
    selected = np.where(credible, cf_ult, bf_ult)
    method = np.where(credible, "Completion factor", "PMPM / B-F")
    monthly = _frame(mm, age, paid, cf_by_month, cf_ult, expected, bf_ult, cl_ult, selected, method)
    return CategoryResult(category, cum, lr, cf_link, cl_link, comp, fit, monthly, methods.mack(cum, cl_link, cfg.max_lag), mask, used, ratio)


def _estimate_large(cum, sel, members, cfg, ratio) -> CategoryResult:
    """Large claims: B-F on a pooled, trended large-claim PMPM for every month.

    Large-claim experience is too thin and lumpy for paid / CF to be credible
    in any single month, so each month gets
    ``paid + (1 - CF) * pooled PMPM * member months``. Factors are
    volume-weighted over all history (thin data needs the volume).
    """
    lr, mask, used, cf_link, cl_link = sel
    n = cum.shape[1]
    comp = _completion(cf_link, cl_link, n)
    paid = triangle.latest_diagonal(cum)
    paid_est = _restated_paid(cum, ratio)
    age = triangle.ages(cum)
    mm = members.reindex(cum.index)
    cf_by_month = comp["cf_completion"].reindex(age.to_numpy()).to_numpy()
    cf_ult = paid_est / cf_by_month
    cl_ult = paid / comp["cl_completion"].reindex(age.to_numpy()).to_numpy()

    pool = (cf_ult / mm)[age >= cfg.large_claim_credible_lag].iloc[-cfg.large_claim_experience_months :]
    g = 1 + cfg.large_claim_trend
    pmpm = pd.Series([np.mean([v * g ** ((t - m).n / 12) for m, v in pool.items()]) for t in cum.index], index=cum.index)
    expected = pmpm * mm
    bf_ult = paid_est + (1 - cf_by_month) * expected
    monthly = _frame(mm, age, paid, cf_by_month, cf_ult, expected, bf_ult, cl_ult, bf_ult.to_numpy(), "Large-claim B-F")
    return CategoryResult(LARGE, cum, lr, cf_link, cl_link, comp, None, monthly, methods.mack(cum, cl_link, cfg.max_lag), mask, used, ratio)


def _latest_increment(cum: pd.DataFrame) -> float:
    """Total paid in the valuation month (the latest diagonal's increments)."""
    return float(triangle.latest_diagonal(cum).sum() - _restated_paid_prev(cum).sum())


def _restated_paid_prev(cum: pd.DataFrame) -> pd.Series:
    age = triangle.ages(cum)
    return pd.Series([cum.iat[i, a - 1] if a > 0 else 0.0 for i, a in enumerate(age)], index=cum.index)


def _backlog_ratios(book: Book, val: pd.Period, triangles: dict, sels: dict) -> dict[str, float]:
    """Paid-in-month / (paid-in-month + excess pended) per category.

    Uses claims operations' pended inventory when it covers the month. Without
    one, falls back to the measured actual-to-expected on routine claims.
    """
    pend = None
    if book.pended is not None:
        pend = book.pended[book.pended["paid_month"] == val].set_index("service_category")["excess_pended"]
    if pend is not None and len(pend):
        ratios = {}
        for c in triangles:
            if c == LARGE:
                continue
            paid_in_month = _latest_increment(triangles[c])
            if c == "Inpatient" and LARGE in triangles:
                paid_in_month += _latest_increment(triangles[LARGE])
            ratios[c] = paid_in_month / (paid_in_month + float(pend.get(c, 0.0)))
        if LARGE in triangles:
            ratios[LARGE] = ratios["Inpatient"]
        return ratios
    a, e = diagonal_actual_expected([(triangles[c], sels[c][3]) for c in triangles if c != LARGE], val)
    return {c: (a / e if e > 0 else 1.0) for c in triangles}


def run(book: Book, valuation_month: str | pd.Period, cfg: ValuationConfig | None = None) -> Valuation:
    """Value every category at ``valuation_month`` using data as of that close.

    If the book has claimant-level large claims, they are removed from the
    inpatient triangle and reserved as their own line.
    """
    cfg = cfg or ValuationConfig()
    val = pd.Period(valuation_month, "M")
    claims = book.claims
    start = claims["incurred_month"].min()
    cats = sorted(claims["service_category"].unique())

    base = claims[COLUMNS]
    triangles: dict[str, pd.DataFrame] = {}
    if book.large_claims is not None:
        lc = book.large_claims.assign(service_category="Inpatient")[COLUMNS]
        base = pd.concat([base, lc.assign(paid_amount=-lc["paid_amount"])])
    for c in cats:
        triangles[c] = triangle.build(base, val, c, start=start)
    if book.large_claims is not None:
        triangles[LARGE] = triangle.build(lc.assign(service_category=LARGE), val, LARGE, start=start)

    sels = {c: _select(cum, c, cfg, volume_weighted=(c == LARGE)) for c, cum in triangles.items()}

    ratios = {c: 1.0 for c in triangles}
    if str(val) in cfg.restate_paid_months:
        ratios = _backlog_ratios(book, val, triangles, sels)

    results = {}
    for c, cum in triangles.items():
        if c == LARGE:
            results[c] = _estimate_large(cum, sels[c], book.members, cfg, ratios[c])
        else:
            results[c] = _estimate_category(c, cum, sels[c], book.members, cfg, ratios[c])

    total_cum = triangle.build(claims, val, start=start)
    total_mack = methods.mack(total_cum, methods.select_volume_weighted(total_cum, cfg.cl_avg_months, cfg.max_lag), cfg.max_lag)
    return Valuation(val, cfg, results, total_mack, book.members)


# --------------------------------------------------------------------------- monitoring

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
                "service_category": "Total" if cat == "Total" else current.label(cat),
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


def hindsight(book: Book, current: Valuation, lookbacks: range, truth: pd.DataFrame | None = None) -> pd.DataFrame:
    """Re-run prior valuations on the data as it looked then; compare IBNR to hindsight.

    Hindsight IBNR at valuation ``v`` = current selected ultimate for months
    <= v, minus what had been paid at ``v``. When a synthetic answer key is
    supplied, the true IBNR at ``v`` is reported as well. When the config
    carries judgmental selections, the mechanical result is shown alongside.
    """
    if truth is not None:
        true_ult = truth.groupby("incurred_month")["true_incurred"].sum()
        true_ult.index = pd.PeriodIndex(true_ult.index, freq="M")
    cfg = current.config
    rows = []
    for back in lookbacks:
        v = current.valuation_month - back
        tm = run(book, v, cfg).total_monthly
        paid_then = tm["paid"]
        months = tm.index
        row = {
            "valuation_month": str(v),
            "months_of_runout": back,
            "ibnr_completion_factor": tm["cf_ibnr"].sum(),
            "ibnr_chain_ladder": tm["cl_ibnr"].sum(),
            "ibnr_selected": tm["selected_ibnr"].sum(),
        }
        if cfg.has_judgment:
            row["ibnr_mechanical"] = run(book, v, cfg.mechanical()).total_monthly["selected_ibnr"].sum()
        row["hindsight_ibnr"] = (current.total_monthly.loc[months, "selected_ultimate"] - paid_then).sum()
        if truth is not None:
            row["true_ibnr"] = (true_ult.reindex(months) - paid_then).sum()
        rows.append(row)
    df = pd.DataFrame(rows).set_index("valuation_month")
    basis = "true_ibnr" if truth is not None else "hindsight_ibnr"
    for col in ("ibnr_completion_factor", "ibnr_chain_ladder", "ibnr_selected", "ibnr_mechanical"):
        if col in df:
            df[f"{col}_error_pct"] = df[col] / df[basis] - 1
    return df


def paid_month_diagnostic(v: Valuation, months: int = 12, max_dev_lag: int = 12) -> pd.DataFrame:
    """Actual vs expected payments by paid (calendar) month.

    For each recent paid month, expected payments on incurred months already
    open at the start of the month are ``C[i, k] * (f[k] - 1)`` using the
    selected link ratios. A ratio well below 1 followed by one well above 1
    is the signature of a processing backlog and catch-up; such diagonals
    distort the link ratios they sit in. Large claims are left out: one
    claimant's payment would read as a processing anomaly.
    """
    pairs = [(r.triangle, r.cf_link) for c, r in v.categories.items() if c != LARGE]
    rows = []
    for back in range(months - 1, -1, -1):
        p = v.valuation_month - back
        actual, expected = diagonal_actual_expected(pairs, p, max_dev_lag)
        rows.append({"paid_month": str(p), "actual_paid": actual, "expected_paid": expected, "actual_to_expected": actual / expected})
    return pd.DataFrame(rows).set_index("paid_month")


def reconcile(book: Book, v: Valuation) -> pd.DataFrame:
    """Data checks a reviewer expects before anyone looks at a factor.

    Each row: check, pass/fail, detail. Reported in the ASOP 43 data section.
    """
    val = v.valuation_month
    c = triangle.as_of(book.claims, val)
    rows = []

    def add(name: str, ok: bool, detail: str) -> None:
        rows.append({"check": name, "result": "Pass" if ok else "FAIL", "detail": detail})

    extract = c["paid_amount"].sum()
    tri = v.total_monthly["paid"].sum()
    add("Claims extract ties to triangles", abs(extract - tri) < 1.0, f"extract ${extract:,.0f} vs triangles ${tri:,.0f}")
    bad_dates = int((c["paid_month"] < c["incurred_month"]).sum())
    add("No payment before incurral", bad_dates == 0, f"{bad_dates} rows with paid month < incurred month")
    neg = int((c["paid_amount"] < 0).sum())
    add("No negative paid cells", neg == 0, f"{neg} negative incurred x paid cells")
    months = v.total_monthly.index
    missing = [str(m) for m in months if pd.isna(book.members.get(m))]
    add("Membership for every incurred month", not missing, "missing: " + (", ".join(missing) if missing else "none"))
    mm = book.members.reindex(months)
    jumps = mm.pct_change().abs()
    big = [f"{m} ({x:+.1%})" for m, x in jumps.items() if x > 0.08]
    add("Membership month-over-month change < 8%", not big, ", ".join(big) if big else "largest change " + f"{jumps.max():.1%}")
    if book.large_claims is not None:
        lc = triangle.as_of(book.large_claims, val)
        ip = c[c["service_category"] == "Inpatient"].groupby(["incurred_month", "paid_month"])["paid_amount"].sum()
        lcc = lc.groupby(["incurred_month", "paid_month"])["paid_amount"].sum()
        over = int((lcc - ip.reindex(lcc.index).fillna(0) > 1.0).sum())
        add("Large claims within inpatient totals", over == 0, f"{lc['claimant_id'].nunique()} claimants, ${lc['paid_amount'].sum():,.0f} paid; {over} cells exceed inpatient")
        small = lc.groupby("claimant_id")["paid_amount"].sum()
        add("Large-claim file is claimant level", lc.duplicated(["claimant_id", "paid_month"]).sum() == 0, f"{len(small)} unique claimants")
    return pd.DataFrame(rows).set_index("check")
