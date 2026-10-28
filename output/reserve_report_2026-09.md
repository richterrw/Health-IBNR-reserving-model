# Medical IBNR Reserve Report: September 2026 Valuation

*Paid claims through 09/30/2026; incurred months 2023-01 to 2026-09. Commercial medical (inpatient, outpatient, professional). Synthetic data.*

## 1. Summary

* **Recommended IBNR liability: $230.6M**. That is $209.2M best-estimate IBNR, plus a 7.5% margin ($15.7M) and 2.5% claim adjustment expense ($5.6M).
* The best estimate is 1.72 months of current incurred claims. For incurred months open at the prior close, IBNR developed **+2.0M** (+1.0% of prior IBNR) in September.
* Year-to-date incurred PMPM is **$549.09**, +7.4% over the same months of 2025. Rolling-12 trend is +7.9%.
* Chain ladder (all-history volume-weighted) is +12.8% above the selected IBNR. Recent link ratios are lower than older ones because claims are paying faster, so all-history factors overstate the remaining runout. The Mack 75th–95th percentile range on the chain ladder is $236.6M to $242.4M.

### Reserve summary by category

| Category | Paid to date | IBNR: completion factor | IBNR: chain ladder | **IBNR: selected** | Margin | CAE | **Total liability** |
|---|---|---|---|---|---|---|---|
| Inpatient | $1,278.9M | $97.0M | $103.2M | $90.9M | $6.8M | $2.4M | $100.1M |
| Outpatient | $1,488.8M | $75.1M | $80.3M | $71.7M | $5.4M | $1.9M | $79.0M |
| Professional | $1,656.6M | $47.5M | $52.4M | $46.6M | $3.5M | $1.3M | $51.4M |
| Total | $4,424.3M | $219.6M | $236.0M | $209.2M | $15.7M | $5.6M | $230.6M |

![IBNR by incurred month](charts/ibnr_by_month.png)

## 2. Methodology and selections

* **Completion factor method** (months aged 3+). Link ratios are the straight average of the latest 6 incurred months at each lag, excluding the high and low. Ultimate = paid ÷ completion factor. Lags of 36+ are treated as complete.
* **PMPM / Bornhuetter-Ferguson** (the latest 3 incurred months). Completion is too low for paid ÷ CF to be credible. The expected cost is the trended, seasonally adjusted PMPM times member months. Ultimate = paid + (1 − CF) × expected, so emerging paid claims carry weight in proportion to completion.
* **Chain ladder.** Volume-weighted link ratios over all history. It serves as a benchmark and as the basis for the Mack (1993) standard error.
* **PMPM trend.** A log-linear regression with calendar-month seasonality, fitted on the latest 30 credible months. The base period is the latest 12 credible months, deseasonalised and centred at their midpoint.

### Completion factors by lag

| Lag | Inpatient | Outpatient | Professional |
|---|---|---|---|
| 0 | 14.3% | 19.8% | 31.9% |
| 1 | 41.4% | 56.4% | 74.4% |
| 2 | 60.9% | 78.4% | 92.1% |
| 3 | 74.5% | 89.3% | 97.7% |
| 4 | 83.8% | 95.0% | 99.3% |
| 5 | 89.4% | 97.7% | 99.8% |
| 6 | 93.3% | 99.0% | 99.9% |
| 7 | 95.7% | 99.5% | 100.0% |
| 8 | 97.1% | 99.8% | 100.0% |

![Completion factors](charts/completion_factors.png)

### Latest months by incurred month (all categories)

| Incurred | Method | Member months | Paid | Completion | PMPM expected | Selected ultimate | Selected IBNR | PMPM | True ultimate* |
|---|---|---|---|---|---|---|---|---|---|
| 2026-04 | CF | 219,206 | $117.6M | 96.0% | $122.5M | $122.5M | $4.9M | $558.80 | $122.1M |
| 2026-05 | CF | 219,383 | $117.9M | 93.1% | $123.5M | $126.6M | $8.7M | $576.86 | $126.4M |
| 2026-06 | CF | 219,891 | $107.5M | 87.7% | $122.0M | $122.6M | $15.1M | $557.50 | $122.8M |
| 2026-07 | PMPM/B-F | 220,771 | $92.2M | 78.0% | $119.7M | $118.2M | $26.0M | $535.43 | $117.8M |
| 2026-08 | PMPM/B-F | 221,871 | $75.2M | 59.7% | $122.9M | $126.0M | $50.8M | $567.79 | $127.0M |
| 2026-09 | PMPM/B-F | 222,253 | $29.8M | 23.6% | $124.5M | $126.2M | $96.4M | $567.77 | $124.5M |

\* True ultimate comes from the synthetic answer key and is shown for validation only. A real valuation never has it.

## 3. PMPM trend

![PMPM trend](charts/pmpm_trend.png)

| Assumption | Inpatient | Outpatient | Professional |
|---|---|---|---|
| Fitted annual trend | +6.0% | +9.2% | +5.1% |
| Selected annual trend | +6.0% | +9.2% | +5.1% |
| R² | 0.81 | 0.95 | 0.93 |
| Base PMPM (deseasonalised) | $163.02 @ 2026-01 | $188.16 @ 2026-01 | $196.97 @ 2026-01 |
| Q4 / Q1 seasonal ratio | 1.16 | 1.10 | 1.08 |

Calendar-year incurred PMPM (partial years are not comparable to full years because of seasonality; use the YTD comparison above):

