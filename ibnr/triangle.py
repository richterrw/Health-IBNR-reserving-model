"""Lag triangles: incurred month (rows) x months of development (columns)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Book:
    """Everything a valuation reads from the warehouse."""

    claims: pd.DataFrame  # incurred_month, paid_month, service_category, paid_amount
    members: pd.Series  # member months by incurred month
    large_claims: pd.DataFrame | None = None  # claimant_id, incurred_month, paid_month, paid_amount
    pended: pd.DataFrame | None = None  # paid_month, service_category, excess_pended


def _periods(df: pd.DataFrame, cols: tuple[str, ...] = ("incurred_month", "paid_month")) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.PeriodIndex(df[c].astype(str), freq="M")
    return df


def load(data_dir: str | Path) -> Book:
    d = Path(data_dir)
    claims = _periods(pd.read_csv(d / "claims.csv"))
    mem = pd.read_csv(d / "membership.csv")
    members = pd.Series(mem["member_months"].values, index=pd.PeriodIndex(mem["incurred_month"], freq="M"), name="member_months")
    large = _periods(pd.read_csv(d / "large_claims.csv")) if (d / "large_claims.csv").exists() else None
    pended = None
    if (d / "pended_inventory.csv").exists():
        pended = _periods(pd.read_csv(d / "pended_inventory.csv"), ("paid_month",))
    return Book(claims, members, large, pended)


def as_of(claims: pd.DataFrame, valuation_month: pd.Period) -> pd.DataFrame:
    """Claims data as it would have looked at the close of ``valuation_month``."""
    return claims[(claims["paid_month"] <= valuation_month) & (claims["incurred_month"] <= valuation_month)]


def build(
    claims: pd.DataFrame,
    valuation_month: pd.Period,
    category: str | None = None,
    value: str = "paid_amount",
    start: pd.Period | None = None,
) -> pd.DataFrame:
    """Cumulative paid triangle. Cells beyond the valuation diagonal are NaN.

    Row index: incurred month. Columns: lag 0..n-1, where lag 0 is payment
    within the incurred month.
    """
    df = as_of(claims, valuation_month)
    if category is not None:
        df = df[df["service_category"] == category]
    lag = (df["paid_month"] - df["incurred_month"]).map(lambda d: d.n)
    inc = df.assign(lag=lag.values).pivot_table(index="incurred_month", columns="lag", values=value, aggfunc="sum")
    start = start if start is not None else df["incurred_month"].min()
    rows = pd.period_range(start, valuation_month, freq="M")
    n = len(rows)
    inc = inc.reindex(index=rows, columns=range(n)).fillna(0.0)
    inc.columns.name = None
    cum = inc.cumsum(axis=1)
    age = np.array([(valuation_month - r).n for r in rows])
    mask = np.arange(n)[None, :] > age[:, None]
    cum = cum.mask(mask)
    cum.index.name = "incurred_month"
    cum.columns.name = "lag"
    return cum


def incremental(cum: pd.DataFrame) -> pd.DataFrame:
    inc = cum.diff(axis=1)
    inc[0] = cum[0]
    return inc


def latest_diagonal(cum: pd.DataFrame) -> pd.Series:
    """Paid to date per incurred month."""
    return cum.ffill(axis=1).iloc[:, -1]


def ages(cum: pd.DataFrame) -> pd.Series:
    """Lag of the latest observed cell per incurred month (0 = valuation month)."""
    return cum.notna().sum(axis=1) - 1
