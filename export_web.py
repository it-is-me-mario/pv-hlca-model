"""Export the manuscript results as web-friendly JSON for the eNextGen interactive
dashboard (https://www.enextgen.it/analyses/...).

Standalone on purpose: it does NOT import ``pv_hlca``/``mario`` (the ``pv_hlca`` conda
env has pandas+pyarrow+openpyxl but no ``mario``). The few constants it needs are
copied from ``src/pv_hlca/figures.py`` and kept in sync with it; the selections
(central case, NZIA-vs-baseline_2030 reshoring effect, one-step Map3 stacks) reproduce
exactly what the matplotlib figures plot, so the JSON matches the paper numbers.

Emits four datasets used by the dashboard:
  footprints.json     -> Fig.2  per-region footprint (central + sensitivity envelope + top-down)
  scenarios.json      -> scoped EU PV emissions by scenario
  onestep.json        -> Fig.4  supply-chain impact linkages (per-stage Map3 stacks, EU27/CN)
  va_employment.json  -> Fig.7  value-added & employment effect of the NZIA (vs baseline_2030)
  meta.json           -> palette + labels shared by every chart

    /opt/anaconda3/envs/pv_hlca/bin/python export_web.py [TARGET_DIR]

TARGET_DIR defaults to the site's static/data/pv-hlca/.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent
SENS = REPO / "outputs" / "sensitivity"
DATA = REPO / "data"
CONFIG = REPO / "config"

#: readable names for the EXIOBASE rest-of-world aggregates (yaml maps them to themselves)
ROW_REGION_NAMES = {"WA": "Rest of Asia-Pacific", "WE": "Rest of Europe",
                    "WF": "Rest of Africa", "WL": "Rest of America", "WM": "Rest of Middle East"}


def region_names() -> dict:
    """Region code -> full country/region name (config/mappings.yaml + readable RoW names)."""
    m = dict(yaml.safe_load((CONFIG / "mappings.yaml").read_text())["region_code_to_full_name"])
    m.update(ROW_REGION_NAMES)
    m["EU27"] = "European Union"
    return m
DEFAULT_TARGET = Path(
    "/Users/lorenzorinaldi/Documents/GitHub/eNextHub/enextgen-site/static/data/pv-hlca"
)

# --------------------------------------------------------------------------- #
# constants mirrored from src/pv_hlca/figures.py (keep in sync)
# --------------------------------------------------------------------------- #
CENTRAL = {"capacity_factor": "OWID", "electricity_mix": "WEO_STEPS",
           "module_efficiency": 0.195, "upstream_reshoring": np.nan,
           "degradation_rate": 0.0, "lci_variant": "IEA"}
IPCC_BAND = (20, 80)
NREL_BAND = (39, 49)
SELECTION = ["AU", "BR", "CN", "EU27", "GB", "IN", "JP", "KR", "MX", "TR", "US"]
TJ_TO_GKWH = 3.6

# English fallback labels (the dashboard localises these in dashboard.js).
SCENARIO_LABELS = {
    "baseline": "Today's supply chain (2024)",
    "baseline_2030": "Today's chain on the 2030 grid",
    "NZIA": "Europe makes 40% (NZIA)",
    "domestic": "Fully made in Europe",
}

CATEGORY_COLORS = {
    "Direct emissions": "#1a1a1a",
    "PV supply chain": "#8CBBFD",
    "PV auxiliaries": "#3F8EFC",
    "PV end of life management": "#02429B",
    "Electricity": "#F8D35E",
    "Fuels": "#D96940",
    "Glass": "#BF9FC2",
    "Metals and Machinery": "#79C2D6", "Metals and Machineries": "#79C2D6",
    "Chemicals and plastics": "#67BA6F", "Plastics and Chemicals": "#67BA6F",
    "Transport": "#69456C",
    "Other": "#d0d0d0",
    "Solar PP, direct": "#555555",
}

# one-step (Fig.4) -------------------------------------------------------------
_ONESTEP_ACTS = ["Metallurgical Grade silicon production", "Solar Grade silicon production",
                 "Ingot production", "Wafer production", "Cells production",
                 "PV modules production", "Solar Power Plant"]
_ONESTEP_LABELS = ["MG-Si", "SG-Si", "Ingot", "Wafer", "Cells", "Modules", "Electricity"]
_ONESTEP_LINK = [("PV modules", "PV modules production", "Solar Power Plant"),
                 ("Cells", "Cells production", "PV modules production"),
                 ("Wafer", "Wafer production", "Cells production"),
                 ("Ingot", "Ingot production", "Wafer production"),
                 ("Solar Grade silicon", "Solar Grade silicon production", "Ingot production"),
                 ("Metallurgical Grade silicon", "Metallurgical Grade silicon production",
                  "Solar Grade silicon production")]
_ONESTEP_ROW_ORDER = ["PV supply chain", "PV auxiliaries", "PV end of life management",
                      "Chemicals and plastics", "Electricity", "Fuels", "Glass",
                      "Metals and Machinery", "Transport", "Other", "Direct emissions"]

# value-added / employment (Fig.7) --------------------------------------------
_VA_FACTORS = ["Compensation of employees",
               "Operating surplus: Consumption of fixed capital",
               "Taxes, subsidies and net surplus"]
_VA_SHORT = {"Compensation of employees": "Wages",
             "Operating surplus: Consumption of fixed capital": "Fixed capital",
             "Taxes, subsidies and net surplus": "Taxes & surplus"}
_VA_COLORS = {"Wages": "#02429B", "Fixed capital": "#79C2D6", "Taxes & surplus": "#F8D35E"}


def _is_central(df: pd.DataFrame, exclude: str | None = None) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for k, v in CENTRAL.items():
        if k == exclude:
            continue
        col = df[k]
        mask &= col.isna() if (isinstance(v, float) and np.isnan(v)) else (col == v)
    return mask


def _round(x, n=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


# --------------------------------------------------------------------------- #
def export_footprints() -> dict:
    """Fig.2: per-region footprint — central case + full sensitivity envelope + top-down."""
    df = pd.read_csv(SENS / "footprints.csv")
    df = df[df["scenario"].isin(SCENARIO_LABELS)]
    try:
        td = pd.read_csv(SENS / "topdown.csv").set_index("region")["footprint_gkwh"]
    except FileNotFoundError:
        td = pd.Series(dtype=float)

    out = {}
    for scn in SCENARIO_LABELS:
        sub = df[df["scenario"] == scn]
        cen = sub[_is_central(sub)].set_index("region")["footprint_gkwh"]
        env = sub.groupby("region")["footprint_gkwh"].agg(["min", "max"])
        rows = []
        for r in cen.sort_values(ascending=False).index:
            rows.append({
                "region": r,
                "central": _round(cen[r]),
                "min": _round(env.loc[r, "min"]),
                "max": _round(env.loc[r, "max"]),
                "topdown": _round(td.get(r, np.nan)),
                "selected": r in SELECTION,
            })
        out[scn] = rows
    return {
        "unit": "gCO₂eq/kWh",
        "bands": {"IPCC median range": list(IPCC_BAND), "NREL harmonized range": list(NREL_BAND)},
        "selection": SELECTION,
        "scenarios": out,
    }


def export_scenarios() -> dict:
    """Scoped EU PV emissions, by scenario (footprint, total Mt, global Gt)."""
    df = pd.read_csv(SENS / "scoped_eu_pv_emissions.csv")
    metrics = {
        "footprint_gkwh": {"label": "EU PV footprint", "unit": "gCO₂eq/kWh"},
        "gen_TWh": {"label": "EU PV generation", "unit": "TWh"},
    }
    rows = []
    for _, r in df.iterrows():
        scn = r["scenario"]
        if scn not in SCENARIO_LABELS:
            continue
        rec = {"scenario": scn}
        for m in metrics:
            rec[m] = _round(r.get(m), 3)
        rows.append(rec)
    # keep manuscript ordering
    order = {s: i for i, s in enumerate(SCENARIO_LABELS)}
    rows.sort(key=lambda x: order.get(x["scenario"], 99))
    return {"metrics": metrics, "rows": rows}


def export_onestep() -> dict:
    """Fig.4: one-step supply-chain impact linkages, per stage, EU27 & CN, per scenario."""
    act_map = (pd.read_excel(DATA / "Mapping_act_and_com.xlsx", sheet_name="Mapping_activities")
               .set_index("Activity_from")["Map3"].to_dict())
    com_map = (pd.read_excel(DATA / "Mapping_act_and_com.xlsx", sheet_name="Mapping_commodities")
               .set_index("Commodity_from")["Map3"].to_dict())

    out = {}
    for scn in SCENARIO_LABELS:
        f = SENS / f"onestep_{scn}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        per_region = {}
        for region in sorted(df["to_region"].unique()):
            d = df[df["to_region"] == region].copy()
            d["cat"] = [act_map.get(it) if lv == "Activity" else com_map.get(it)
                        for lv, it in zip(d["from_level"], d["from_item"])]
            d["cat"] = d["cat"].replace("Machinery and equipment", "Metals and Machinery")
            d["cat"] = d["cat"].where(d["cat"].isin(_ONESTEP_ROW_ORDER), "Other")
            piv = (d.groupby(["cat", "to_activity"])["ghg"].sum().unstack("to_activity")
                   .reindex(index=_ONESTEP_ROW_ORDER, columns=_ONESTEP_ACTS))
            col_tot = piv.sum(axis=0)
            pct = piv.div(col_tot, axis=1) * 100
            absol = col_tot * TJ_TO_GKWH

            # inherited (linkage) % of each stage coming from the upstream PV commodity
            perc_raw = {}
            for com, _left, act in _ONESTEP_LINK:
                tot = col_tot.get(act, np.nan)
                if not (tot and np.isfinite(tot)):
                    continue
                val = d[(d["to_activity"] == act) & (d["from_level"] == "Commodity")
                        & (d["from_item"] == com)]["ghg"].sum()
                perc_raw[act] = val / tot * 100

            # Footprint of 1 kWh of solar electricity, cascaded down the chain: each stage's
            # per-kWh contribution = the downstream stage's value times the inherited share.
            # So the "Modules" bar equals the PV-supply-chain part of "Electricity", the
            # "Cells" bar the PV-supply-chain part of "Modules", and so on (Fig.4 cascade).
            per_kwh = {}
            prev = None
            for act in _ONESTEP_ACTS[::-1]:          # Solar Power Plant -> ... -> MG-Si
                if prev is None:
                    per_kwh[act] = float(absol.get(act, np.nan))
                else:
                    p, base = perc_raw.get(prev), per_kwh.get(prev)
                    per_kwh[act] = (base * p / 100.0) if (p is not None and base is not None
                                                          and np.isfinite(base)) else None
                prev = act

            stages = []
            for act, lbl in zip(_ONESTEP_ACTS, _ONESTEP_LABELS):
                shares = {cat: _round(pct.loc[cat, act], 1) for cat in _ONESTEP_ROW_ORDER
                          if pd.notna(pct.loc[cat, act]) and pct.loc[cat, act] > 0}
                stages.append({
                    "activity": act, "label": lbl,
                    "total_gkwh": _round(per_kwh.get(act), 3),       # per kWh of electricity
                    "footprint_per_product_gkwh": _round(absol.get(act, np.nan), 3),
                    "inherited_pct": _round(perc_raw.get(act), 1),
                    "shares": shares,
                })
            per_region[region] = stages
        out[scn] = per_region
    return {
        "categories": _ONESTEP_ROW_ORDER,
        "stage_order": _ONESTEP_LABELS,
        "scenarios": out,
    }


def export_va_employment() -> dict:
    """Fig.7: value-added (by factor) and employment (by sector) effect of the NZIA,
    isolated as NZIA minus baseline_2030 (both on the 2030 grid)."""
    ref, scen = "baseline_2030", "NZIA"
    base = dict(capacity_factor="OWID", electricity_mix="WEO_STEPS",
                module_efficiency=0.195, degradation_rate=0.0, lci_variant="IEA")

    def _sel(df, scn):
        m = pd.Series(True, index=df.index)
        for k, v in base.items():
            m &= df[k] == v
        return df[m & (df["scenario"] == scn) & (df["upstream_reshoring"].isna())]

    # --- value added by factor (M€ -> b€) ---
    va = pd.read_csv(SENS / "value_added.csv")
    va = va[va["factor"].isin(_VA_FACTORS)].copy()
    va["factor"] = va["factor"].map(_VA_SHORT)
    vb = _sel(va, ref).groupby(["region", "factor"])["value_added"].sum()
    vn = _sel(va, scen).groupby(["region", "factor"])["value_added"].sum()
    dva = (vn - vb).unstack("factor").fillna(0)
    va_base = _sel(va, ref).groupby("region")["value_added"].sum()
    va_pct = (dva.sum(axis=1) / va_base * 100)

    # --- employment by sector (Map4) ---
    mp = pd.read_excel(DATA / "Mapping_activities.xlsx").set_index("Activity_from")["Map4"]
    emp = pd.read_csv(SENS / "employment.csv")
    emp["sector"] = emp["activity"].map(mp).fillna("Other")
    emp["sector"] = emp["sector"].replace({"Solar PP, direct": "PV supply chain"})
    eb = _sel(emp, ref).groupby(["region", "sector"])["employment"].sum()
    en = _sel(emp, scen).groupby(["region", "sector"])["employment"].sum()
    demp = (en - eb).unstack("sector").fillna(0)
    emp_base = _sel(emp, ref).groupby("region")["employment"].sum()
    emp_pct = (demp.sum(axis=1) / emp_base.replace(0, np.nan) * 100)

    # regions with a non-negligible VA change, ordered by total VA delta (as Fig.7)
    totals = dva.sum(axis=1)
    regions = list(totals[totals.abs() > 40.0].sort_values(ascending=False).index)

    va_factors = [f for f in _VA_SHORT.values() if f in dva.columns]
    emp_sectors = [s for s in CATEGORY_COLORS if s in demp.columns] + \
                  [s for s in demp.columns if s not in CATEGORY_COLORS]

    va_rows, emp_rows = [], []
    for r in regions:
        va_rows.append({
            "region": r,
            "pct": _round(va_pct.get(r), 2),
            **{f: _round(dva.loc[r, f] / 1000.0, 3) for f in va_factors},  # b€
        })
        emp_rows.append({
            "region": r,
            "pct": _round(emp_pct.get(r), 3),
            **{s: _round(demp.loc[r, s], 2) for s in emp_sectors},  # 1000 persons
        })
    return {
        "ref": ref, "scen": scen,
        "value_added": {"unit": "b€", "factors": va_factors, "colors": _VA_COLORS, "rows": va_rows},
        "employment": {"unit": "1000 persons", "sectors": emp_sectors, "rows": emp_rows},
    }


def _mapping_tables() -> tuple:
    """The sector/commodity -> category groupings behind the figure legends, exactly as
    applied in the figures (one-step Map3 categories; employment Map4 sectors)."""
    acts = pd.read_excel(DATA / "Mapping_act_and_com.xlsx", sheet_name="Mapping_activities")[["Activity_from", "Map3"]]
    coms = pd.read_excel(DATA / "Mapping_act_and_com.xlsx", sheet_name="Mapping_commodities")[["Commodity_from", "Map3"]]
    acts = acts.rename(columns={"Activity_from": "item"}).assign(item_type="Activity")
    coms = coms.rename(columns={"Commodity_from": "item"}).assign(item_type="Commodity")
    cat = pd.concat([acts, coms], ignore_index=True)
    cat["legend_category"] = (cat["Map3"].replace("Machinery and equipment", "Metals and Machinery")
                              .where(lambda s: s.isin(_ONESTEP_ROW_ORDER), "Other"))
    cat = cat[["legend_category", "item_type", "item"]].sort_values(["legend_category", "item_type", "item"])

    emp = pd.read_excel(DATA / "Mapping_activities.xlsx")[["Activity_from", "Map4"]].copy()
    emp["Map4"] = emp["Map4"].replace({"Solar PP, direct": "PV supply chain"})
    emp = emp.rename(columns={"Activity_from": "activity", "Map4": "employment_sector"})
    emp = emp[["employment_sector", "activity"]].sort_values(["employment_sector", "activity"])
    return cat, emp


def build_excel(target: Path, footprints: dict, onestep: dict, va: dict):
    """One workbook with the raw data behind every figure + the legend mappings."""
    # Fig.2 footprints
    fp_rows = []
    for scn, lst in footprints["scenarios"].items():
        for r in lst:
            fp_rows.append({"scenario": scn, "scenario_label": SCENARIO_LABELS.get(scn, scn),
                            "region": r["region"], "central_gkwh": r["central"],
                            "min_gkwh": r["min"], "max_gkwh": r["max"], "topdown_gkwh": r["topdown"]})
    df_fp = pd.DataFrame(fp_rows)

    # Fig.4 supply-chain steps
    os_rows = []
    for scn, regs in onestep["scenarios"].items():
        for reg, stages in regs.items():
            for s in stages:
                for cat, pctv in s["shares"].items():
                    os_rows.append({"scenario": scn, "region": reg, "step": s["label"],
                                    "category": cat, "share_pct": pctv,
                                    "step_carbon_footprint_per_kwh_gkwh": s["total_gkwh"]})
    df_os = pd.DataFrame(os_rows)

    # Fig.3 scenarios (full scoped table)
    df_scn = pd.read_csv(SENS / "scoped_eu_pv_emissions.csv")
    df_scn = df_scn[df_scn["scenario"].isin(SCENARIO_LABELS)].copy()
    df_scn.insert(1, "scenario_label", df_scn["scenario"].map(SCENARIO_LABELS))

    # Fig.7 value added & employment
    df_va = pd.DataFrame(va["value_added"]["rows"])
    df_emp = pd.DataFrame(va["employment"]["rows"])

    cat_map, emp_map = _mapping_tables()

    readme = pd.DataFrame([
        ("source", "Rinaldi et al. (under review) — hybrid LCA of photovoltaic electricity"),
        ("1_footprints", "Fig.2 — PV electricity carbon footprint by country: central case, sensitivity range (min/max), Top-Down [gCO2eq/kWh]"),
        ("2_supply_chain_steps", "Fig.4 — per-step composition (share %) and per-kWh carbon footprint cascaded down the chain"),
        ("3_scenarios", "Fig.3 — scoped EU PV footprint, generation and emissions by scenario"),
        ("4_value_added", "Fig.7 — value-added change by factor [b€], NZIA vs Baseline-2030"),
        ("5_employment", "Fig.7 — employment change by sector [1000 persons], NZIA vs Baseline-2030"),
        ("map_categories", "Legend mapping for Fig.4: which activities/commodities make up each category"),
        ("map_employment_sectors", "Legend mapping for Fig.7 employment: activity -> sector"),
    ], columns=["sheet", "description"])

    xlsx = target / "pv-hlca-data.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        readme.to_excel(xw, sheet_name="README", index=False)
        df_fp.to_excel(xw, sheet_name="1_footprints", index=False)
        df_os.to_excel(xw, sheet_name="2_supply_chain_steps", index=False)
        df_scn.to_excel(xw, sheet_name="3_scenarios", index=False)
        df_va.to_excel(xw, sheet_name="4_value_added", index=False)
        df_emp.to_excel(xw, sheet_name="5_employment", index=False)
        cat_map.to_excel(xw, sheet_name="map_categories", index=False)
        emp_map.to_excel(xw, sheet_name="map_employment_sectors", index=False)
    print(f"wrote pv-hlca-data.xlsx  ({xlsx.stat().st_size/1024:.1f} kB)")


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    target.mkdir(parents=True, exist_ok=True)

    footprints, scenarios, onestep, va = (export_footprints(), export_scenarios(),
                                          export_onestep(), export_va_employment())
    datasets = {
        "footprints.json": footprints,
        "scenarios.json": scenarios,
        "onestep.json": onestep,
        "va_employment.json": va,
        "meta.json": {
            "category_colors": CATEGORY_COLORS,
            "scenario_labels": SCENARIO_LABELS,
            "region_names": region_names(),
            "source": "Rinaldi et al. (under review)",
        },
    }
    for name, obj in datasets.items():
        (target / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1))
        print(f"wrote {name}  ({(target / name).stat().st_size/1024:.1f} kB)")
    build_excel(target, footprints, onestep, va)
    print(f"-> {target}")


if __name__ == "__main__":
    main()
