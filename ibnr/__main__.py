"""Command line: ``python -m ibnr --valuation-month 2026-09``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import report, synthetic, triangle, valuation
from .config import ValuationConfig


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Monthly health IBNR valuation")
    p.add_argument("--valuation-month", default="2026-09", help="Paid-through month, YYYY-MM")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--regenerate", action="store_true", help="Rebuild the synthetic data set first")
    p.add_argument("--hindsight-months", type=int, default=12, help="Number of prior valuations to back-test")
    p.add_argument("--cf-avg-months", type=int, default=ValuationConfig.cf_avg_months)
    p.add_argument("--pmpm-lags", type=int, default=ValuationConfig.pmpm_lags)
    p.add_argument("--trend", type=float, default=None, help="Override annual PMPM trend, e.g. 0.07")
    p.add_argument("--margin", type=float, default=ValuationConfig.margin_pct)
    args = p.parse_args(argv)

    data = Path(args.data_dir)
    if args.regenerate or not (data / "claims.csv").exists():
        synthetic.write(data, valuation_month=args.valuation_month)

    cfg = ValuationConfig(
        cf_avg_months=args.cf_avg_months,
        pmpm_lags=args.pmpm_lags,
        selected_annual_trend=args.trend,
        margin_pct=args.margin,
    )
    claims, members = triangle.load(data / "claims.csv", data / "membership.csv")
    val = pd.Period(args.valuation_month, "M")

    truth_df = None
    truth = None
    if (data / "true_ultimate.csv").exists():
        truth_df = pd.read_csv(data / "true_ultimate.csv")
        truth = truth_df.groupby("incurred_month")["true_incurred"].sum()
        truth.index = pd.PeriodIndex(truth.index, freq="M")

    current = valuation.run(claims, members, val, cfg)
    prior = valuation.run(claims, members, val - 1, cfg)
    rf = valuation.rollforward(current, prior)
    h = valuation.hindsight(claims, members, current, range(args.hindsight_months, 2, -1), truth_df)
    diag = valuation.paid_month_diagnostic(current)
    paths = report.write_all(current, rf, h, diag, Path(args.out_dir), truth)

    s = current.summary().loc["Total"]
    print(f"Valuation {val}: selected IBNR ${s['ibnr_selected']:,.0f}; total liability ${s['total_liability']:,.0f}")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
