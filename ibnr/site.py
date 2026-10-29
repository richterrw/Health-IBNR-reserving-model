"""Static project site for GitHub Pages (``docs/``), built from the same run as the report."""

from __future__ import annotations

import html
import shutil
from pathlib import Path

import pandas as pd

from .report import ReportPack, _selections_table

REPO = "https://github.com/richterrw/Health-IBNR-reserving-model"

CSS = """
:root {
  --bg: #f9f9f7; --surface: #ffffff; --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
  --line: #e1e0d9; --accent: #2a78d6; --accent-ink: #1c5cab; --good: #006300; --bad: #b42323;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 980px; margin: 0 auto; padding: 0 16px; }
header { background: var(--surface); border-bottom: 1px solid var(--line); padding: 48px 0 36px; }
.eyebrow { color: var(--accent-ink); font-weight: 600; font-size: 14px; letter-spacing: .02em; margin: 0 0 8px; }
h1 { font-size: clamp(28px, 5vw, 40px); line-height: 1.15; margin: 0 0 12px; }
.lede { color: var(--ink2); font-size: 18px; max-width: 760px; margin: 0 0 24px; }
.buttons { display: flex; flex-wrap: wrap; gap: 10px; }
.btn { display: inline-block; padding: 10px 16px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;
  border: 1px solid var(--line); color: var(--ink); background: var(--surface); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn:hover { border-color: var(--accent); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 32px 0 8px; }
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
.kpi .label { color: var(--ink2); font-size: 13px; margin: 0 0 4px; }
.kpi .value { font-size: 28px; font-weight: 700; margin: 0; line-height: 1.2; }
.kpi .note { color: var(--muted); font-size: 13px; margin: 4px 0 0; }
section { padding: 36px 0 8px; }
h2 { font-size: 24px; margin: 0 0 12px; }
h3 { font-size: 17px; margin: 24px 0 8px; }
p { margin: 0 0 14px; }
.muted { color: var(--ink2); }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; margin: 16px 0; }
.card img { width: 100%; height: auto; display: block; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; background: var(--surface);
  border: 1px solid var(--line); border-radius: 10px; margin: 16px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 10px 12px; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child { text-align: left; }
td:first-child { white-space: normal; min-width: 170px; }
thead th { color: var(--ink2); font-weight: 600; background: var(--bg); }
tbody tr:last-child td { border-bottom: 0; }
tr.strong td { font-weight: 700; }
td.wrap-cell { white-space: normal; text-align: left; min-width: 280px; }
.num { font-variant-numeric: tabular-nums; }
.steps { counter-reset: s; list-style: none; padding: 0; margin: 0; display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.steps li { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px 14px 52px; position: relative; }
.steps li::before { counter-increment: s; content: counter(s); position: absolute; left: 16px; top: 14px; width: 24px; height: 24px;
  border-radius: 50%; background: var(--accent); color: #fff; font-size: 13px; font-weight: 700; display: grid; place-items: center; }
.steps b { display: block; }
ul.clean { padding-left: 20px; margin: 0 0 14px; }
ul.clean li { margin: 0 0 6px; }
.callout { border-left: 4px solid var(--accent); background: var(--surface); padding: 14px 16px; border-radius: 0 10px 10px 0; margin: 16px 0; }
.good { color: var(--good); font-weight: 700; }
.bad { color: var(--bad); font-weight: 700; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; background: var(--line); padding: 1px 5px; border-radius: 4px; }
footer { border-top: 1px solid var(--line); margin-top: 48px; padding: 24px 0 40px; color: var(--ink2); font-size: 14px; }
a { color: var(--accent-ink); }
"""


def _m(x: float) -> str:
    return f"${x / 1e6:,.1f}M"


def _pct(x: float, sign: bool = True) -> str:
    return f"{x:+.1%}" if sign else f"{x:.1%}"


