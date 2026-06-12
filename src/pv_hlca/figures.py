"""Publication figures from the sensitivity export (matplotlib only, no PowerBI).

Reads the tidy tables written by :func:`pv_hlca.export.run_and_export`
(``footprints.csv``, ``production.csv``, ``headline.csv``) and writes PNG+PDF.

Function names follow the manuscript figure order (fig1, fig2, ...):

  fig1  regional solar-electricity footprint with full sensitivity envelope + central
        case + literature bands
  fig2  tornado: sensitivity of the EU27 footprint to each lever
  fig3  scenario effect: baseline / baseline_2030 / NZIA per region, with bands
  fig4  EU27 vs CN footprint under current vs projected-2030 grids
  fig5  disaggregated solar footprint by upstream activity (needs heavy export)

Central case (defaults): capacity_factor=OWID, electricity_mix=WEO_STEPS,
module_efficiency=0.195, no degradation, IEA LCI, no forced upstream reshoring.
Shared lexicon constants (AX_FOOTPRINT, LBL_*, NZIA_DECLARED) keep wording uniform.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# slightly larger base fonts across all figures (structural text: titles, axis labels,
# ticks, legends); dense in-bar annotations keep their explicit smaller sizes
plt.rcParams.update({
    "font.size": 11.5,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "xtick.labelsize": 10.5,
    "ytick.labelsize": 10.5,
    "legend.fontsize": 10.5,
})

LEVERS = ["capacity_factor", "electricity_mix", "module_efficiency", "upstream_reshoring"]
# Central case = published configuration: OWID cumulative capacity factor
# (flow-realised fleet CF; RN single-grid-point sampling sits on the band's high
# edge in 18/22 regions, so it is a sensitivity bound, not the central case),
# 19.5% module efficiency, no forced upstream reshoring. electricity_mix only
# affects NZIA/2030 scenarios (the baseline verification figures are mix-invariant).
CENTRAL = {"capacity_factor": "OWID", "electricity_mix": "WEO_STEPS",
           "module_efficiency": 0.195, "upstream_reshoring": np.nan,
           "degradation_rate": 0.0, "lci_variant": "IEA"}
IPCC_BAND = (20, 80)
NREL_BAND = (39, 49)
#: countries shown in the headline model-comparison figure (manuscript selection)
SELECTION = ["AU", "BR", "CN", "EU27", "GB", "IN", "JP", "KR", "MX", "TR", "US"]
#: MARIO discrete palette (mario.views.plot_specs._PALETTES["mario"]) — named subset
MARIO = {"blue": "#3F8EFC", "mauve": "#BF9FC2", "teal": "#79C2D6", "green": "#67BA6F",
         "orange": "#D96940", "yellow": "#F8D35E", "dark_blue": "#02429B",
         "purple": "#69456C", "dark_teal": "#276D80", "dark_green": "#2D6332",
         "light_blue": "#8CBBFD"}
MARIO_CYCLE = ["#3F8EFC", "#BF9FC2", "#79C2D6", "#67BA6F", "#D96940", "#F8D35E",
               "#02429B", "#69456C", "#276D80", "#2D6332", "#753017", "#A47E07"]

#: physical uncertainty levers (move the footprint), distinct from the scenario
#: levers (electricity_mix, upstream_reshoring) which are analysis axes
PHYS_LEVERS = ["capacity_factor", "module_efficiency", "degradation_rate", "lci_variant"]
#: human-readable lever labels for the tornado figure
LEVER_LABELS = {
    "capacity_factor": "Capacity factor",
    "module_efficiency": "Module efficiency",
    "degradation_rate": "Annual degradation",
    "lci_variant": "Upstream LCI",
    "electricity_mix": "2030 grid mix",
    "upstream_reshoring": "Upstream reshoring",
}

# --------------------------------------------------------------------------- #
# shared lexicon — one wording for every figure (the caption defines the central
# case; figures never repeat it). Use these constants instead of inline strings.
# --------------------------------------------------------------------------- #
AX_FOOTPRINT = "Carbon footprint [gCO₂eq/kWh]"
AX_PRICE = "Solar electricity price [EUR/kWh]"
LBL_CENTRAL = "Hybrid — central case"
LBL_ENVELOPE = "Hybrid — sensitivity envelope"
LBL_TOPDOWN = "Top-Down"
NZIA_DECLARED = "NZIA (as declared)"        # the published 40% scenario; never "as-published"

#: shared, house style applied to every figure for cross-figure consistency
_STYLE = {
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.axisbelow": True,
    "axes.grid": True, "axes.grid.axis": "y",
    "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "legend.fontsize": 9, "legend.frameon": False,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
}
plt.rcParams.update(_STYLE)


# --------------------------------------------------------------------------- #
def _load(sens_dir, name="footprints.csv") -> pd.DataFrame:
    return pd.read_csv(Path(sens_dir) / name)


def _is_central(df: pd.DataFrame, exclude: str | None = None) -> pd.Series:
    """Boolean mask of rows at the central case (optionally ignoring one lever)."""
    mask = pd.Series(True, index=df.index)
    for k, v in CENTRAL.items():
        if k == exclude:
            continue
        col = df[k]
        mask &= col.isna() if (isinstance(v, float) and np.isnan(v)) else (col == v)
    return mask


def _save(fig, outdir, stem):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(outdir / f"{stem}.tiff", dpi=600, bbox_inches="tight",
                pil_kwargs={"compression": "tiff_lzw"})
    return outdir / f"{stem}.png"


# --------------------------------------------------------------------------- #
def fig1(sens_dir, outdir, scenario="baseline", countries=None, cap=100.0):
    """Headline: per-region solar footprint, Hybrid (central case + full sensitivity
    envelope) vs Top-Down, against IPCC/NREL literature bands. Regions are the
    manuscript selection, ordered by descending Hybrid central case. Top-Down values
    come from ``topdown.csv``; zero values are not drawn and a value above ``cap``
    (e.g. IN) is clipped with a dashed marker and its value annotated in parentheses.
    """
    countries = countries or SELECTION
    HYB, ENV, TD = MARIO["dark_blue"], MARIO["blue"], MARIO["orange"]
    df = _load(sens_dir)
    df = df[(df["scenario"] == scenario) & (df["region"].isin(countries))]
    cen = df[_is_central(df)].set_index("region")["footprint_gkwh"].reindex(countries)
    env = df.groupby("region")["footprint_gkwh"].agg(["min", "max"]).reindex(countries)
    try:
        td = _load(sens_dir, "topdown.csv").set_index("region")["footprint_gkwh"]
    except FileNotFoundError:
        td = pd.Series(dtype=float)
    order = cen.sort_values(ascending=False).index
    x = np.arange(len(order))

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.axhspan(*IPCC_BAND, color="0.82", alpha=0.55, zorder=0)
    ax.axhspan(*NREL_BAND, color="0.62", alpha=0.55, zorder=0)
    ax.vlines(x, env.loc[order, "min"], env.loc[order, "max"], color=ENV, lw=6.5, alpha=0.55, zorder=3)
    # tiny dots: the individual runs inside the envelope (distribution, not meant to be told apart)
    for xi, r in zip(x, order):
        vals = df[df["region"] == r]["footprint_gkwh"].values
        ax.scatter(np.full(len(vals), xi), vals, s=9, color=HYB, alpha=0.5,
                   linewidths=0, zorder=4)
    ax.plot(x, cen.loc[order], "o", color=HYB, ms=8.5, zorder=5)
    for xi, r in zip(x, order):
        v = td.get(r, np.nan)
        if np.isnan(v) or v <= 0:                    # zero top-down (e.g. BR, TR): not drawn
            continue
        if v <= cap:
            ax.plot([xi, xi], [v, cen[r]], color=TD, lw=0.8, alpha=0.30, zorder=1)
            ax.plot(xi, v, "D", color=TD, ms=8, mfc="white", mec=TD, mew=1.7, zorder=6)
        else:                                        # out of range (e.g. IN): dashed marker + (value)
            ax.plot([xi, xi], [cen[r], cap * 0.96], color=TD, lw=0.8, alpha=0.30, zorder=1)
            ax.scatter([xi], [cap * 0.96], marker="D", s=70, facecolors="white", edgecolors=TD,
                       linewidths=1.7, linestyle=(0, (2, 1.3)), zorder=6, clip_on=False)
            ax.annotate(f"({v:.0f})", xy=(xi, cap * 0.96), xytext=(xi, cap * 0.885),
                        ha="center", fontsize=8.5, color=TD, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(order)
    for lbl in ax.get_xticklabels():
        if lbl.get_text() in ("EU27", "CN"):
            lbl.set_fontweight("bold")
    ax.set_ylabel(AX_FOOTPRINT)
    ax.set_ylim(0, cap); ax.grid(axis="y", ls=":", alpha=0.4)
    handles = [Line2D([], [], marker="o", ls="", color=HYB, ms=7, label=LBL_CENTRAL),
               Line2D([], [], color=ENV, lw=4.5, alpha=0.6, label=LBL_ENVELOPE),
               Line2D([], [], marker="D", ls="", color=TD, mfc="white", mec=TD, mew=1.6, ms=7, label=LBL_TOPDOWN),
               Patch(facecolor="0.82", label="IPCC median range"),
               Patch(facecolor="0.62", label="NREL harmonized range")]
    ax.legend(handles=handles, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08),
              ncol=5, framealpha=0.92, columnspacing=1.2, handletextpad=0.5)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig1_headline")


#: PV supply-chain stages (commodity labels) in production order, with short tags
PV_STAGES = {"Metallurgical Grade silicon": "MG-Si", "Solar Grade silicon": "SG-Si",
             "Ingot": "Ingot", "Wafer": "Wafer", "Cells": "Cells",
             "PV modules": "Modules", "Solar": "Solar"}
#: each PV stage commodity -> its own producing activity (for the direct-emissions diagonal)
STAGE_ACTIVITY = {"Solar": "Solar Power Plant", "PV modules": "PV modules production",
                  "Cells": "Cells production", "Wafer": "Wafer production",
                  "Ingot": "Ingot production", "Solar Grade silicon": "Solar Grade silicon production",
                  "Metallurgical Grade silicon": "Metallurgical Grade silicon production"}
#: Shared category -> MARIO colour map, coordinated across BOTH decomposition figures
#: (fig_decomp, exploded/Map4, and fig_onestep, one-step/Map3) so a category keeps the
#: same colour everywhere. The three PV-chain categories form a light->dark blue family.
#: Aliases ("Metals and Machineries"/"Metals and Machinery", "Plastics and Chemicals"/
#: "Chemicals and plastics") point to the same colour.
CATEGORY_COLORS = {
    "Direct emissions": "#1a1a1a",
    "PV supply chain": "#8CBBFD",          # light blue
    "PV auxiliaries": "#3F8EFC",           # mario blue
    "PV end of life management": "#02429B",  # dark blue
    "Electricity": "#F8D35E",
    "Fuels": "#D96940",
    "Glass": "#BF9FC2",
    "Metals and Machinery": "#79C2D6", "Metals and Machineries": "#79C2D6",
    "Chemicals and plastics": "#67BA6F", "Plastics and Chemicals": "#67BA6F",
    "Transport": "#69456C",
    "Other": "#d0d0d0",
    "Solar PP, direct": "#555555",          # direct emissions of the solar plant
}
#: light fills that need dark text labels
_LIGHT_FILLS = {"#F8D35E", "#8CBBFD", "#67BA6F", "#BF9FC2", "#d0d0d0", "#79C2D6", "#3F8EFC"}

#: exploded (fig_decomp) categories, stacking order. "Direct emissions" is the
#: same-activity/same-region diagonal carved out of the mapped categories.
DECOMP_CATS = ["Direct emissions", "PV supply chain", "Electricity", "Metals and Machineries",
               "Plastics and Chemicals", "Glass", "Fuels", "Transport", "Other"]
_DECOMP_COLORS = {c: CATEGORY_COLORS[c] for c in DECOMP_CATS}
_DECOMP_LIGHT = _LIGHT_FILLS


def fig_decomp(sens_dir, outdir, scenario="baseline", regions=("EU27", "CN"),
               mapcol="Map4", min_label=5.0, mapping_path=None):
    """Per-stage decomposition of the PV supply-chain GHG footprint by activity of
    origin, one panel per region. Reads the exploded footprint ``fc_ex_<scenario>``
    (commodity-side, GHG), maps contributing activities to ``mapcol`` categories and
    shows each stage's composition as a 100% stacked bar with data labels (segments
    ≥ ``min_label`` %)."""
    fc = pd.read_parquet(Path(sens_dir) / f"fc_ex_{scenario}.parquet")
    if mapping_path is None:
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "Mapping_activities.xlsx"
    mp = pd.read_excel(mapping_path).set_index("Activity_from")[mapcol]
    fc = fc.assign(cat=fc["from_item"].map(mp).fillna("Other"))
    # carve out "Direct emissions": same producing activity, same region (the diagonal)
    direct = (fc["from_item"] == fc["to_commodity"].map(STAGE_ACTIVITY)) & (fc["from_region"] == fc["to_region"])
    fc.loc[direct, "cat"] = "Direct emissions"
    stages = list(PV_STAGES)

    fig, axes = plt.subplots(1, len(regions), figsize=(6.5 * len(regions), 5), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, reg in zip(axes, regions):
        raw = (fc[fc.to_region == reg].groupby(["to_commodity", "cat"])["ghg"].sum()
               .unstack("cat").reindex(stages).reindex(columns=DECOMP_CATS).fillna(0))
        absg = raw * 3.6                                       # gCO2eq/kWh-eq
        piv = raw.div(raw.sum(axis=1), axis=0) * 100           # share per stage
        x = np.arange(len(stages)); bottom = np.zeros(len(stages))
        for c in DECOMP_CATS:
            vals = piv[c].values
            ax.bar(x, vals, bottom=bottom, color=_DECOMP_COLORS[c], label=c, width=0.72,
                   edgecolor="white", lw=0.4)
            for xi, v, b, a in zip(x, vals, bottom, absg[c].values):
                if v >= min_label:
                    txt = f"{v:.0f}%\n({a:.1f})" if xi == len(stages) - 1 else f"{v:.0f}%"
                    ax.text(xi, b + v / 2, txt, ha="center", va="center",
                            fontsize=6.5, linespacing=0.9,
                            color="0.92" if c == "Direct emissions" else
                            ("0.15" if _DECOMP_COLORS[c] in _DECOMP_LIGHT else "white"),
                            fontweight="bold")
            bottom += vals
        ax.set_xticks(x); ax.set_xticklabels([PV_STAGES[s] for s in stages], rotation=40, ha="right")
        ax.set_title(reg, fontweight="bold"); ax.set_ylim(0, 100); ax.margins(x=0.02)
    axes[0].set_ylabel("Share of stage GHG footprint [%]")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, fontsize=8.5, bbox_to_anchor=(0.5, -0.07), frameon=False)
    fig.tight_layout()
    return fig, _save(fig, outdir, f"fig_decomp_{scenario}")


# --------------------------------------------------------------------------- #
# one-step decomposition ("supply chain impact linkages", thesis Fig.11 style)
# --------------------------------------------------------------------------- #
#: PV producing activities, upstream -> downstream, and their output-commodity labels
_ONESTEP_ACTS = ["Metallurgical Grade silicon production", "Solar Grade silicon production",
                 "Ingot production", "Wafer production", "Cells production",
                 "PV modules production", "Solar Power Plant"]
_ONESTEP_LABELS = ["MG-Si", "SG-Si", "Ingot", "Wafer", "Cells", "Modules", "Electricity"]
#: (upstream PV commodity consumed, activity that produces it) -> linkage bands
_ONESTEP_LINK = [("PV modules", "PV modules production", "Solar Power Plant"),
                 ("Cells", "Cells production", "PV modules production"),
                 ("Wafer", "Wafer production", "Cells production"),
                 ("Ingot", "Ingot production", "Wafer production"),
                 ("Solar Grade silicon", "Solar Grade silicon production", "Ingot production"),
                 ("Metallurgical Grade silicon", "Metallurgical Grade silicon production",
                  "Solar Grade silicon production")]
#: stacking order for the one-step (Map3) categories
_ONESTEP_ROW_ORDER = ["PV supply chain", "PV auxiliaries", "PV end of life management",
                      "Chemicals and plastics", "Electricity", "Fuels", "Glass",
                      "Metals and Machinery", "Transport", "Other", "Direct emissions"]


def _onestep_maps(mapping_path=None):
    """Map3 category lookups for the contributing commodities and (direct) activities."""
    if mapping_path is None:
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "Mapping_act_and_com.xlsx"
    act = pd.read_excel(mapping_path, sheet_name="Mapping_activities").set_index("Activity_from")["Map3"]
    com = pd.read_excel(mapping_path, sheet_name="Mapping_commodities").set_index("Commodity_from")["Map3"]
    return act.to_dict(), com.to_dict()


def _hex_gradient(start, end, steps):
    s = [int(start[i:i+2], 16) for i in (1, 3, 5)]
    e = [int(end[i:i+2], 16) for i in (1, 3, 5)]
    return ['#{:02x}{:02x}{:02x}'.format(*[round(s[i] + (e[i]-s[i])*t/(steps-1))
            for i in range(3)]) for t in range(steps)]


def _onestep_panel(ax, df, region, act_map, com_map):
    d = df[df.to_region == region].copy()
    d["cat"] = [act_map.get(it) if lv == "Activity" else com_map.get(it)
                for lv, it in zip(d.from_level, d.from_item)]
    d["cat"] = d["cat"].replace("Machinery and equipment", "Metals and Machinery")
    # keep every contribution (unmapped or off-list -> Other) so the stage total matches f_j
    d["cat"] = d["cat"].where(d["cat"].isin(_ONESTEP_ROW_ORDER), "Other")
    piv = (d.groupby(["cat", "to_activity"])["ghg"].sum().unstack("to_activity")
           .reindex(index=_ONESTEP_ROW_ORDER, columns=_ONESTEP_ACTS))
    col_tot = piv.sum(axis=0)
    pct = piv.div(col_tot, axis=1) * 100
    absol = col_tot * 3.6                                           # gCO2eq/kWh-eq per stage

    x = np.arange(len(_ONESTEP_ACTS)) * 1.5
    bw = 0.62
    seen = set()
    for j, act in enumerate(_ONESTEP_ACTS):
        bottom = 0.0
        for cat in _ONESTEP_ROW_ORDER:
            v = pct.loc[cat, act]
            if pd.notna(v) and v > 0:
                ax.bar(x[j], v, width=bw, bottom=bottom, color=CATEGORY_COLORS[cat],
                       edgecolor="white", linewidth=0.4, label=cat if cat not in seen else None)
                seen.add(cat); bottom += v

    pos = {a: x[j] for j, a in enumerate(_ONESTEP_ACTS)}
    for com, left_act, act in _ONESTEP_LINK:
        if left_act not in pos or act not in pos:
            continue
        tot = col_tot.get(act, np.nan)
        if not (tot and np.isfinite(tot)):
            continue
        val = d[(d.to_activity == act) & (d.from_level == "Commodity")
                & (d.from_item == com)]["ghg"].sum()
        perc = val / tot * 100
        xl, xr = pos[left_act] + bw/2, pos[act] - bw/2
        # flat, very pale fill of the linking band (no gradient)
        ax.fill([xl, xr, xr, xl], [100, perc, 0, 0], color=CATEGORY_COLORS["PV supply chain"],
                alpha=0.10, edgecolor=None, zorder=0)
        ax.plot([xl, xr], [100, perc], color="0.35", alpha=0.6, lw=1.1, zorder=1)
        ax.plot([xr, pos[act] + bw/2], [perc, perc], color="0.35", alpha=0.6, lw=1.1, zorder=1)
        ax.text(xr - 0.1, perc, f"{perc:.0f}%", ha="right", va="center", fontsize=9,
                color="0.2", fontweight="bold")

    ax.set_xticks(x); ax.set_xticklabels(_ONESTEP_LABELS, rotation=40, ha="right")
    ax.set_ylim(0, 100); ax.margins(x=0.02)
    ax.set_title(f"{region}  (Solar total: {absol.get('Solar Power Plant', float('nan')):.1f} "
                 f"gCO₂eq/kWh)", fontweight="bold", fontsize=10)


def fig_onestep(sens_dir, outdir, scenario="baseline", regions=("EU27", "CN"), mapping_path=None):
    """One-step ("supply chain impact linkages") decomposition of the PV footprint,
    reproducing thesis Fig.11. Reads ``onestep_<scenario>.parquet`` (the diag(f).z +
    diag(e) split; see :func:`pv_hlca.indicators.onestep_decomp_pv`). Each stage's
    total footprint is split into its direct emissions + the *full embodied* footprint
    of each first-tier input; the six upstream PV commodities collapse to a single
    "PV supply chain" bar, and the connecting gradient bands carry the % of the stage
    inherited from the immediately-upstream PV commodity. Colours are shared with
    :func:`fig_decomp` via ``CATEGORY_COLORS``."""
    df = pd.read_parquet(Path(sens_dir) / f"onestep_{scenario}.parquet")
    act_map, com_map = _onestep_maps(mapping_path)
    fig, axes = plt.subplots(1, len(regions), figsize=(6.5 * len(regions), 7.3), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, reg in zip(axes, regions):
        _onestep_panel(ax, df, reg, act_map, com_map)
    axes[0].set_ylabel("Share of stage GHG footprint [%]")
    # legend in the row_order, top->bottom of the stack
    h, l = axes[0].get_legend_handles_labels()
    hd = dict(zip(l, h))
    order = [c for c in _ONESTEP_ROW_ORDER if c in hd]
    if "Direct emissions" in order:                       # first, as in fig_breakdown (3a)
        order = ["Direct emissions"] + [c for c in order if c != "Direct emissions"]
    # two balanced rows: avoids a lone trailing column (e.g. "Other" starting a new one)
    fig.legend([hd[c] for c in order], order, loc="lower center",
               ncol=(len(order) + 1) // 2, fontsize=8,
               bbox_to_anchor=(0.5, -0.08), frameon=False)
    fig.tight_layout()
    return fig, _save(fig, outdir, f"fig_onestep_{scenario}")


def _lever_swing_pct(df, region, scenario):
    """For one region, the signed % deviation from the central footprint that each
    physical lever can produce: {lever: (lo_pct, hi_pct)}. Normalised by the region's
    own central footprint so regions are directly comparable."""
    d = df[(df["region"] == region) & (df["scenario"] == scenario)]
    central = float(d[_is_central(d)]["footprint_gkwh"].iloc[0])
    out = {}
    for lever in PHYS_LEVERS:
        sub = d[_is_central(d, exclude=lever)]["footprint_gkwh"]
        if sub.notna().sum() >= 2:
            out[lever] = ((sub.min() - central) / central * 100,
                          (sub.max() - central) / central * 100)
    return out, central


def _tornado_panel(ax, sens_dir, regions=("EU27", "CN"), scenario="baseline"):
    """Draw the lever-ranking tornado on ``ax`` (used standalone by :func:`fig2` and in
    the combined sensitivity figure). Returns the number of levers shown."""
    df = _load(sens_dir)
    per_region = {r: _lever_swing_pct(df, r, scenario)[0] for r in regions}
    centrals = {r: _lever_swing_pct(df, r, scenario)[1] for r in regions}
    # fixed order: by the largest absolute swing across regions (most influential on top)
    levers = [l for l in PHYS_LEVERS if any(l in per_region[r] for r in regions)]
    levers.sort(key=lambda l: max(max(abs(v) for v in per_region[r].get(l, (0, 0)))
                                  for r in regions))
    colors = [MARIO["teal"], MARIO["orange"], MARIO["green"], MARIO["mauve"]]
    reg_color = {r: colors[i % len(colors)] for i, r in enumerate(regions)}
    n = len(regions); h = 0.8 / n
    for j, r in enumerate(regions):
        offset = (j - (n - 1) / 2) * h
        for i, lever in enumerate(levers):
            lo, hi = per_region[r].get(lever, (0, 0))
            y = i + offset
            ax.barh(y, hi - lo, left=lo, height=h * 0.9, color=reg_color[r], alpha=0.85, zorder=3,
                    label=f"{r} (central case: {centrals[r]:.0f} gCO₂eq/kWh)" if i == 0 else None)
            if lo < -0.1:
                ax.annotate(f"{lo:.0f}%", xy=(lo, y), xytext=(-2, 0), textcoords="offset points",
                            va="center", ha="right", fontsize=7.5, color=reg_color[r])
            if hi > 0.1:
                ax.annotate(f"+{hi:.0f}%", xy=(hi, y), xytext=(2, 0), textcoords="offset points",
                            va="center", ha="left", fontsize=7.5, color=reg_color[r])
    ax.axvline(0, color="0.2", lw=1.3, ls="--", zorder=2)
    ax.set_yticks(range(len(levers)))
    ax.set_yticklabels([LEVER_LABELS[l] for l in levers])
    ax.set_xlabel("Deviation from the region's footprint in central case [%]")
    ax.margins(x=0.16)
    ax.legend(loc="lower left", fontsize=8)
    return len(levers)


def fig2(sens_dir, outdir, regions=("EU27", "CN"), scenario="baseline"):
    """Lever ranking (tornado): signed % deviation from each region's own central
    footprint produced by each physical uncertainty lever (EU27 vs China)."""
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    _tornado_panel(ax, sens_dir, regions, scenario)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig2_tornado")


def fig3(sens_dir, outdir, scenarios=("baseline", "baseline_2030", "NZIA")):
    """Per-region footprint by scenario: central case (markers) + sensitivity bands."""
    df = _load(sens_dir)
    df = df[df["scenario"].isin(scenarios)]
    order = (df[(df.scenario == "baseline") & _is_central(df)]
             .set_index("region")["footprint_gkwh"].sort_values().index)
    x = np.arange(len(order))
    width = 0.8 / len(scenarios)
    colors = {"baseline": "#444", "baseline_2030": "#2a7", "NZIA": "#e67"}

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.axhspan(*IPCC_BAND, color="#728FA5", alpha=0.15)
    for j, scen in enumerate(scenarios):
        d = df[df.scenario == scen]
        rng = d.groupby("region")["footprint_gkwh"].agg(["min", "max"]).reindex(order)
        cen = d[_is_central(d)].set_index("region")["footprint_gkwh"].reindex(order)
        xx = x + (j - (len(scenarios) - 1) / 2) * width
        ax.vlines(xx, rng["min"], rng["max"], color=colors.get(scen, "gray"), lw=2, alpha=0.5)
        ax.plot(xx, cen, "o", color=colors.get(scen, "gray"), ms=4, label=scen)
    ax.set_xticks(x); ax.set_xticklabels(order, rotation=45, ha="right")
    ax.set_ylabel(AX_FOOTPRINT)
    ax.set_title("Scenario effect on the regional solar footprint", fontweight="bold")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig3_scenario_effect")


def fig4(sens_dir, outdir, regions=("EU27", "CN")):
    """EU27 vs CN footprint, current grid (baseline) vs projected 2030 (baseline_2030)."""
    df = _load(sens_dir)
    df = df[df.region.isin(regions) & df.scenario.isin(["baseline", "baseline_2030"])]
    cen = df[_is_central(df)].pivot_table(index="region", columns="scenario",
                                          values="footprint_gkwh").reindex(regions)
    x = np.arange(len(regions))
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.axhspan(*IPCC_BAND, color="#728FA5", alpha=0.15, label="IPCC median range")
    for i, r in enumerate(regions):
        b, p = cen.loc[r, "baseline"], cen.loc[r, "baseline_2030"]
        ax.annotate("", xy=(x[i], p), xytext=(x[i], b),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=2))
        ax.plot(x[i], b, "o", color="#444", ms=9)
        ax.plot(x[i], p, "o", color="#2a7", ms=9)
        ax.text(x[i] + 0.06, b, f"{b:.0f}", va="center")
        ax.text(x[i] + 0.06, p, f"{p:.0f}", va="center", color="#2a7")
    ax.plot([], [], "o", color="#444", label="current grid (baseline)")
    ax.plot([], [], "o", color="#2a7", label="projected 2030 grid")
    ax.set_xticks(x); ax.set_xticklabels(regions)
    ax.set_xlim(-0.5, len(regions) - 0.3)
    ax.set_ylabel(AX_FOOTPRINT)
    ax.set_title("Grid-decarbonisation effect (2030 projected for both regions)",
                 fontweight="bold")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig4_eu_cn_2030")


def fig5(sens_dir, outdir, mapping_path=None, regions=("CN", "EU27"), scenario="baseline"):
    """Disaggregated solar footprint by upstream activity group (central case).

    Needs the heavy export (``f_dis_solar.parquet``). From-activities are grouped
    with the activity mapping (``Mapping_activities.xlsx``, Map4) and summed over
    from-regions, giving a stacked bar (gCO₂eq/kWh) per producing region.
    """
    fpath = Path(sens_dir) / "f_dis_solar.parquet"
    if not fpath.exists():
        raise FileNotFoundError(f"{fpath} missing — run export with heavy=True.")
    fd = pd.read_parquet(fpath)
    fd = fd[(fd["scenario"] == scenario) & _is_central(fd)]
    if mapping_path is None:
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "Mapping_activities.xlsx"
    mp = pd.read_excel(mapping_path).set_index("Activity_from")["Map4"]
    fd = fd.assign(group=fd["Activity"].map(mp).fillna("Other"))
    g = (fd.groupby(["Region_to", "group"])["CO2eq"].sum() * 3.6).unstack("group")
    g = g.reindex(regions).fillna(0.0)
    g = g[g.sum().sort_values(ascending=False).index]      # biggest groups first

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bottom = np.zeros(len(g))
    cmap = plt.get_cmap("tab10")
    for k, col in enumerate(g.columns):
        ax.bar(g.index, g[col].values, bottom=bottom, label=col, color=cmap(k % 10))
        bottom += g[col].values
    ax.set_ylabel(AX_FOOTPRINT)
    ax.set_title("Disaggregated solar footprint by upstream activity", fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig5_disaggregated")


def _upstream_panel(ax, sens_dir, region="EU27", scenario="NZIA"):
    """Draw the upstream-reshoring scan on ``ax`` (creates its own twin axis). Footprint
    on the left axis, recovered EU value added on the right, as the EU domestic share of
    the upstream PV stages is swept 0->1, holding every other lever at the central case."""
    base = dict(capacity_factor="OWID", electricity_mix="WEO_STEPS",
                module_efficiency=0.195, degradation_rate=0.0, lci_variant="IEA")

    def _sel(df):
        m = pd.Series(True, index=df.index)
        for k, v in base.items():
            m &= df[k] == v
        return df[m & (df["scenario"] == scenario)]

    f = _sel(_load(sens_dir)); f = f[f["region"] == region]
    va = _sel(_load(sens_dir, "value_added.csv"))
    ups = sorted(f["upstream_reshoring"].dropna().unique())
    foot = [float(f[f["upstream_reshoring"] == u]["footprint_gkwh"].iloc[0]) for u in ups]
    # EU value added recovered relative to no upstream reshoring (up=0), isolated
    va_eu = {u: va[(va["upstream_reshoring"] == u) & (va["region"] == region)]["value_added"].sum()
             for u in ups}
    ref = va_eu[min(ups)]
    va_rec = [(va_eu[u] - ref) / 1e3 for u in ups]          # M€ -> b€
    PUB_X = 0.4

    ax2 = ax.twinx(); ax2.grid(False)
    # the two curves are identified by the matching axis colours (no legend needed)
    C_FOOT, C_VA = MARIO["dark_blue"], MARIO["orange"]
    xs = [u * 100 for u in ups]                    # plot the domestic share as integer %
    ax2.plot(xs, va_rec, "s-", color=C_VA, lw=2, ms=5, zorder=2)
    ax.plot(xs, foot, "o-", color=C_FOOT, lw=2, ms=6, zorder=3)
    # NZIA as declared = black vertical line at the 40% upstream share
    ax.axvline(PUB_X * 100, color="black", ls="--", lw=1.3, zorder=4)
    ax.annotate("NZIA", xy=(PUB_X * 100, 1.0), xycoords=("data", "axes fraction"), xytext=(4, -4),
                textcoords="offset points", fontsize=8.5, color="black", va="top", ha="left")
    ax.set_xlabel("EU domestic production share of PV supply-chain stages [%]")
    ax.set_xticks(range(0, 101, 20))
    ax.set_ylabel(f"{region} footprint [gCO₂eq/kWh]", color=C_FOOT)
    ax2.set_ylabel("EU value added recovered [b€]", color=C_VA)
    ax.tick_params(axis="y", colors=C_FOOT)
    ax2.tick_params(axis="y", colors=C_VA)
    # integer ticks from 0: footprint every 5 gCO2eq/kWh, VA every 1 b€; the VA axis is
    # extended to fmax/5 so both axes have the same number of intervals -> aligned gridlines
    fmax = 5 * np.ceil(max(foot) / 5)
    ax.set_ylim(0, fmax); ax.set_yticks(np.arange(0, fmax + 1, 5))
    vmax = max(np.ceil(max(va_rec)), fmax / 5)
    ax2.set_ylim(0, vmax); ax2.set_yticks(np.arange(0, vmax + 1, 1))
    ax2.spines["right"].set_visible(True)          # show the secondary-axis border
    return ax2


def fig_upstream(sens_dir, outdir, region="EU27", scenario="NZIA"):
    """Upstream-reshoring scan (R1.7 / R2.3): EU27 footprint (left) and value added
    recovered from foreign suppliers (right) as the EU domestic share of the upstream PV
    stages is swept 0->1. The NZIA as declared (40% upstream) is marked."""
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    _upstream_panel(ax, sens_dir, region, scenario)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_upstream")


def fig_sensitivity(sens_dir, outdir):
    """Sensitivity and robustness (combined): (a) tornado ranking of the physical
    uncertainty levers (EU27 vs China) and (b) the upstream-reshoring scan of the EU
    footprint and recovered value added. Merges :func:`fig2` and :func:`fig_upstream`."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 7.3))
    _tornado_panel(axes[0], sens_dir)
    _upstream_panel(axes[1], sens_dir)
    axes[0].set_title("a) Footprint sensitivity to input-data uncertainty")
    axes[1].set_title("b) Footprint and value added vs upstream reshoring")
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_sensitivity")


