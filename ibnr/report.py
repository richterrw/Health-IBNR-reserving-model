"""Monthly reserve report: Excel workbook, markdown memo and charts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter  # noqa: E402

from . import trend as trend_mod  # noqa: E402
from .valuation import Valuation  # noqa: E402

DIAG_TOL = 0.05  # paid-month actual/expected tolerance before flagging

# Chart styling: reference data-viz palette, recessive chrome.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _style(ax: plt.Axes, title: str, subtitle: str | None = None) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=22 if subtitle else 10, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK2)


def _millions(x, _):
    return f"${x / 1e6:,.0f}M"


def _legend(ax: plt.Axes) -> None:
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=4, handlelength=1.6)


def chart_ibnr_by_month(v: Valuation, truth: pd.Series | None, path: Path) -> None:
    tm = v.total_monthly.tail(12)
    x = np.arange(len(tm))
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    ax.plot(x, tm["selected_ibnr"], color=SERIES[0], lw=2, marker="o", ms=4, label="Selected (CF + PMPM/B-F)")
    ax.plot(x, tm["cf_ibnr"], color=SERIES[1], lw=2, marker="o", ms=4, label="Completion factor only")
    ax.plot(x, tm["cl_ibnr"], color=SERIES[2], lw=2, marker="o", ms=4, label="Chain ladder (all-history VWA)")
    if truth is not None:
        ax.plot(x, truth.reindex(tm.index) - tm["paid"], color=INK2, lw=1.2, ls="--", label="True IBNR (synthetic answer key)")
    ax.set_xticks(x, [m.strftime("%b %y") for m in tm.index])
    ax.yaxis.set_major_formatter(FuncFormatter(_millions))
    _style(ax, "IBNR by incurred month", f"Valuation {v.valuation_month.strftime('%B %Y')}, last 12 incurred months, all categories")
    _legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_completion(v: Valuation, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    lags = np.arange(13)
    for i, (cat, r) in enumerate(v.categories.items()):
        ax.plot(lags, r.completion["cf_completion"].reindex(lags), color=SERIES[i], lw=2, marker="o", ms=4, label=v.label(cat))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_ylim(0, 1.05)
    ax.set_xticks(lags)
    ax.set_xlabel("Months of development (0 = incurred month)", color=MUTED, fontsize=9)
    _style(ax, "Selected completion factors", "Share of ultimate paid by lag. Routine: 6-month avg ex hi/lo. Large claims: all-history volume-weighted")
    _legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_pmpm(v: Valuation, path: Path) -> None:
    tm = v.total_monthly
    rep = trend_mod.report(tm["selected_ultimate"], v.members)
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    x = tm.index.to_timestamp()
    imm = (tm["age"] < v.config.pmpm_lags).to_numpy()
    ax.plot(x, rep["pmpm"], color=SERIES[0], lw=1.2, alpha=0.55, label="Monthly incurred PMPM")
    ax.plot(x[imm], rep["pmpm"][imm], color=SERIES[0], lw=0, marker="o", ms=5, mfc=SURFACE, mew=1.5, label="Immature month (PMPM/B-F)")
    ax.plot(x, rep["rolling12_pmpm"], color=SERIES[1], lw=2, label="Rolling 12-month PMPM")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:,.0f}"))
    last = rep["trend_12_over_12"].dropna().iloc[-1]
    _style(ax, "Incurred PMPM, all medical", f"Rolling-12 trend {last:+.1%} (12-over-12); Q4 peaks are deductible seasonality")
    _legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_hindsight(h: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    x = np.arange(len(h))
    basis = "true_ibnr" if "true_ibnr" in h else "hindsight_ibnr"
    # Mechanical is drawn first and dashed so the selected line stays visible where they coincide.
    if "ibnr_mechanical" in h:
        ax.plot(x, h["ibnr_mechanical"] / h[basis] - 1, color=SERIES[3], lw=2, ls=(0, (4, 2)), marker="o", ms=4, label="Selected, mechanical")
    cols = [("ibnr_selected", "Selected (with judgment)"), ("ibnr_completion_factor", "Completion factor only"), ("ibnr_chain_ladder", "Chain ladder")]
    for i, (c, label) in enumerate(cols):
        ax.plot(x, h[c] / h[basis] - 1, color=SERIES[i], lw=2, marker="o", ms=4, label=label, zorder=3 if i == 0 else 2)
    ax.axhline(0, color=AXIS, lw=1)
    ax.yaxis.set_major_locator(MultipleLocator(0.04))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xticks(x, [pd.Period(m, "M").strftime("%b %y") for m in h.index])
    ref = "true IBNR" if basis == "true_ibnr" else "hindsight IBNR"
    _style(ax, "Hindsight test: IBNR error at prior valuations", f"Estimated IBNR / {ref} - 1. Above zero = over-reserved")
    _legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------------- Excel

def _autosize(ws) -> None:
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 40)


def _fmt(ws, money_cols: list[str], pct_cols: list[str], factor_cols: list[str]) -> None:
    header = {c.value: c.column_letter for c in ws[1]}
    for name, fmt in [(m, "#,##0") for m in money_cols] + [(p, "0.0%") for p in pct_cols] + [(f, "0.0000") for f in factor_cols]:
        if name in header:
            for cell in ws[header[name]][1:]:
                cell.number_format = fmt


def write_excel(pack: "ReportPack", path: Path) -> None:
    from openpyxl.styles import Font, PatternFill

    def strs(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if isinstance(df.index, pd.PeriodIndex):
            df.index = df.index.astype(str)
        return df

    v, rf, h, diag = pack.valuation, pack.rollforward, pack.hindsight, pack.diagnostic
    summary = v.summary()
    trend_rows = pd.DataFrame(
        {
            c: {
                "fitted_annual_trend": r.trend.fitted_annual_trend,
                "selected_annual_trend": r.trend.annual_trend,
                "r_squared": r.trend.r_squared,
                "base_pmpm_deseasonalised": r.trend.base_pmpm,
                "base_midpoint": str(r.trend.base_midpoint),
                "fit_from": str(r.trend.fit_months[0]),
                "fit_to": str(r.trend.fit_months[-1]),
            }
            for c, r in v.categories.items()
            if r.trend is not None
        }
    ).T
    seasonal = pd.DataFrame({c: r.trend.seasonal_index for c, r in v.categories.items() if r.trend is not None})
    seasonal.index.name = "calendar_month"
    pmpm = trend_mod.report(v.total_monthly["selected_ultimate"], v.members)
    assumptions = pd.Series(vars(v.config), name="value").astype(str).to_frame()

    money = ["paid_to_date", "ibnr_completion_factor", "ibnr_chain_ladder", "ibnr_selected", "margin", "cae", "total_liability",
             "chain_ladder_se", "chain_ladder_p75", "chain_ladder_p95", "paid", "cf_ultimate", "expected_claims", "bf_ultimate",
             "cl_ultimate", "selected_ultimate", "cf_ibnr", "cl_ibnr", "selected_ibnr", "member_months", "incurred",
             "prior_ibnr", "paid_on_prior_months", "expected_remaining", "current_ibnr_prior_months", "development",
             "new_month_ibnr", "current_ibnr", "hindsight_ibnr", "true_ibnr", "ultimate", "reserve", "se",
             "actual_paid", "expected_paid", "ibnr_mechanical", "ibnr_with_judgment", "impact"]
    pct = ["development_pct_of_prior", "trend_12_over_12", "pmpm_yoy", "fitted_annual_trend", "selected_annual_trend",
           "ibnr_completion_factor_error_pct", "ibnr_chain_ladder_error_pct", "ibnr_selected_error_pct", "cv",
           "ibnr_mechanical_error_pct", "impact_pct"]
    factors = ["actual_to_expected", "completion_factor", "cf_link_ratio", "cf_completion", "cl_link_ratio", "cl_completion", "r_squared"]

    sheets: list[tuple[str, pd.DataFrame]] = [
        ("Summary", summary),
        ("Rollforward", rf),
        ("By Month", strs(v.total_monthly)),
        ("PMPM Trend", strs(pmpm)),
        ("Trend Fit", trend_rows),
        ("Seasonality", seasonal),
        ("Hindsight", h),
        ("Paid Month Diag", diag),
        ("Data Checks", pack.reconciliation),
        ("Selections", _selections_table(v)),
    ]
    if pack.mechanical is not None:
        sheets.insert(1, ("Judgment Impact", _impact_table(v, pack.mechanical)))
    for cat, r in v.categories.items():
        ab = {"Inpatient": "IP", "Outpatient": "OP", "Professional": "Prof", "Large claims": "LC"}.get(cat, cat[:8])
        sheets.append((f"{ab} Factors", r.completion))
        sheets.append((f"{ab} Triangle", strs(r.triangle)))
        sheets.append((f"{ab} Link Ratios", strs(r.link_ratios)))
        sheets.append((f"{ab} Monthly", strs(r.monthly)))
        mk = strs(r.mack.copy())
        mk["cv"] = mk["se"] / mk["reserve"].where(mk["reserve"] > 0)
        sheets.append((f"{ab} Mack", mk))
    sheets.append(("Assumptions", assumptions))

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets:
            df.to_excel(xw, sheet_name=name)
            ws = xw.sheets[name]
            ws.freeze_panes = "B2"
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="256ABF")
            if "Triangle" in name:
                for row in ws.iter_rows(min_row=2, min_col=2):
                    for c in row:
                        c.number_format = "#,##0"
            elif "Link Ratios" in name:
                for row in ws.iter_rows(min_row=2, min_col=2):
                    for c in row:
                        c.number_format = "0.0000"
            else:
                _fmt(ws, money, pct, factors)
                if name in ("PMPM Trend", "By Month"):
                    header = {c.value: c.column_letter for c in ws[1]}
                    for col in ("pmpm", "rolling12_pmpm", "selected_pmpm"):
                        if col in header:
                            for cell in ws[header[col]][1:]:
                                cell.number_format = "$#,##0.00"
            _autosize(ws)


# --------------------------------------------------------------------------- Markdown

def _m(x: float) -> str:
    return f"${x / 1e6:,.1f}M"


LABELS = {
    "service_category": "Category",
    "paid_to_date": "Paid to date",
    "ibnr_completion_factor": "IBNR: completion factor",
    "ibnr_chain_ladder": "IBNR: chain ladder",
    "ibnr_selected": "**IBNR: selected**",
    "margin": "Margin",
    "cae": "CAE",
    "total_liability": "**Total liability**",
    "method": "Method",
    "member_months": "Member months",
    "paid": "Paid",
    "completion_factor": "Completion",
    "expected_claims": "PMPM expected",
    "selected_ultimate": "Selected ultimate",
    "selected_ibnr": "Selected IBNR",
    "selected_pmpm": "PMPM",
    "true_ultimate": "True ultimate*",
    "months": "Months",
    "incurred": "Incurred",
    "pmpm": "PMPM",
    "pmpm_change": "Change",
    "prior_ibnr": "Prior IBNR",
    "paid_on_prior_months": "Paid in month",
    "expected_remaining": "Expected remaining",
    "current_ibnr_prior_months": "Current IBNR (prior months)",
    "development": "Development",
    "development_pct_of_prior": "% of prior",
    "new_month_ibnr": "New month IBNR",
    "current_ibnr": "Current IBNR",
    "months_of_runout": "Runout (mo)",
    "true_ibnr": "True IBNR*",
    "hindsight_ibnr": "Hindsight IBNR",
    "ibnr_selected_error_pct": "Selected error",
    "ibnr_completion_factor_error_pct": "CF error",
    "ibnr_chain_ladder_error_pct": "CL error",
    "actual_paid": "Actual paid",
    "expected_paid": "Expected paid",
    "actual_to_expected": "Actual / expected",
    "flag": "Flag",
    "ibnr_mechanical": "IBNR: mechanical",
    "ibnr_mechanical_error_pct": "Mechanical error",
    "ibnr_with_judgment": "IBNR: with judgment",
    "impact": "Impact",
    "impact_pct": "Impact %",
    "selection": "Selection",
    "rationale": "Rationale",
    "result": "Result",
    "detail": "Detail",
    "check": "Check",
    "paid_month": "Paid month",
}


def _table(df: pd.DataFrame, fmts: dict[str, callable]) -> str:
    cols = list(fmts)
    head = "| " + " | ".join([LABELS.get(df.index.name, df.index.name or "")] + [LABELS.get(c, c) for c in cols]) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    lines = [head, sep]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [fmts[c](row[c]) for c in cols]) + " |")
    return "\n".join(lines)


@dataclass
class ReportPack:
    """Everything the report needs for one close."""

    valuation: Valuation
    rollforward: pd.DataFrame
    hindsight: pd.DataFrame
    diagnostic: pd.DataFrame
    reconciliation: pd.DataFrame
    mechanical: Valuation | None = None  # same close with judgmental selections removed
    truth: pd.Series | None = None  # synthetic answer key: true ultimate by incurred month


def _selections_table(v: Valuation) -> pd.DataFrame:
    rows = []
    for key, why in v.config.selection_notes.items():
        kind, _, what = key.partition(":")
        label = {
            "exclude_paid_months": f"Exclude paid month {what} from link-ratio averages",
            "restate_paid_months": f"Restate paid for pended backlog at the {what} close",
            "factor_override": f"Override {what}",
        }.get(kind, key)
        rows.append({"selection": label, "rationale": why})
    df = pd.DataFrame(rows, columns=["selection", "rationale"])
    df.index = range(1, len(df) + 1)
    df.index.name = "#"
    return df


def _impact_table(v: Valuation, mech: Valuation) -> pd.DataFrame:
    a = mech.summary()["ibnr_selected"]
    b = v.summary()["ibnr_selected"]
    df = pd.DataFrame({"ibnr_mechanical": a, "ibnr_with_judgment": b})
    df["impact"] = df["ibnr_with_judgment"] - df["ibnr_mechanical"]
    df["impact_pct"] = df["impact"] / df["ibnr_mechanical"]
    return df


def write_markdown(pack: ReportPack, path: Path, chart_dir: str) -> None:
    v, rf, h, diag, truth = pack.valuation, pack.rollforward, pack.hindsight, pack.diagnostic, pack.truth
    s = v.summary()
    tot = s.loc["Total"]
    vm = v.valuation_month
    tm = v.total_monthly
    cfg = v.config
    pmpm = trend_mod.report(tm["selected_ultimate"], v.members)
    cy = trend_mod.calendar_year(tm["selected_ultimate"], v.members)
    # Year-to-date comparison on the same calendar months, to avoid seasonality bias.
    ytd_months = [m for m in tm.index if m.year == vm.year]
    py_months = [m - 12 for m in ytd_months]
    ytd = tm.loc[ytd_months, "selected_ultimate"].sum() / v.members.reindex(ytd_months).sum()
    pytd = tm.loc[py_months, "selected_ultimate"].sum() / v.members.reindex(py_months).sum()
    r = rf.loc["Total"]
    months_of_claims = tot["ibnr_selected"] / (tm["selected_ultimate"].tail(12).sum() / 12)
    pct = lambda x: f"{x:.1%}"  # noqa: E731
    sgn = lambda x: f"{x:+.1%}"  # noqa: E731

    lines = [
        f"# Medical IBNR Reserve Report: {vm.strftime('%B %Y')} Valuation",
        "",
        f"*Paid claims through {vm.end_time.strftime('%m/%d/%Y')}; incurred months {tm.index[0]} to {vm}. "
        "Commercial medical (inpatient, outpatient, professional). Synthetic data; illustrative only.*",
        "",
        "## 1. Summary",
        "",
        f"* **Recommended IBNR liability: {_m(tot['total_liability'])}**. That is {_m(tot['ibnr_selected'])} best-estimate IBNR, "
        f"plus a {cfg.margin_pct:.1%} margin ({_m(tot['margin'])}) and {cfg.cae_pct:.1%} claim adjustment expense ({_m(tot['cae'])}).",
        f"* The best estimate is {months_of_claims:.2f} months of current incurred claims. "
        f"For incurred months open at the prior close, IBNR developed **{r['development'] / 1e6:+.1f}M** ({sgn(r['development_pct_of_prior'])} of prior IBNR) "
        f"in {vm.strftime('%B')}.",
        f"* Year-to-date incurred PMPM is **${ytd:,.2f}**, {sgn(ytd / pytd - 1)} over the same months of {vm.year - 1}. "
        f"Rolling-12 trend is {sgn(pmpm['trend_12_over_12'].iloc[-1])}.",
    ]
    if v.has_large:
        lt = s.loc[v.label("Large claims")]
        lines.append(
            f"* Large claimants over ${cfg.large_claim_threshold / 1000:,.0f}k are reserved separately: {_m(lt['ibnr_selected'])} of IBNR "
            f"({lt['ibnr_selected'] / tot['ibnr_selected']:.0%} of the total) on a pooled, trended large-claim PMPM."
        )
    if pack.mechanical is not None:
        mt = pack.mechanical.summary().loc["Total", "ibnr_selected"]
        lines.append(
            f"* Actuarial selections (section 3) change IBNR by {(tot['ibnr_selected'] - mt) / 1e6:+.1f}M from the mechanical result of {_m(mt)}."
        )
    lines += [
        f"* The chain ladder (all-history volume-weighted) is {sgn(tot['ibnr_chain_ladder'] / tot['ibnr_selected'] - 1)} above the selected IBNR. "
        "Recent link ratios are lower than older ones because claims are paying faster, so all-history factors overstate the remaining runout. "
        f"The Mack 75th–95th percentile range on the chain ladder is {_m(tot['chain_ladder_p75'])} to {_m(tot['chain_ladder_p95'])}.",
        "",
        "### Reserve summary by category",
        "",
        _table(s, {k: _m for k in ["paid_to_date", "ibnr_completion_factor", "ibnr_chain_ladder", "ibnr_selected", "margin", "cae", "total_liability"]}),
        "",
        f"![IBNR by incurred month]({chart_dir}/ibnr_by_month.png)",
        "",
        "## 2. Methodology",
        "",
        f"* **Completion factor method** (months aged {cfg.pmpm_lags}+). Link ratios are the straight average of the latest "
        f"{cfg.cf_avg_months} incurred months at each lag{', excluding the high and low' if cfg.cf_exclude_hi_lo else ''}. "
        f"Ultimate = paid ÷ completion factor. Lags of {cfg.max_lag}+ are treated as complete.",
        f"* **PMPM / Bornhuetter-Ferguson** (the latest {cfg.pmpm_lags} incurred months). Completion is too low for paid ÷ CF to be credible. "
        "The expected cost is the trended, seasonally adjusted PMPM times member months. "
        "Ultimate = paid + (1 − CF) × expected, so emerging paid claims carry weight in proportion to completion.",
    ]
    if v.has_large:
        lines.append(
            f"* **Large claims** (claimants over ${cfg.large_claim_threshold / 1000:,.0f}k). They are removed from the inpatient triangle and "
            "reserved by B-F for every incurred month, on a pooled large-claim PMPM. The pool is the latest "
            f"{cfg.large_claim_experience_months} months aged {cfg.large_claim_credible_lag}+, trended at {cfg.large_claim_trend:.0%} a year. "
            "Large-claim link ratios are volume-weighted over all history because the data is thin. "
            "One $2M claimant can move a month's paid ÷ CF estimate by more than the routine IBNR on it."
        )
    lines += [
        "* **Chain ladder.** Volume-weighted link ratios over all history with no judgment applied. It serves as a benchmark and as the basis for the Mack (1993) standard error.",
        f"* **PMPM trend.** A log-linear regression with calendar-month seasonality, fitted on the latest {cfg.trend_fit_months} credible months. "
        f"The base period is the latest {cfg.base_period_months} credible months, deseasonalised and centred at their midpoint.",
        "",
        "### Completion factors by lag",
        "",
    ]
    comp = pd.DataFrame({v.label(c): r_.completion["cf_completion"] for c, r_ in v.categories.items()}).head(9)
    comp.index.name = "Lag"
    lines += [_table(comp, {c: pct for c in comp.columns}), "", f"![Completion factors]({chart_dir}/completion_factors.png)", ""]

    lines += ["### Latest months by incurred month (all categories)", ""]
    recent = tm.tail(6).copy()
    recent.index = recent.index.astype(str)
    recent.index.name = "Incurred"
    recent["method"] = np.where(recent["age"] >= cfg.pmpm_lags, "CF", "PMPM/B-F")
    fm = {
        "method": str,
        "member_months": lambda x: f"{x:,.0f}",
        "paid": _m,
        "completion_factor": pct,
        "expected_claims": _m,
        "selected_ultimate": _m,
        "selected_ibnr": _m,
        "selected_pmpm": lambda x: f"${x:,.2f}",
    }
    if truth is not None:
        recent["true_ultimate"] = truth.reindex(tm.tail(6).index).to_numpy()
        fm["true_ultimate"] = _m
    lines += [_table(recent, fm), ""]
    if truth is not None:
        lines += ["\\* True ultimate comes from the synthetic answer key and is shown for validation only. A real valuation never has it.", ""]

    # ---- 3. Selections
    lines += ["## 3. Actuarial selections", ""]
    sel = _selections_table(v)
    if len(sel):
        lines += [
            "These are departures from the mechanical method, each logged with its rationale in `selections.json`. "
            "A selection applies only to closes on or after the month it references, so the hindsight test uses what was knowable at each close.",
            "",
            _table(sel, {"selection": str, "rationale": str}),
            "",
        ]
        if pack.mechanical is not None:
            imp = _impact_table(v, pack.mechanical)
            lines += [
                f"Impact at the {vm.strftime('%B %Y')} close:",
                "",
                _table(imp, {"ibnr_mechanical": _m, "ibnr_with_judgment": _m, "impact": lambda x: f"{x / 1e6:+.2f}M", "impact_pct": sgn}),
                "",
            ]
        if "ibnr_mechanical_error_pct" in h:
            biggest = (h["ibnr_selected_error_pct"].abs() - h["ibnr_mechanical_error_pct"].abs()).idxmin()
            lines += [
                f"The selections matter most at the {pd.Period(biggest, 'M').strftime('%B %Y')} close. The mechanical method missed true IBNR by "
                f"{sgn(h.loc[biggest, 'ibnr_mechanical_error_pct'])} there, and the method with judgment missed by {sgn(h.loc[biggest, 'ibnr_selected_error_pct'])} "
                "(section 6).",
                "",
            ]
    else:
        lines += ["No departures from the mechanical method this close.", ""]

    # ---- 4. Trend
    lines += ["## 4. PMPM trend", "", f"![PMPM trend]({chart_dir}/pmpm_trend.png)", ""]
    trend_tbl = pd.DataFrame(
        {
            v.label(c): {
                "Fitted annual trend": sgn(r_.trend.fitted_annual_trend),
                "Selected annual trend": sgn(r_.trend.annual_trend),
                "R²": f"{r_.trend.r_squared:.2f}",
                "Base PMPM (deseasonalised)": f"${r_.trend.base_pmpm:,.2f} @ {r_.trend.base_midpoint}",
                "Q4 / Q1 seasonal ratio": f"{r_.trend.seasonal_index.loc[10:12].mean() / r_.trend.seasonal_index.loc[1:3].mean():.2f}",
            }
            for c, r_ in v.categories.items()
            if r_.trend is not None
        }
    )
    trend_tbl.index.name = "Assumption"
    lines += [_table(trend_tbl, {c: str for c in trend_tbl.columns}), ""]
    if v.has_large:
        lines += [f"Large claims are trended at the selected {cfg.large_claim_trend:.0%} a year (frequency and severity combined).", ""]
    cy.index.name = "Year"
    lines += [
        "Calendar-year incurred PMPM (partial years are not comparable to full years because of seasonality; use the YTD comparison above):",
        "",
        _table(cy, {"months": lambda x: f"{x:.0f}", "member_months": lambda x: f"{x:,.0f}", "incurred": _m, "pmpm": lambda x: f"${x:,.2f}", "pmpm_change": lambda x: "" if pd.isna(x) else sgn(x)}),
        "",
        "## 5. Reserve roll-forward",
        "",
        f"From the {(vm - 1).strftime('%B')} close to the {vm.strftime('%B')} close.",
        "",
        _table(
            rf,
            {
                "prior_ibnr": _m,
                "paid_on_prior_months": _m,
                "expected_remaining": _m,
                "current_ibnr_prior_months": _m,
                "development": lambda x: f"{x / 1e6:+.1f}M",
                "development_pct_of_prior": sgn,
                "new_month_ibnr": _m,
                "current_ibnr": _m,
            },
        ),
        "",
        "Development = current IBNR on prior months − (prior IBNR − paid in month). Positive is adverse.",
        "",
        "## 6. Hindsight test",
        "",
        "Each prior valuation is re-run on the data as it stood at that month-end and compared with what is known now. "
        + ("Because the data is synthetic, the comparison is against **true** IBNR from the answer key." if truth is not None else "The comparison is against hindsight IBNR."),
        "",
        f"![Hindsight test]({chart_dir}/hindsight.png)",
        "",
    ]
    basis = "true_ibnr" if "true_ibnr" in h else "hindsight_ibnr"
    hcols = {"months_of_runout": lambda x: f"{x:.0f}", "ibnr_selected": _m}
    if "ibnr_mechanical" in h:
        hcols["ibnr_mechanical"] = _m
    hcols.update({"ibnr_completion_factor": _m, "ibnr_chain_ladder": _m, basis: _m, "ibnr_selected_error_pct": sgn})
    if "ibnr_mechanical" in h:
        hcols["ibnr_mechanical_error_pct"] = sgn
    hcols.update({"ibnr_completion_factor_error_pct": sgn, "ibnr_chain_ladder_error_pct": sgn})
    hh = h.copy()
    hh.index.name = "Valuation"
    sel_err = h["ibnr_selected_error_pct"]
    lines += [
        _table(hh, hcols),
        "",
        f"Selected-method error averaged {sgn(sel_err.mean())} (mean absolute {pct(sel_err.abs().mean())}). "
        + (f"The mechanical version's mean absolute error was {pct(h['ibnr_mechanical_error_pct'].abs().mean())}. " if "ibnr_mechanical" in h else "")
        + f"Completion factor only averaged {sgn(h['ibnr_completion_factor_error_pct'].mean())}; "
        f"chain ladder averaged {sgn(h['ibnr_chain_ladder_error_pct'].mean())}.",
        "",
        "## 7. Paid-month diagnostic",
        "",
        "Actual payments in each calendar month on incurred months already open, compared with the payments the selected link ratios "
        f"expected (lags 1 to 12, routine claims; large claimants are too lumpy for this test). Months more than {DIAG_TOL:.0%} off expected are flagged.",
        "",
        _table(
            diag.assign(flag=np.where((diag["actual_to_expected"] - 1).abs() > DIAG_TOL, "⚠", "")),
            {"actual_paid": _m, "expected_paid": _m, "actual_to_expected": lambda x: f"{x:.3f}", "flag": str},
        ),
        "",
    ]

    # ---- 8. ASOP 43
    lines += _asop43(pack, s, h)

    # ---- 9. Items for review
    lines += ["## 9. Items for review", ""]
    flagged = diag[(diag["actual_to_expected"] - 1).abs() > DIAG_TOL]
    if len(flagged):
        desc = ", ".join(f"{pd.Period(m, 'M').strftime('%b %Y')} ({x:.0%} of expected)" for m, x in flagged["actual_to_expected"].items())
        handled = all(str(m) in cfg.exclude_paid_months for m in flagged.index)
        lines.append(
            f"* **Paid-month anomaly: {desc}.** A low month followed by a high one is a processing backlog and its catch-up, not a change in incurred cost. "
            + (
                "These diagonals are excluded from the link-ratio averages (section 3). Drop the exclusions once the diagonals roll out of the "
                f"{cfg.cf_avg_months}-month window."
                if handled
                else f"Link ratios on these diagonals sit inside the {cfg.cf_avg_months}-month averaging window. Consider excluding them in `selections.json`."
            )
        )
    worst = h["ibnr_selected_error_pct"].abs().idxmax()
    lines.append(
        f"* **Hindsight.** The largest selected-method miss was the {pd.Period(worst, 'M').strftime('%B %Y')} valuation "
        f"({sgn(h.loc[worst, 'ibnr_selected_error_pct'])})."
    )
    if v.has_large:
        lr_ = v.categories["Large claims"].monthly
        lines.append(
            f"* **Large claims.** The large-claim pool runs at ${lr_['expected_claims'].iloc[-1] / lr_['member_months'].iloc[-1]:,.2f} PMPM for {vm.strftime('%B %Y')}. "
            "A run of $1M+ claimants would move it materially. Review the open large-claim list with case management before booking."
        )
    lines += [
        f"* **Margin.** IBNR plus margin and CAE ({_m(tot['total_liability'])}) sits "
        f"{'below' if tot['total_liability'] < tot['chain_ladder_p75'] else 'above'} the Mack chain ladder 75th percentile "
        f"({_m(tot['chain_ladder_p75'])}). Confirm the margin against the plan's historical IBNR runout before booking.",
        "",
        "Supporting exhibits (triangles, link ratios, factors, Mack detail, data checks and assumptions) are in the Excel exhibits workbook. "
        "The live-formula model, where selections can be changed, is in the `ibnr_model` workbook.",
        "",
    ]
    path.write_text("\n".join(lines))


def _asop43(pack: ReportPack, s: pd.DataFrame, h: pd.DataFrame) -> list[str]:
    """Disclosures organised along ASOP No. 43, Property/Casualty and Health Unpaid Claim Estimates."""
    v = pack.valuation
    cfg = v.config
    vm = v.valuation_month
    tot = s.loc["Total"]
    recon = pack.reconciliation
    n_fail = int((recon["result"] != "Pass").sum())
    basis = "true" if "true_ibnr" in h else "hindsight"
    return [
        "## 8. ASOP No. 43 disclosures",
        "",
        "This section is organised along Actuarial Standard of Practice No. 43, *Unpaid Claim Estimates*.",
        "",
        "**Intended purpose and measure.** The estimate is an unpaid claim estimate for medical claims incurred on or before "
        f"{vm.end_time.strftime('%B %d, %Y')} and unpaid at that date, for monthly financial reporting. The measure is an actuarial central estimate "
        f"({_m(tot['ibnr_selected'])}), plus an explicit {cfg.margin_pct:.1%} margin for adverse deviation and {cfg.cae_pct:.1%} for claim adjustment expense. "
        f"The recommended liability is {_m(tot['total_liability'])}.",
        "",
        "**Scope.** Commercial medical claims: inpatient (including large claimants), outpatient and professional. "
        "Excluded: pharmacy, capitation, provider incentive and risk-settlement accruals, premium deficiency reserves, and reinsurance or stop-loss recoveries.",
        "",
        "**Methods and rationale.** Completion factors on recent averages for mature months follow current claims processing, "
        "which has sped up over the experience period. A PMPM-based Bornhuetter-Ferguson covers immature months where paid-to-date is not credible. "
        "Large claims are reserved separately on a pooled B-F so that a single claimant does not drive a month's estimate. "
        "The chain ladder and its Mack range are benchmarks; section 1 explains why they are not selected.",
        "",
        f"**Key assumptions.** {cfg.cf_avg_months}-month average link ratios ex hi/lo; completion assumed at lag {cfg.max_lag}; "
        f"PMPM/B-F for the latest {cfg.pmpm_lags} months; trend and seasonality from section 4; large-claim pool trend {cfg.large_claim_trend:.0%}; "
        "judgmental selections as listed in section 3.",
        "",
        f"**Data and reliance.** The data is a synthetic claims extract, membership file, large-claimant file and pended-inventory report. "
        f"The estimate relies on these without audit, subject to the checks below ({n_fail} failures).",
        "",
        _table(recon, {"result": str, "detail": str}),
        "",
        f"**Uncertainty.** Actual runout will differ from the estimate. The Mack standard error on the chain ladder is {_m(tot['chain_ladder_se'])} "
        f"(75th–95th percentile {_m(tot['chain_ladder_p75'])}–{_m(tot['chain_ladder_p95'])}). Over {len(h)} prior closes, the selected method's mean absolute error "
        f"against {basis} IBNR was {h['ibnr_selected_error_pct'].abs().mean():.1%}. The main sources of uncertainty are: large-claim emergence, "
        "processing-speed changes, PMPM trend in the immature months, and seasonality in the latest quarter.",
        "",
        "**Changes since the prior valuation.** Methods and assumptions are unchanged from the prior close. Judgmental selections are logged in section 3 with the date each took effect.",
        "",
        "**Subsequent events.** None known.",
        "",
        "*This is an illustrative portfolio analysis on synthetic data. It is not a Statement of Actuarial Opinion.*",
        "",
    ]


def write_all(pack: ReportPack, out_dir: Path) -> dict[str, Path]:
    v = pack.valuation
    out_dir.mkdir(parents=True, exist_ok=True)
    charts = out_dir / "charts"
    charts.mkdir(exist_ok=True)
    tag = str(v.valuation_month)
    chart_ibnr_by_month(v, pack.truth, charts / "ibnr_by_month.png")
    chart_completion(v, charts / "completion_factors.png")
    chart_pmpm(v, charts / "pmpm_trend.png")
    chart_hindsight(pack.hindsight, charts / "hindsight.png")
    xlsx = out_dir / f"reserve_exhibits_{tag}.xlsx"
    md = out_dir / f"reserve_report_{tag}.md"
    write_excel(pack, xlsx)
    write_markdown(pack, md, "charts")
    return {"exhibits": xlsx, "report": md, "charts": charts}