def _table(headers: list[str], rows: list[list[str]], strong_last: bool = False) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = []
    for i, r in enumerate(rows):
        cls = ' class="strong"' if strong_last and i == len(rows) - 1 else ""
        body.append(f"<tr{cls}>" + "".join(f'<td class="num">{c}</td>' if j else f"<td>{c}</td>" for j, c in enumerate(r)) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def write(pack: ReportPack, chart_dir: Path, out_dir: Path) -> Path:
    v, h = pack.valuation, pack.hindsight
    cfg = v.config
    vm = v.valuation_month
    tag = str(vm)
    s = v.summary()
    tot = s.loc["Total"]
    tm = v.total_monthly
    true_ibnr = (pack.truth.reindex(tm.index) - tm["paid"]).sum() if pack.truth is not None else None

    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for png in chart_dir.glob("*.png"):
        shutil.copy(png, assets / png.name)
    (out_dir / ".nojekyll").write_text("")

    report_url = f"{REPO}/blob/main/output/reserve_report_{tag}.md"
    model_url = f"{REPO}/raw/main/output/ibnr_model_{tag}.xlsx"
    exhibits_url = f"{REPO}/raw/main/output/reserve_exhibits_{tag}.xlsx"

    mae = lambda c: h[c].abs().mean()  # noqa: E731
    has_mech = "ibnr_mechanical_error_pct" in h
    if has_mech:
        best = (h["ibnr_selected_error_pct"].abs() - h["ibnr_mechanical_error_pct"].abs()).idxmin()
        best_name = pd.Period(best, "M").strftime("%B %Y")
        mech_err, sel_err = h.loc[best, "ibnr_mechanical_error_pct"], h.loc[best, "ibnr_selected_error_pct"]

    # ---- results by method
    method_rows = []
    defs = [("<b>Selected</b> (CF + PMPM/B-F + large-claim pool + judgment)", tot["ibnr_selected"], "ibnr_selected_error_pct")]
    if pack.mechanical is not None:
        defs.append(("Same, mechanical (no judgment)", pack.mechanical.summary().loc["Total", "ibnr_selected"], "ibnr_mechanical_error_pct"))
    defs += [
        ("Completion factor only", tot["ibnr_completion_factor"], "ibnr_completion_factor_error_pct"),
        ("Chain ladder (all-history volume-weighted)", tot["ibnr_chain_ladder"], "ibnr_chain_ladder_error_pct"),
    ]
    for name, ibnr, col in defs:
        row = [name, _m(ibnr)]
        if true_ibnr is not None:
            row.append(_pct(ibnr / true_ibnr - 1))
        row.append(_pct(mae(col), sign=False) if col in h else "–")
        method_rows.append(row)
    method_headers = ["Method", "IBNR"] + (["vs. true IBNR"] if true_ibnr is not None else []) + [f"Hindsight MAE, {len(h)} closes"]

    cat_rows = [
        [html.escape(idx), _m(r["paid_to_date"]), _m(r["ibnr_selected"]), _m(r["margin"]), _m(r["cae"]), _m(r["total_liability"])]
        for idx, r in s.iterrows()
    ]
    sel_rows = [[html.escape(r["selection"]), f'<span class="muted">{html.escape(r["rationale"])}</span>'] for _, r in _selections_table(v).iterrows()]
    sel_html = (
        _table(["Selection", "Rationale"], sel_rows).replace('<td class="num"><span', '<td class="wrap-cell"><span')
        if sel_rows
        else "<p>No departures from the mechanical method this close.</p>"
    )
    n_checks = len(pack.reconciliation)
    n_pass = int((pack.reconciliation["result"] == "Pass").sum())

    kpis = [
        ("Recommended liability", _m(tot["total_liability"]), f"IBNR + {cfg.margin_pct:.1%} margin + {cfg.cae_pct:.1%} CAE"),
        ("Best-estimate IBNR", _m(tot["ibnr_selected"]), f"{vm.strftime('%B %Y')} close"),
        ("Hindsight error", _pct(mae("ibnr_selected_error_pct"), sign=False), f"mean absolute, vs {_pct(mae('ibnr_chain_ladder_error_pct'), sign=False)} for the chain ladder"),
    ]
    if has_mech:
        kpis.append(("Backlog close, with judgment", _pct(sel_err), f"{best_name}; {_pct(mech_err)} without"))
    kpi_html = "".join(f'<div class="kpi"><p class="label">{a}</p><p class="value">{b}</p><p class="note">{c}</p></div>' for a, b, c in kpis)

    judgment = ""
    if has_mech:
        judgment = f"""
<div class="callout">At the <b>{best_name}</b> close, claims operations were in the middle of a processing backlog.
The mechanical method missed true IBNR by <span class="bad">{_pct(mech_err)}</span>. Restating paid claims for the pended inventory
and excluding the distorted payment months brought it to <span class="good">{_pct(sel_err)}</span>, in line with an ordinary month.</div>"""

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Health IBNR Reserving Model</title>
<meta name="description" content="Monthly health IBNR valuation: completion factor and chain ladder reserves, PMPM trend, large-claim pool, actuarial judgment, reserve report and live Excel model.">
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="wrap">
    <p class="eyebrow">Health actuarial · Reserving</p>
    <h1>Health IBNR Reserving Model</h1>
    <p class="lede">A monthly medical IBNR valuation, built the way a health plan valuation team runs its month-end close:
    lag triangles, completion factors, chain ladder and Mack ranges, PMPM trend, a large-claim pool, and logged actuarial judgment.
    The output is a reserve report with ASOP 43 disclosures and a live-formula Excel model.</p>
    <div class="buttons">
      <a class="btn primary" href="{report_url}">Read the {vm.strftime('%B %Y')} reserve report</a>
      <a class="btn" href="{model_url}">Download the Excel model</a>
      <a class="btn" href="{REPO}">View the code</a>
    </div>
    <div class="kpis">{kpi_html}</div>
  </div>
</header>
<main class="wrap">

<section>
  <h2>What it does</h2>
  <ol class="steps">
    <li><b>Lag triangles</b>Paid claims by incurred month × months of development, by service category.</li>
    <li><b>Completion factors</b>Recent 6-month averages, excluding the high and low; ultimate = paid ÷ completion.</li>
    <li><b>PMPM / Bornhuetter-Ferguson</b>For the newest {cfg.pmpm_lags} months, where paid claims aren't credible yet.</li>
    <li><b>Large-claim pool</b>Claimants over ${cfg.large_claim_threshold / 1000:,.0f}k are reserved separately on a trended pooled PMPM.</li>
    <li><b>Actuarial judgment</b>Excluded diagonals, backlog restatement and factor overrides, each logged with a rationale.</li>
    <li><b>Monthly report</b>Roll-forward, hindsight test, paid-month diagnostic, data checks and ASOP 43 disclosures.</li>
  </ol>
</section>

<section>
  <h2>Results at the {vm.strftime('%B %Y')} valuation</h2>
  <p class="muted">The data is synthetic, so the true answer is known. Every method is scored against it at the current close and at {len(h)} prior month-ends.</p>
  {_table(method_headers, method_rows)}
  <p>The chain ladder over-reserves by about {mae('ibnr_chain_ladder_error_pct'):.0%} because claims now pay faster than they used to.
  All-history factors overstate the remaining runout; recent-average completion factors track the change.</p>
  <div class="card"><img src="assets/ibnr_by_month.png" alt="IBNR by incurred month for each method against true IBNR, last 12 incurred months" loading="lazy"></div>
</section>

<section>
  <h2>Actuarial judgment</h2>
  <p>Every departure from the formula lives in <code>selections.json</code> with a written reason, and the report prints it.
  A selection only applies to closes on or after the month it references, so the hindsight test uses only what was knowable at each close.</p>
  {judgment}
  <div class="card"><img src="assets/hindsight.png" alt="Hindsight test: IBNR error at each prior close for each method" loading="lazy"></div>
  {sel_html}
</section>

<section>
  <h2>Reserve by category</h2>
  {_table(["Category", "Paid to date", "IBNR", "Margin", "CAE", "Total liability"], cat_rows, strong_last=True)}
  <div class="card"><img src="assets/completion_factors.png" alt="Selected completion factors by lag for each category" loading="lazy"></div>
</section>

<section>
  <h2>PMPM trend</h2>
  <p>A log-linear regression with calendar-month seasonality sets the expected cost for immature months.
  Deductibles make Q1 run low and Q4 high. The book's cost level, trend and large-claim frequency are checked against the Milliman Medical Index,
  PwC's medical cost trend survey, and published high-cost-claimant studies.</p>
  <div class="card"><img src="assets/pmpm_trend.png" alt="Monthly and rolling 12-month incurred PMPM" loading="lazy"></div>
</section>

<section>
  <h2>Validation</h2>
  <ul class="clean">
    <li><b>Published benchmark.</b> The chain ladder and Mack standard errors reproduce the Taylor-Ashe (1983) results used by Mack (1993) and R's <code>ChainLadder</code>.</li>
    <li><b>Excel ties to Python.</b> The live workbook is recalculated in CI and ties to the Python engine; an override typed into the workbook matches the same override in Python.</li>
    <li><b>Known truth.</b> Every prior close is re-run on the data as it stood then and scored against true IBNR.</li>
    <li><b>Data checks.</b> {n_pass} of {n_checks} reconciliation checks pass: the extract ties to the triangles, dates are valid, membership is complete, large claims sit within inpatient.</li>
  </ul>
</section>

<section>
  <h2>Outputs</h2>
  <ul class="clean">
    <li><a href="{report_url}">Reserve report</a>: summary, methodology, selections, trend, roll-forward, hindsight, diagnostics, ASOP 43 disclosures.</li>
    <li><a href="{model_url}">Live Excel model</a>: every factor and reserve is a formula, with yellow override cells.</li>
    <li><a href="{exhibits_url}">Exhibits workbook</a>: triangles, link ratios, Mack detail, roll-forward, hindsight, data checks.</li>
    <li><a href="{REPO}">Source code and tests</a>: Python, run with <code>python -m ibnr</code>.</li>
  </ul>
</section>

</main>
<footer>
  <div class="wrap">
    Built by <a href="https://github.com/richterrw">richterrw</a>. Synthetic data; illustrative only, not a Statement of Actuarial Opinion.
    This page is generated by <code>python -m ibnr</code> from the same run as the report.
  </div>
</footer>
</body>
</html>
"""
    path = out_dir / "index.html"
    path.write_text(page)
    return path