def fig_breakdown(sens_dir, outdir, scenario="baseline", countries=None, mapping_path=None):
    """Hybrid footprint breakdown (R2.7 / minor L264-266): the disaggregated solar
    footprint of each producing region, split two ways — (a) by activity of origin
    (Map4 groups) and (b) by region of origin (China / EU27 / RoW). Shows how the
    hybrid model attributes upstream impacts to where production actually occurs,
    the structural redistribution the top-down representation cannot resolve.
    Needs the heavy export ``f_dis_solar.parquet`` (central case).
    """
    fpath = Path(sens_dir) / "f_dis_solar.parquet"
    if not fpath.exists():
        raise FileNotFoundError(f"{fpath} missing — run the heavy export (f_dis_solar).")
    countries = countries or SELECTION
    fd = pd.read_parquet(fpath)
    fd = fd[(fd["scenario"] == scenario) & _is_central(fd)].copy()
    fd["CO2eq"] *= 3.6                                        # -> gCO2eq/kWh
    if mapping_path is None:
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "Mapping_activities.xlsx"
    mp = pd.read_excel(mapping_path).set_index("Activity_from")["Map4"]
    fd["group"] = fd["Activity"].map(mp).fillna("Other")
    # the PV activities are the direct emitters of each stage — label them as in
    # fig_onestep ("Direct emissions"), so the two figures share one category meaning
    fd["group"] = fd["group"].replace({"PV supply chain": "Direct emissions",
                                       "Solar PP, direct": "Direct emissions"})
    fd["origin"] = np.where(fd["Region_from"] == "CN", "China",
                    np.where(fd["Region_from"] == "EU27", "European Union", "Rest of World"))

    order = (fd.groupby("Region_to")["CO2eq"].sum().reindex(countries)
             .sort_values(ascending=True).index)

    fig, axes = plt.subplots(1, 2, figsize=(13, 0.5 * len(order) + 1.6), sharey=True)

    # (a) by activity of origin
    ga = fd.groupby(["Region_to", "group"])["CO2eq"].sum().unstack("group").reindex(order).fillna(0)
    ga = ga[[c for c in CATEGORY_COLORS if c in ga.columns] +
            [c for c in ga.columns if c not in CATEGORY_COLORS]]
    left = np.zeros(len(ga))
    for col in ga.columns:
        axes[0].barh(ga.index, ga[col].values, left=left,
                     color=CATEGORY_COLORS.get(col, "#bbb"), label=col, height=0.7)
        left += ga[col].values
    for yi, tot in enumerate(left):                          # total at the end of each bar
        axes[0].text(tot + 0.6, yi, f"{tot:.0f}", va="center", ha="left", fontsize=7.5, color="0.25")
    axes[0].set_title("a) By activity of origin")
    axes[0].set_xlabel("gCO₂eq/kWh")
    axes[0].legend(fontsize=7.5, ncol=1, loc="lower right")

    # (b) by region of origin
    ORI = {"China": MARIO["blue"], "European Union": MARIO["dark_blue"], "Rest of World": MARIO["orange"]}
    gb = fd.groupby(["Region_to", "origin"])["CO2eq"].sum().unstack("origin").reindex(order).fillna(0)
    gb = gb[[c for c in ORI if c in gb.columns]]
    left = np.zeros(len(gb))
    for col in gb.columns:
        axes[1].barh(gb.index, gb[col].values, left=left, color=ORI[col], label=col, height=0.7)
        left += gb[col].values
    for yi, tot in enumerate(left):
        axes[1].text(tot + 0.6, yi, f"{tot:.0f}", va="center", ha="left", fontsize=7.5, color="0.25")
    axes[1].set_title("b) By region of origin")
    axes[1].set_xlabel("gCO₂eq/kWh")
    axes[1].legend(fontsize=8, loc="lower right")
    for lbl in axes[0].get_yticklabels():
        if lbl.get_text() in ("EU27", "CN"):
            lbl.set_fontweight("bold")
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_breakdown")


