# Health IBNR Reserving Model

[![tests](https://github.com/richterrw/Health-IBNR-reserving-model/actions/workflows/tests.yml/badge.svg)](https://github.com/richterrw/Health-IBNR-reserving-model/actions/workflows/tests.yml)

A monthly medical IBNR valuation, built the way a health plan valuation team runs its month-end close:

1. Build **paid-claims lag triangles** (incurred month × months of development) by service category.
2. Estimate reserves with the **completion factor method**, and benchmark against the **chain ladder** with **Mack** standard errors.
3. Pull **large claimants (>$250k)** out of inpatient and reserve them separately on a pooled, trended PMPM.
4. Run a **PMPM trend analysis** (log-linear trend with calendar-month seasonality). It sets the expected cost for months too immature to rely on paid claims.
5. Apply **actuarial judgment** through a logged selections file: diagonal exclusions, backlog restatement and factor overrides, each with its rationale.
6. Produce a **monthly reserve report**. It includes the reserve summary with margin and CAE, roll-forward, hindsight test, paid-month diagnostic, data reconciliation and **ASOP No. 43** disclosures. Alongside it are an exhibits workbook and a **live-formula Excel model**.

**[Project site →](https://richterrw.github.io/Health-IBNR-reserving-model/)** · **[Read the September 2026 reserve report →](output/reserve_report_2026-09.md)**

![Hindsight test](output/charts/hindsight.png)

## Results at the September 2026 valuation

| | IBNR | vs. true IBNR ($220.0M) | Hindsight mean abs. error, 10 prior closes |
|---|---|---|---|
| **Selected** (CF + PMPM/B-F + large-claim pool + judgment) | **$226.2M** | +2.9% | **1.9%** |
| Same, mechanical (no judgment) | $225.4M | +2.5% | 2.1% |
| Completion factor only | $227.6M | +3.5% | 4.4% |
| Chain ladder (all-history volume-weighted) | $245.5M | +11.6% | 10.3% |

* **Recommended liability: $249.3M.** That is the $226.2M best estimate plus a 7.5% margin and 2.5% claim adjustment expense.
* **Judgment matters most when operations break.** At the June 2026 close, in the middle of a claims-processing backlog, the mechanical method under-reserved by **5.0%**. Restating paid for the pended inventory and excluding the distorted diagonals brings that close to **+2.5%**, in line with an ordinary month.
* **The chain ladder over-reserves by about 10%** because claims now pay faster than they used to. All-history factors overstate the remaining runout; recent-average completion factors track the change.

"True IBNR" comes from the synthetic answer key. A real plan never has one, which is why the hindsight test is built in.

## Quick start

```bash
pip install -r requirements.txt
python -m ibnr --valuation-month 2026-09     # writes the report, exhibits, live Excel model and charts to output/
python -m pytest -q                          # 27 tests, including the published Taylor-Ashe / Mack benchmark
```

Useful flags: `--selections none` (mechanical run), `--no-large-claims`, `--regenerate`, `--cf-avg-months 3`, `--pmpm-lags 2`, `--trend 0.07`, `--margin 0.10`, `--hindsight-months 18`.

## Outputs

| File | What it is |
|---|---|
| [`output/reserve_report_2026-09.md`](output/reserve_report_2026-09.md) | The monthly reserve memo: summary, methodology, selections and their impact, trend, roll-forward, hindsight, paid-month diagnostic, ASOP 43 disclosures, items for review |
| `output/ibnr_model_2026-09.xlsx` | **Live-formula model.** The triangle is data; every link ratio, average, completion factor, ultimate, IBNR and load is an Excel formula. Typing a link ratio into a yellow override cell recalculates the reserve. The Summary sheet shows the Python result next to the workbook's (they tie to within $1). |
| `output/reserve_exhibits_2026-09.xlsx` | Supporting exhibits: triangles, link ratios, factors, Mack detail, roll-forward, hindsight, data checks, selections log, judgment impact |
| `output/charts/` | IBNR by month, completion factors, PMPM trend, hindsight |

## Actuarial judgment

Every departure from the mechanical method lives in [`selections.json`](selections.json) with a written rationale, and the report prints it. A selection applies only to closes on or after the month it references, so hindsight re-runs use only what was knowable at each close.

| Selection | Why |
|---|---|
| Exclude paid months June and July 2026 from link-ratio averages | The paid-month diagnostic flags June at 87% of expected payments and July at 128%: a processing backlog and its catch-up, not a change in cost. |
| Restate paid at the June 2026 close for the pended backlog | Paid-to-date on every open month is short by the delayed payments. Paid is grossed up using claims operations' pended-inventory report, so the backlog is reserved for rather than read as lower cost. |
| Factor overrides (none this close) | Supported per category and lag. The live Excel model exposes the same override as a yellow input cell. |

## Methodology

| Step | Approach |
|---|---|
| Link ratios | Completion factor method: straight average of the latest 6 incurred months at each lag, excluding the high and low. Excluded diagonals are skipped and the window reaches further back. Chain ladder: volume-weighted over all history with no judgment applied. Lags 36+ are complete. |
| Completion factors | `CF[k] = 1 / ∏_{j≥k} f[j]`; ultimate = paid ÷ CF[age] |
| Immature months (latest 3) | Bornhuetter-Ferguson on a PMPM expected: `ultimate = paid + (1 − CF) × PMPM_expected × member months` |
| PMPM expected | `log PMPM = a + b·t + month effects`, fitted on the latest 30 credible months. The base is the last 12 months, deseasonalised and trended to the target month. |
| Large claims | Claimants over $250k are removed from inpatient. Every month gets B-F on a pooled large-claim PMPM (latest 24 months aged 6+, trended 9%/yr). Factors are all-history volume-weighted because the data is thin. |
| Range | Mack (1993) standard error on the chain ladder, with a lognormal 75th and 95th percentile |
| Loads | 7.5% margin (provision for adverse deviation) and 2.5% CAE. Both are configurable in `ibnr/config.py`. |
| Roll-forward | Prior IBNR − paid in month = expected remaining. Current IBNR on those months − expected remaining = development. |
| Hindsight | Re-run each of the last 10 month-ends on the data as of that date, with and without judgment, then compare with true (or hindsight) IBNR. |
| Paid-month diagnostic | Actual ÷ expected payments by calendar month on routine claims. Flags backlogs and catch-ups that distort the link ratios on their diagonals. |
| Data reconciliation | The extract ties to the triangles; no payments before incurral; no negative cells; membership is complete and stable; large claims sit within inpatient totals. |

Completion factors and the chain ladder use the same arithmetic (`CF = 1/CDF`). What separates them is **how the factors are selected**. Health practice uses short, recent averages because claims operations change month to month. All-history volume weighting is the classic chain ladder and the basis of Mack's variance.

## Data

The data is **synthetic** (`ibnr/synthetic.py`): about 185k–222k commercial members, January 2023 to September 2026. It's shaped like the files a valuation team pulls:

| File | Grain |
|---|---|
| `data/claims.csv` | incurred month × paid month × service category: paid $ and claim count |
| `data/membership.csv` | member months by month |
| `data/large_claims.csv` | claimant × incurred month × paid month for claimants over $250k (included in `claims.csv`) |
| `data/pended_inventory.csv` | claims operations' excess pended dollars at month-end |
| `data/true_ultimate.csv` | **answer key**: true incurred by month and category, used only for validation |

The generator includes the problems a real book throws at you:

* Category-specific lag patterns.
* Trend and deductible seasonality.
* Poisson/Pareto large claimants that pay slower than routine inpatient.
* Claims paying faster over time.
* A June 2026 processing backlog with July catch-up.

To run on real data, provide the same columns and leave out `true_ultimate.csv`.

### Calibration to public benchmarks

The synthetic book is set to be the right order of magnitude against published figures:

| | Synthetic book | Public reference |
|---|---|---|
| Cost trend | Rolling-12 incurred PMPM trend +6.5%; fitted 5–9% a year by category | PwC *Behind the Numbers 2026* projects 8.5% medical cost trend for the group market ([PwC](https://www.pwc.com/us/en/industries/health-industries/library/behind-the-numbers.html)) |
| Cost level | $559 PMPM YTD 2026, plan-paid medical only (no Rx, after member cost sharing) | The 2025 Milliman Medical Index puts a family of four on an employer plan at $35,119 a year, about $730 PMPM all-in, including Rx and employee cost sharing ([Milliman](https://www.milliman.com/en/insight/2025-milliman-medical-index)) |
| Large claimants | 1.1 per 1,000 members a year over $250k (medical) | A multi-employer study found 0.25% of employees with claims exceeded $250k in medical and Rx claims in a year ([ISPOR 2023](https://www.ispor.org/heor-resources/presentations-database/presentation/intl2023-3668/127185)) |

These are calibration checks for realism, not fitted targets. No public claims data with paid dates exists at the grain needed for lag triangles; CMS's synthetic claims files don't carry a paid date. That's why the model uses synthetic data with a known answer.

## Validation

* **Taylor-Ashe benchmark.** The chain ladder reserve ($18,680,856) and the Mack standard errors (total $2,447,095; latest year $1,363,155) match the published results for the Taylor & Ashe (1983) triangle used by Mack (1993) and R's `ChainLadder`.
* **Excel ties to Python.** CI recalculates the live workbook in LibreOffice. It checks that the totals tie to the Python engine and that an override typed into the workbook gives the same IBNR as the same override in Python.
* **Accuracy against known truth.** The current close lands within 5% of true IBNR, the backlog restatement improves the June close, and the paid-month diagnostic flags the planted backlog.

## Layout

```
ibnr/
  synthetic.py    synthetic claims, membership, large claimants and pended inventory
  triangle.py     data loading (Book), lag triangles, as-of-date slicing
  methods.py      link ratios, factor selection and exclusions, completion factors, chain ladder, Mack
  trend.py        PMPM trend fit, seasonality, rolling-12 / 12-over-12 trend
  valuation.py    per-category valuation, large-claim pool, judgment, roll-forward, hindsight, diagnostics, reconciliation
  report.py       markdown report (with ASOP 43 section), exhibits workbook, charts
  excel_model.py  live-formula Excel model
  site.py         GitHub Pages site (docs/), generated from the same run
  config.py       every assumption, plus loading the selections log
  __main__.py     CLI
selections.json   actuarial selections log with rationale
tests/            unit tests, Taylor-Ashe benchmark, end-to-end checks against the answer key, Excel recalculation
output/           September 2026 report, workbooks and charts
docs/             project site served by GitHub Pages
```
