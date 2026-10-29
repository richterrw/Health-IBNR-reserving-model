"""Development methods: link ratios, completion factors, chain ladder, Mack.

Notation: ``C[i, k]`` is cumulative paid for incurred month ``i`` at lag ``k``.
A link ratio ``f[i, k] = C[i, k+1] / C[i, k]``. A completion factor at lag
``k`` is the share of ultimate paid by lag ``k``:

    CF[k] = 1 / prod_{j >= k} f[j]

so ``ultimate = paid / CF[age]``. The chain ladder CDF is ``1 / CF``. The two
methods differ only in *how the link ratios are selected*: health valuation
practice uses short, recent straight averages (claims operations change
quickly); the classic chain ladder uses volume-weighted all-history averages,
which is also what Mack's variance formula assumes.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd


def link_ratios(cum: pd.DataFrame) -> pd.DataFrame:
    """Age-to-age factors. Column ``k`` is the lag k -> k+1 ratio."""
    a = cum.iloc[:, :-1].to_numpy()
    b = cum.iloc[:, 1:].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(a > 0, b / a, np.nan)
    return pd.DataFrame(f, index=cum.index, columns=cum.columns[:-1])


def paid_month_mask(lr: pd.DataFrame, paid_months: tuple[str, ...] | list[str]) -> pd.DataFrame:
    """True where a link ratio's development lands in one of ``paid_months``.

    The ratio at (incurred month i, lag k) picks up payments made in paid
    month ``i + k + 1``, so a diagonal of the triangle is a paid month.
    """
    excluded = {pd.Period(m, "M") for m in paid_months}
    rows = [[(i + k + 1) in excluded for k in lr.columns] for i in lr.index]
    return pd.DataFrame(rows, index=lr.index, columns=lr.columns, dtype=bool)


def used_cells(lr: pd.DataFrame, n_months: int, exclude: pd.DataFrame | None = None) -> dict[int, list]:
    """Incurred months whose ratio feeds the average at each lag."""
    out = {}
    for k in lr.columns:
        col = lr[k]
        if exclude is not None:
            col = col[~exclude[k]]
        out[k] = list(col.dropna().index[-n_months:])
    return out


def select_straight_average(
    lr: pd.DataFrame, n_months: int, exclude_hi_lo: bool, max_lag: int, exclude: pd.DataFrame | None = None
) -> pd.Series:
    """Straight average of the most recent ``n_months`` ratios at each lag.

    Ratios flagged in ``exclude`` are skipped (the window reaches further
    back instead). The high and low are dropped when at least four ratios
    are available. Lags at or beyond ``max_lag`` (and lags with no data)
    select 1.0.
    """
    cells = used_cells(lr, n_months, exclude)
    out = {}
    for k in lr.columns:
        col = lr.loc[cells[k], k].to_numpy()
        if k >= max_lag or col.size == 0:
            out[k] = 1.0
            continue
        if exclude_hi_lo and col.size >= 4:
            col = np.sort(col)[1:-1]
        out[k] = float(col.mean())
    return pd.Series(out, name="link_ratio")


def select_volume_weighted(cum: pd.DataFrame, n_months: int | None, max_lag: int, exclude: pd.DataFrame | None = None) -> pd.Series:
    """Volume-weighted average ratio: sum C[i,k+1] / sum C[i,k]."""
    out = {}
    for k in cum.columns[:-1]:
        both = cum[[k, k + 1]].dropna()
        if exclude is not None:
            both = both[~exclude.loc[both.index, k]]
        if n_months is not None:
            both = both.iloc[-n_months:]
        if k >= max_lag or both.empty or both[k].sum() <= 0:
            out[k] = 1.0
            continue
        out[k] = float(both[k + 1].sum() / both[k].sum())
    return pd.Series(out, name="link_ratio")


def completion_factors(selected: pd.Series, n_lags: int) -> pd.Series:
    """CF[k] for k = 0..n_lags-1 from selected link ratios (tail = 1.0)."""
    f = selected.reindex(range(n_lags), fill_value=1.0).to_numpy()
    # A month observed at lag k still needs f[k], f[k+1], ...
    cdf = np.cumprod(f[::-1])[::-1]
    return pd.Series(1.0 / cdf, index=range(n_lags), name="completion_factor")


def mack(cum: pd.DataFrame, f: pd.Series, max_lag: int) -> pd.DataFrame:
    """Mack (1993) chain ladder standard errors.

    ``f`` must be the volume-weighted all-history factors for the variance
    formula to be the Mack estimator. Returns ultimate, reserve and standard
    error per incurred month, plus a ``Total`` row including the covariance
    between months that share estimated factors.
    """
    n = cum.shape[1]
    K = min(n - 1, max_lag)  # last lag with a non-unit factor is K-1
    C = cum.to_numpy()
    fv = f.reindex(range(n - 1), fill_value=1.0).to_numpy()

    sigma2 = np.full(K, np.nan)
    S = np.zeros(K)  # sum of C[i,k] over months used to estimate f[k]
    for k in range(K):
        ok = ~np.isnan(C[:, k + 1]) & (C[:, k] > 0)
        S[k] = C[ok, k].sum()
        m = ok.sum()
        if m >= 2:
            dev = C[ok, k + 1] / C[ok, k] - fv[k]
            sigma2[k] = (C[ok, k] * dev**2).sum() / (m - 1)
    # Mack's extrapolation for lags with fewer than two observations.
    for k in range(K):
        if np.isnan(sigma2[k]):
            prev = sigma2[:k][~np.isnan(sigma2[:k])]
            if prev.size >= 2 and prev[-2] > 0:
                sigma2[k] = min(prev[-1] ** 2 / prev[-2], prev[-2], prev[-1])
            else:
                sigma2[k] = prev[-1] if prev.size else 0.0

    age = (~np.isnan(C)).sum(axis=1) - 1
    paid = np.array([C[i, a] for i, a in enumerate(age)])
    proj = np.zeros((len(C), K + 1))
    for i, a in enumerate(age):
        proj[i, : min(a, K) + 1] = C[i, : min(a, K) + 1]
        for k in range(min(a, K), K):
            proj[i, k + 1] = proj[i, k] * fv[k]
    ult = np.array([paid[i] * np.prod(fv[min(a, K):K]) for i, a in enumerate(age)])

    mse = np.zeros(len(C))
    for i, a in enumerate(age):
        tot = 0.0
        for k in range(min(a, K), K):
            if proj[i, k] > 0 and S[k] > 0:
                tot += sigma2[k] / fv[k] ** 2 * (1 / proj[i, k] + 1 / S[k])
        mse[i] = ult[i] ** 2 * tot

    # Total reserve MSE adds the parameter-error covariance between months:
    #   sum_i U_i * (sum_{j younger than i} U_j) * sum_{k >= age_i} 2 sigma2_k / f_k^2 / S_k
    total_mse = mse.sum()
    for i, a in enumerate(age):
        younger = ult[i + 1 :].sum()
        cov = sum(2 * sigma2[k] / fv[k] ** 2 / S[k] for k in range(min(a, K), K) if S[k] > 0)
        total_mse += ult[i] * younger * cov

    out = pd.DataFrame(
        {"paid": paid, "ultimate": ult, "reserve": ult - paid, "se": np.sqrt(mse)},
        index=cum.index,
    )
    total = pd.DataFrame(
        [[out["paid"].sum(), out["ultimate"].sum(), out["reserve"].sum(), np.sqrt(total_mse)]],
        columns=out.columns,
        index=pd.Index(["Total"], name="incurred_month"),
    )
    return pd.concat([out, total])


def lognormal_percentile(mean: float, se: float, p: float) -> float:
    """Percentile of a lognormal with the given mean and standard error."""
    if mean <= 0 or se <= 0:
        return mean
    s2 = np.log(1 + (se / mean) ** 2)
    mu = np.log(mean) - s2 / 2
    return float(np.exp(mu + np.sqrt(s2) * NormalDist().inv_cdf(p)))