#: value-added factor colours and order (bottom -> top)
_VA_FACTORS = ["Compensation of employees",
               "Operating surplus: Consumption of fixed capital",
               "Taxes, subsidies and net surplus"]
_VA_COLORS = {"Compensation of employees": MARIO["dark_blue"],
              "Operating surplus: Consumption of fixed capital": MARIO["teal"],
              "Taxes, subsidies and net surplus": MARIO["yellow"]}
_VA_SHORT = {"Compensation of employees": "Wages",
             "Operating surplus: Consumption of fixed capital": "Fixed capital",
             "Taxes, subsidies and net surplus": "Taxes & surplus"}


def fig_va_employment(sens_dir, outdir, ref="baseline_2030", scen="NZIA",
                      min_abs_va=40.0, mapping_path=None):
    """Value-added and employment variation of the NZIA, by region (Fig.5). The
    reshoring effect is isolated by comparing NZIA against ``baseline_2030`` (both at
    the 2030 grid), not the 2024 baseline — otherwise the grid-projection swamps it.
    (a) value added by factor (wages / fixed capital / taxes & surplus); (b) employment
    by sector (Map4). Bars are the absolute variation; the dot is the % change. EU27
    gains ~€4 bn (about half as wages), China bears the largest loss.
    """
    base = dict(capacity_factor="OWID", electricity_mix="WEO_STEPS",
                module_efficiency=0.195, degradation_rate=0.0, lci_variant="IEA")

    def _sel(df, scn):
        m = pd.Series(True, index=df.index)
        for k, v in base.items():
            m &= df[k] == v
        return df[m & (df["scenario"] == scn) & (df["upstream_reshoring"].isna())]

    # (a) value added by factor
    va = _load(sens_dir, "value_added.csv")
    va = va[va["factor"].isin(_VA_FACTORS)]
    vb = _sel(va, ref).groupby(["region", "factor"])["value_added"].sum()
    vn = _sel(va, scen).groupby(["region", "factor"])["value_added"].sum()
    dva = (vn - vb).unstack("factor").fillna(0)
    va_base = _sel(va, ref).groupby("region")["value_added"].sum()
    va_pct = (dva.sum(axis=1) / va_base * 100)

    # (b) employment by sector (Map4)
    if mapping_path is None:
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "Mapping_activities.xlsx"
    mp = pd.read_excel(mapping_path).set_index("Activity_from")["Map4"]
    emp = _load(sens_dir, "employment.csv")
    emp["sector"] = emp["activity"].map(mp).fillna("Other")
    # employment is a sectoral split, not an emissions split: the direct PV/solar jobs
    # belong to the PV supply chain (no "Direct emissions" category here)
    emp["sector"] = emp["sector"].replace({"Solar PP, direct": "PV supply chain"})
    eb = _sel(emp, ref).groupby(["region", "sector"])["employment"].sum()
    en = _sel(emp, scen).groupby(["region", "sector"])["employment"].sum()
    demp = (en - eb).unstack("sector").fillna(0)
    emp_base = _sel(emp, ref).groupby("region")["employment"].sum()
    emp_pct = (demp.sum(axis=1) / emp_base.replace(0, np.nan) * 100)

    # regions: those with a non-negligible VA change, ordered by total VA delta
    regions = dva.sum(axis=1)[dva.sum(axis=1).abs() > min_abs_va].sort_values(ascending=False).index
    x = np.arange(len(regions))

    def _annotate_pct(ax, totals, pct, scale, which, fmt="{:+.2f}%"):
        """Label the % change above/below the bars of the ``which`` regions."""
        for xi, r in zip(x, regions):
            if r in which and r in pct.index:
                v = totals.get(r, 0) / scale
                ax.annotate(fmt.format(pct[r]), xy=(xi, v),
                            xytext=(0, 6 if v >= 0 else -12), textcoords="offset points",
                            ha="center", fontsize=8, fontweight="bold", color="0.25")

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.0))
    # --- (a) VA ---
    ax = axes[0]
    bottom_pos = np.zeros(len(regions)); bottom_neg = np.zeros(len(regions))
    for f in _VA_FACTORS:
        vals = dva.reindex(regions)[f].values / 1000.0          # M€ -> b€
        bot = np.where(vals >= 0, bottom_pos, bottom_neg)
        ax.bar(x, vals, bottom=bot, color=_VA_COLORS[f], label=_VA_SHORT[f], width=0.7)
        bottom_pos += np.where(vals >= 0, vals, 0); bottom_neg += np.where(vals < 0, vals, 0)
    ax.axhline(0, color="0.3", lw=0.8)
    _annotate_pct(ax, dva.sum(axis=1), va_pct, 1000.0, which=("EU27", "CN"))
    ax.set_xticks(x); ax.set_xticklabels(regions, rotation=45, ha="right")
    for lbl in ax.get_xticklabels():
        if lbl.get_text() in ("EU27", "CN"):
            lbl.set_fontweight("bold")
    ax.set_ylabel("Value added variation [b€]")
    ax.set_title("a) Value added (% = share of regional GDP)")
    ax.legend(fontsize=8, loc="lower left")
    y0, y1 = ax.get_ylim(); ax.set_ylim(y0 - 0.10 * (y1 - y0), y1)   # headroom to read the CN total

    # --- (b) employment ---
    ax = axes[1]
    sectors = [s for s in CATEGORY_COLORS if s in demp.columns] + \
              [s for s in demp.columns if s not in CATEGORY_COLORS]
    bottom_pos = np.zeros(len(regions)); bottom_neg = np.zeros(len(regions))
    for s in sectors:
        vals = demp.reindex(regions)[s].values
        bot = np.where(vals >= 0, bottom_pos, bottom_neg)
        ax.bar(x, vals, bottom=bot, color=CATEGORY_COLORS.get(s, "#bbb"), label=s, width=0.7)
        bottom_pos += np.where(vals >= 0, vals, 0); bottom_neg += np.where(vals < 0, vals, 0)
    ax.axhline(0, color="0.3", lw=0.8)
    _annotate_pct(ax, demp.sum(axis=1), emp_pct, 1.0, which=("EU27", "WA", "CN"), fmt="{:+.3f}%")
    ax.set_xticks(x); ax.set_xticklabels(regions, rotation=45, ha="right")
    for lbl in ax.get_xticklabels():
        if lbl.get_text() in ("EU27", "CN"):
            lbl.set_fontweight("bold")
    ax.set_ylabel("Employment variation [1000 persons]")
    ax.set_title("b) Employment")
    ax.legend(fontsize=7.5, ncol=1, loc="lower left")
    y0, y1 = ax.get_ylim(); ax.set_ylim(y0 - 0.08 * (y1 - y0), y1)   # room for the CN total label

    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_va_employment")


