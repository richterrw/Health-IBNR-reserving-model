# Health IBNR Reserving Model

A monthly medical IBNR valuation, built the way a health plan valuation team runs its month-end close:

1. Build **paid-claims lag triangles** (incurred month × months of development) by service category.
2. Estimate reserves with the **completion factor method**, and benchmark against the **chain ladder** with **Mack** standard errors.
3. Run a **PMPM trend analysis** (log-linear trend with calendar-month seasonality). It sets the expected cost for months too immature to rely on paid claims.
4. Produce a **monthly reserve report**: reserve summary with margin and CAE, roll-forward from the prior close, hindsight test, paid-month diagnostic, and a full Excel workbook of supporting exhibits.

**[Read the September 2026 reserve report →](output/reserve_report_2026-09.md)**

![IBNR by incurred month](output/charts/ibnr_by_month.png)

## Quick start

```bash
pip install -r requirements.txt
python -m ibnr --valuation-month 2026-09     # writes output/reserve_report_2026-09.{md,xlsx} + charts
python -m pytest -q                          # 16 tests, including the published Taylor-Ashe / Mack benchmark
```

Useful flags: `--regenerate` (rebuild the synthetic data), `--cf-avg-months 3`, `--pmpm-lags 2`, `--trend 0.07` (override fitted trend), `--margin 0.10`, `--hindsight-months 18`.

## Data

The model uses **synthetic** commercial medical claims (`ibnr/synthetic.py`) for about 185k–222k members from January 2023 to September 2026. The data is shaped like a warehouse extract:

| File | Grain |
|---|---|
| `data/claims.csv` | incurred month × paid month × service category: paid $ and claim count |
| `data/membership.csv` | member months by month |
| `data/true_ultimate.csv` | **answer key**: true incurred by month and category. A real plan never has this; it is used only to validate the model. |

The generator includes the problems a real book throws at you:

* **Category-specific lag patterns.** Inpatient is slow (about 14% paid in the incurred month); professional is fast (about 32%).
* **PMPM trend and deductible seasonality.** Trends are about 5–8% a year by category; Q1 runs low and Q4 high.
* **Inpatient large-claimant shocks.**
* **Claims paying faster over time** (auto-adjudication). Old link ratios therefore overstate the remaining runout.
* **A processing backlog** in paid month June 2026, with catch-up in July.

To run on real data, drop in CSVs with the same columns (`incurred_month`, `paid_month`, `service_category`, `paid_amount`; `incurred_month`, `member_months`) and leave out `true_ultimate.csv`.

## Methodology

| Step | Approach |
|---|---|
| Link ratios | Completion factor method: straight average of the latest 6 incurred months at each lag, excluding the high and low. Chain ladder: volume-weighted over all history. Lags 36+ are complete. |
| Completion factors | `CF[k] = 1 / ∏_{j≥k} f[j]`; ultimate = paid ÷ CF[age] |
| Immature months (latest 3) | Bornhuetter-Ferguson on a PMPM expected: `ultimate = paid + (1 − CF) × PMPM_expected × member months` |
| PMPM expected | `log PMPM = a + b·t + month effects`, fitted on the latest 30 credible months. The base is the last 12 months, deseasonalised and trended to the target month. |
| Range | Mack (1993) standard error on the chain ladder, with a lognormal 75th and 95th percentile |
| Loads | 7.5% margin (provision for adverse deviation) and 2.5% CAE. Both are configurable in `ibnr/config.py`. |
| Roll-forward | Prior IBNR − paid in month = expected remaining. Current IBNR on those months − expected remaining = development. |
| Hindsight | Re-run each of the last 10 month-ends on the data as of that date, then compare with true (or hindsight) IBNR. |
| Paid-month diagnostic | Actual ÷ expected payments by calendar month. Flags backlogs and catch-ups that distort the link ratios on their diagonals. |

Completion factors and the chain ladder use the same arithmetic (`CF = 1/CDF`). What separates them is **how the factors are selected**. Health practice uses short, recent averages because claims operations change month to month. All-history volume weighting is the classic chain ladder and the basis of Mack's variance.

## Results at the September 2026 valuation

| | IBNR | vs. true IBNR ($207.5M) |
|---|---|---|
| **Selected** (CF + PMPM/B-F) | **$209.2M** | **+0.8%** |
| Completion factor only | $219.6M | +5.8% |
| Chain ladder (all-history VWA) | $236.0M | +13.7% |

Recommended liability is **$230.6M** after margin and CAE. Over 10 prior month-ends, the selected method's mean absolute error against true IBNR is **2.8%**, against roughly 10% for the chain ladder. The largest miss (−7.8%) was the June 2026 close, run in the middle of the processing backlog. The paid-month diagnostic flags that month.

![Hindsight test](output/charts/hindsight.png)

## Layout

```
ibnr/
  synthetic.py   synthetic claims + membership generator
  triangle.py    lag triangle construction, as-of-date slicing
  methods.py     link ratios, factor selection, completion factors, chain ladder, Mack
  trend.py       PMPM trend fit, seasonality, rolling-12 / 12-over-12 trend
  valuation.py   per-category valuation, hybrid selection, roll-forward, hindsight, diagnostics
  report.py      Excel workbook, markdown report, charts
  config.py      every assumption in one dataclass
  __main__.py    CLI
tests/           unit tests (Taylor-Ashe benchmark) and end-to-end checks against the answer key
output/          September 2026 report, workbook and charts
```

## Excel workbook

`output/reserve_report_2026-09.xlsx` contains:

* Summary, Rollforward, By Month, PMPM Trend, Trend Fit, Seasonality, Hindsight, Paid Month Diag
* For each category: Factors (selected link ratios and completion factors under both methods), Triangle, Link Ratios, Monthly, and Mack
* Assumptions