| Year | Months | Member months | Incurred | PMPM | Change |
|---|---|---|---|---|---|
| 2023 | 12 | 2,239,445 | $1,038.0M | $463.53 |  |
| 2024 | 12 | 2,377,723 | $1,179.9M | $496.24 | +7.1% |
| 2025 | 12 | 2,501,861 | $1,327.8M | $530.74 | +7.0% |
| 2026 | 9 | 1,981,011 | $1,087.8M | $549.09 | +3.5% |

## 4. Reserve roll-forward

From the August close to the September close.

| Category | Prior IBNR | Paid in month | Expected remaining | Current IBNR (prior months) | Development | % of prior | New month IBNR | Current IBNR |
|---|---|---|---|---|---|---|---|---|
| Inpatient | $89.3M | $32.7M | $56.6M | $59.9M | +3.3M | +3.7% | $30.9M | $90.9M |
| Outpatient | $70.9M | $33.4M | $37.6M | $36.6M | -0.9M | -1.3% | $35.1M | $71.7M |
| Professional | $46.6M | $30.0M | $16.6M | $16.2M | -0.3M | -0.7% | $30.4M | $46.6M |
| Total | $206.9M | $96.1M | $110.8M | $112.8M | +2.0M | +1.0% | $96.4M | $209.2M |

Development = current IBNR on prior months − (prior IBNR − paid in month). Positive is adverse.

## 5. Hindsight test

Each prior valuation is re-run on the data as it stood at that month-end and compared with what is known now. Because the data is synthetic, the comparison is against **true** IBNR from the answer key.

![Hindsight test](charts/hindsight.png)

| Valuation | Runout (mo) | **IBNR: selected** | IBNR: completion factor | IBNR: chain ladder | True IBNR* | Selected error | CF error | CL error |
|---|---|---|---|---|---|---|---|---|
| 2025-09 | 12 | $191.3M | $193.8M | $206.2M | $186.0M | +2.9% | +4.2% | +10.9% |
| 2025-10 | 11 | $197.2M | $207.9M | $219.7M | $196.0M | +0.6% | +6.1% | +12.1% |
| 2025-11 | 10 | $196.1M | $208.3M | $220.6M | $198.3M | -1.1% | +5.0% | +11.2% |
| 2025-12 | 9 | $207.8M | $218.8M | $230.9M | $208.3M | -0.2% | +5.1% | +10.9% |
| 2026-01 | 8 | $208.9M | $208.4M | $221.2M | $196.0M | +6.6% | +6.3% | +12.9% |
| 2026-02 | 7 | $202.7M | $203.6M | $219.4M | $195.5M | +3.7% | +4.1% | +12.2% |
| 2026-03 | 6 | $206.4M | $207.1M | $225.4M | $199.3M | +3.5% | +3.9% | +13.1% |
| 2026-04 | 5 | $203.6M | $197.2M | $216.6M | $204.2M | -0.3% | -3.5% | +6.1% |
| 2026-05 | 4 | $206.7M | $209.7M | $229.1M | $208.5M | -0.9% | +0.6% | +9.9% |
| 2026-06 | 3 | $203.9M | $189.1M | $210.8M | $221.2M | -7.8% | -14.5% | -4.7% |

Selected-method error averaged +0.7% (mean absolute 2.8%). Completion factor only averaged +1.7%; chain ladder averaged +9.5%.

## 6. Paid-month diagnostic

Actual payments in each calendar month on incurred months already open, compared with the payments the selected link ratios expected (lags 1 to 12). Months more than 5% off expected are flagged.

| Paid month | Actual paid | Expected paid | Actual / expected | Flag |
|---|---|---|---|---|
| 2025-10 | $85.0M | $84.2M | 1.009 |  |
| 2025-11 | $88.3M | $90.0M | 0.981 |  |
| 2025-12 | $91.7M | $90.2M | 1.017 |  |
| 2026-01 | $94.9M | $94.9M | 1.000 |  |
| 2026-02 | $88.7M | $91.7M | 0.968 |  |
| 2026-03 | $89.1M | $91.0M | 0.979 |  |
| 2026-04 | $90.8M | $94.4M | 0.962 |  |
| 2026-05 | $92.8M | $90.9M | 1.021 |  |
| 2026-06 | $85.2M | $96.2M | 0.885 | ⚠ |
| 2026-07 | $107.7M | $88.7M | 1.214 | ⚠ |
| 2026-08 | $93.4M | $92.7M | 1.008 |  |
| 2026-09 | $96.0M | $96.6M | 0.993 |  |

## 7. Items for review

* **Paid-month anomaly: Jun 2026 (89% of expected), Jul 2026 (121% of expected).** A low month followed by a high one is a processing backlog and its catch-up, not a change in incurred cost. Link ratios on those diagonals stay in the 6-month averaging window until they roll off. Consider excluding them from the averages, or covering them through the margin.
* **Hindsight.** The largest selected-method miss was the June 2026 valuation (-7.8%). Check whether that close fell inside a payment anomaly flagged above.
* **Inpatient shock claims.** Large claimants drive inpatient volatility. The hi/lo exclusion limits their effect on factors, but immature inpatient months still depend on the PMPM expected value.
* **Margin.** IBNR plus margin and CAE ($230.6M) sits below the Mack chain ladder 75th percentile ($236.6M). Confirm the margin against the plan's historical IBNR runout before booking.

Supporting exhibits (triangles, link ratios, factors, Mack detail and assumptions) are in the Excel workbook.