def fig_stages(sens_dir, outdir, cfg=None):
    """Supply-chain reconfiguration, two complementary views of how the NZIA reshapes
    the EU PV supply chain, Baseline 2030 vs NZIA (both at the projected 2030 grid, so the
    grid-decarbonisation effect is isolated from the reshoring effect):

    (a) EU world-production share — the EU's weight in *global* output of each of the six
        stages: only modules become significant (~10%) while the upstream stays a few % —
        downstream-concentrated reshoring and upstream value-added leakage.
    (b) Footprint by origin — the EU PV carbon footprint (g CO2eq/kWh) split by region of
        origin (China / EU27 / rest of world). The NZIA lifts the domestic share from ~16%
        to ~22% while only modestly cutting the absolute footprint, because reshoring is
        downstream while the upstream stays abroad.

    Together: the NZIA reshapes the chain mainly downstream, and the carbon kept onshore
    rises, but the bulk of the footprint still originates abroad.
    """
    from . import io as _io
    from .indicators import TJ_TO_GKWH
    cfg = cfg or _io.load_config()
    stages = ["Metallurgical Grade silicon", "Solar Grade silicon", "Ingot",
              "Wafer", "Cells", "PV modules"]
    labels = ["MG-Si", "SoG-Si", "Ingot", "Wafer", "Cells", "PV modules"]

    # (a) EU world-production share, from the model output
    prod = _load(sens_dir, "production.csv")
    base = dict(capacity_factor="OWID", electricity_mix="WEO_STEPS",
                module_efficiency=0.195, degradation_rate=0.0, lci_variant="IEA")

    def world_share(scen):
        m = pd.Series(True, index=prod.index)
        for k, v in base.items():
            m &= prod[k] == v
        d = prod[m & (prod["scenario"] == scen) & (prod["upstream_reshoring"].isna())]
        world = d.groupby("commodity")["production"].sum()
        eu = d[d["region"] == "EU27"].groupby("commodity")["production"].sum()
        return (eu / world * 100).reindex(stages).fillna(0).values

    # (b) EU PV footprint by region of origin (same split/labels/colours as fig_breakdown 3b)
    ORI = {"China": MARIO["blue"], "European Union": MARIO["dark_blue"], "Rest of World": MARIO["orange"]}

    def origin_split(scen):
        df = pd.read_parquet(sens_dir / f"fc_ex_{scen}.parquet")
        d = df[(df["to_region"] == "EU27") & (df["to_commodity"] == "Solar")].copy()
        d["origin"] = np.where(d["from_region"] == "CN", "China",
                       np.where(d["from_region"] == "EU27", "European Union", "Rest of World"))
        g = d.groupby("origin")["ghg"].sum() * TJ_TO_GKWH
        return g.reindex(list(ORI)).fillna(0.0)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.0))

    # --- panel a: EU world-production share ---
    ax = axes[0]
    y = np.arange(len(stages)); h = 0.38
    b, n = world_share("baseline_2030"), world_share("NZIA")
    ax.barh(y + h/2, b, height=h, color=MARIO["light_blue"], label="Baseline 2030")
    ax.barh(y - h/2, n, height=h, color=MARIO["dark_blue"], label="NZIA")
    for yi, v0, v1 in zip(y, b, n):
        ax.text(v0 + max(n.max(), 1) * 0.012, yi + h/2, f"{v0:.1f}%",
                va="center", fontsize=7, color="0.4")
        ax.text(v1 + max(n.max(), 1) * 0.012, yi - h/2, f"{v1:.1f}%",
                va="center", fontsize=7, color=MARIO["dark_blue"], fontweight="bold")
    ax.set_yticks(y); ax.set_yticklabels(labels); ax.invert_yaxis()
    ax.set_xlabel("EU world-production share [%]")
    ax.set_title("a) EU production share (of world output)")
    ax.margins(x=0.14)
    ax.legend(loc="center right")

    # --- panel b: EU PV footprint by region of origin ---
    ax = axes[1]
    scens = [("baseline_2030", "Baseline 2030"), ("NZIA", "NZIA")]
    yb = np.arange(len(scens)); hb = 0.5
    for yi, (scen, _) in zip(yb, scens):
        g = origin_split(scen)
        left = 0.0
        for col in ORI:
            v = float(g[col])
            ax.barh(yi, v, height=hb, left=left, color=ORI[col])
            if v > 1.5:                                   # in-bar value where it fits
                ax.text(left + v / 2, yi, f"{v:.1f}", va="center", ha="center",
                        fontsize=8, color="white", fontweight="bold")
            left += v
        dom = float(g["European Union"])
        ax.text(left * 1.02, yi, f"{left:.1f}  ({dom / left * 100:.0f}% dom.)",
                va="center", fontsize=8, color="0.3")
    ax.set_yticks(yb); ax.set_yticklabels([lbl for _, lbl in scens]); ax.invert_yaxis()
    ax.set_xlabel("EU PV footprint by origin [g CO$_2$eq/kWh]")
    ax.set_title("b) Footprint by origin")
    ax.margins(x=0.18)
    ax.legend(handles=[Patch(color=ORI[c], label=c) for c in ORI], loc="center right")

    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_stages")


