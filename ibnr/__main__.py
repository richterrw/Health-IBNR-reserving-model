"""Command line: ``python -m ibnr --valuation-month 2026-09``."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from . import excel_model, report, site, synthetic, triangle, valuation
from .config import ValuationConfig


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Monthly health IBNR valuation")
    p.add_argument("--valuation-month", default="2026-09", help="Paid-through month, YYYY-MM")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--site-dir", default="docs", help="Where to write the GitHub Pages site; 'none' to skip")
    p.add_argument("--selections", default="selections.json", help="Actuarial selections log; 'none' for a mechanical run")
    p.add_argument("--regenerate", action="store_true", help="Rebuild the synthetic data set first")
    p.add_argument("--no-large-claims", action="store_true", help="Leave large claimants in the inpatient triangle")
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
    if args.selections.lower() != "none" and Path(args.selections).exists():
        cfg = cfg.with_selections(args.selections)

    book = triangle.load(data)
    if args.no_large_claims:
        book = replace(book, large_claims=None)
    val = pd.Period(args.valuation_month, "M")

    truth_df = truth = None
    if (data / "true_ultimate.csv").exists():
        truth_df = pd.read_csv(data / "true_ultimate.csv")
        truth = truth_df.groupby("incurred_month")["true_incurred"].sum()
        truth.index = pd.PeriodIndex(truth.index, freq="M")

    current = valuation.run(book, val, cfg)
    pack = report.ReportPack(
        valuation=current,
        rollforward=valuation.rollforward(current, valuation.run(book, val - 1, cfg)),
        hindsight=valuation.hindsight(book, current, range(args.hindsight_months, 2, -1), truth_df),
        diagnostic=valuation.paid_month_diagnostic(current),
        reconciliation=valuation.reconcile(book, current),
        mechanical=valuation.run(book, val, cfg.mechanical()) if cfg.has_judgment else None,
        truth=truth,
    )
    out = Path(args.out_dir)
    paths = report.write_all(pack, out)
    paths["model"] = excel_model.write(current, out / f"ibnr_model_{val}.xlsx")
    if args.site_dir.lower() != "none":
        paths["site"] = site.write(pack, paths["charts"], Path(args.site_dir))

    s = current.summary().loc["Total"]
    print(f"Valuation {val}: selected IBNR ${s['ibnr_selected']:,.0f}; total liability ${s['total_liability']:,.0f}")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