def fig_prices(sens_dir, outdir, scenario="baseline", countries=None, cfg=None):
    """Price verification (R2.7): per-region solar-electricity producer price, hybrid
    (central case + envelope) and Top-Down, against the IRENA 2024 LCOE 5th–95th range
    and weighted average, mapped from the 22 model regions to IRENA macro-regions. The
    Top-Down series is the published legacy-EXIOBASE 'Solar' price (see
    :func:`pv_hlca.indicators.topdown_price`); zero values are not drawn.
    """
    from . import io as _io
    from . import indicators
    cfg = cfg or _io.load_config()
    countries = countries or SELECTION
    HYB, ENV, TD = MARIO["dark_blue"], MARIO["blue"], MARIO["orange"]
    df = _load(sens_dir, "prices.csv")
    df = df[(df["scenario"] == scenario) & (df["region"].isin(countries))]
    cen = df[_is_central(df)].set_index("region")["price_eur_kwh"].reindex(countries)
    env = df.groupby("region")["price_eur_kwh"].agg(["min", "max"]).reindex(countries)

    irena = pd.read_csv(Path(cfg["paths"]["reference_dir"]) / "irena_lcoe_2024.csv") \
        if "reference_dir" in cfg.get("paths", {}) else \
        pd.read_csv(Path(__file__).resolve().parents[2] / "reference" / "irena_lcoe_2024.csv")
    macro = cfg["mappings"]["region_to_irena_macro"]
    irena = irena.set_index("macro_region")
    ref = pd.DataFrame({r: irena.loc[macro[r]] for r in countries if macro.get(r) in irena.index}).T

    order = cen.sort_values(ascending=False).index
    x = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for xi, r in zip(x, order):
        if r in ref.index:
            p05, wavg, p95 = ref.loc[r, "p05"], ref.loc[r, "weighted"], ref.loc[r, "p95"]
            ax.add_patch(plt.Rectangle((xi - 0.34, p05), 0.68, p95 - p05,
                                       color="0.78", alpha=0.6, zorder=0))
            ax.hlines(wavg, xi - 0.34, xi + 0.34, color="0.25", lw=2, zorder=2)
    ax.vlines(x, env.loc[order, "min"], env.loc[order, "max"], color=ENV, lw=4.5, alpha=0.55, zorder=3)
    ax.plot(x, cen.loc[order], "o", color=HYB, ms=6.5, zorder=5)
    td = indicators.topdown_price(cfg)
    if td is not None:
        for xi, r in zip(x, order):
            v = td.get(r, np.nan)
            if np.isnan(v) or v <= 0:               # zero top-down (e.g. BR, NO, RU, TR): not drawn
                continue
            ax.plot([xi, xi], [v, cen[r]], color=TD, lw=0.8, alpha=0.30, zorder=1)
            ax.plot(xi, v, "D", color=TD, ms=8, mfc="white", mec=TD, mew=1.7, zorder=6)
    ax.set_xticks(x); ax.set_xticklabels(order)
    for lbl in ax.get_xticklabels():
        if lbl.get_text() in ("EU27", "CN"):
            lbl.set_fontweight("bold")
    ax.set_ylabel("Solar electricity price [EUR/kWh]")
    handles = [
        Line2D([], [], marker="o", color="w", markerfacecolor=HYB, markersize=7, label=LBL_CENTRAL),
        Line2D([], [], color=ENV, lw=4.5, alpha=0.6, label=LBL_ENVELOPE),
        Line2D([], [], marker="D", ls="", color=TD, mfc="white", mec=TD, mew=1.6, ms=7, label=LBL_TOPDOWN),
        Patch(color="0.78", alpha=0.6, label="IRENA 2024 LCOE 5th–95th"),
        Line2D([], [], color="0.25", lw=2, label="IRENA weighted avg."),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.08),
              ncol=5, framealpha=0.92, columnspacing=1.2, handletextpad=0.5)
    ax.set_ylim(0, None)
    fig.tight_layout()
    return fig, _save(fig, outdir, "fig_prices")


def make_all(sens_dir="outputs/sensitivity", outdir="outputs/figures"):
    """Generate every manuscript figure from the sensitivity export. Each figure is
    independent: one whose required input is missing is skipped with a message rather
    than aborting the rest. Figures are written as PNG (200 dpi) and TIFF (600 dpi)
    under their content names; ``make_figures.py`` additionally saves them under the
    paper figure numbers (Figure2 … Figure9).

    Inputs required beyond the basic export (``run_and_export``):
    - the footprint breakdown needs the heavy export (``f_dis_solar.parquet``);
    - the supply-chain impact-linkage figure needs ``onestep_*.parquet``;
    - the by-origin panel of the reconfiguration figure needs ``fc_ex_*.parquet``.
    Run ``export.run_and_export(..., heavy=True)`` plus ``export.write_onestep_data``
    and ``export.write_decomposition_data`` to produce all of them.
    """
    jobs = [
        ("footprint validation",         lambda: fig1(sens_dir, outdir, scenario="baseline")),
        ("footprint breakdown",          lambda: fig_breakdown(sens_dir, outdir, scenario="baseline")),
        ("supply-chain impact linkages", lambda: fig_onestep(sens_dir, outdir, scenario="baseline")),
        ("producer prices",              lambda: fig_prices(sens_dir, outdir, scenario="baseline")),
        ("supply-chain reconfiguration", lambda: fig_stages(sens_dir, outdir)),
        ("value added + employment",     lambda: fig_va_employment(sens_dir, outdir)),
        ("sensitivity + upstream scan",  lambda: fig_sensitivity(sens_dir, outdir)),
    ]
    paths = []
    for desc, fn in jobs:
        try:
            _, p = fn()
            paths.append(p)
        except (FileNotFoundError, KeyError, IndexError, ValueError) as e:
            print(f"{desc} skipped: {type(e).__name__}: {e}")
    return paths
