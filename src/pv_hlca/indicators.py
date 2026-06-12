"""Indicators: CO2eq footprints, prices, production/value-added/emissions, and the
disaggregated footprint / price of solar electricity.

Formulas (validated against the reference results):
  - headline footprint = CO2eq of the 'f' multiplier for Activity 'Solar Power Plant',
    x 3.6 -> gCO2eq/kWh.
  - f_dis_solar = diag(e_CO2eq) . w   (full upstream attribution), Solar columns.
  - p_dis_solar = diag(v) . w, Solar columns.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

TJ_TO_GKWH = 3.6


def _gwp(cfg) -> dict:
    return cfg["parameters"]["gwp_factors"]


def co2eq_series(matrix: pd.DataFrame, cfg) -> pd.Series:
    """Sum satellite rows of a footprint/emission matrix with GWP factors."""
    out = None
    for gas, fac in _gwp(cfg).items():
        mask = matrix.index.to_series().str.contains(gas, case=False, na=False)
        if mask.any():
            part = matrix.loc[mask].iloc[0].fillna(0) * fac
            out = part if out is None else out + part
    return out


def solar_footprint(db, cfg, scenario: str = "baseline", g_per_kwh: bool = True,
                    activity: str = "Solar Power Plant") -> pd.Series:
    """Per-region footprint of solar electricity for the given producing Activity
    (default the explicit 'Solar Power Plant'; pass the legacy/EXIOBASE PV activity
    for the top-down benchmark)."""
    f = db.query(matrices="f", scenarios=scenario)
    co2 = co2eq_series(f, cfg)
    idx = co2.index
    sel = (idx.get_level_values(2) == activity) & (idx.get_level_values(1) == "Activity")
    s = pd.Series({k[0]: float(v) for k, v in co2[sel].items()})
    return s * TJ_TO_GKWH if g_per_kwh else s


def f_dis_solar(db, cfg, scenario: str = "baseline") -> pd.Series:
    """Disaggregated CO2eq footprint of the Solar commodity: diag(e_CO2eq) . w,
    restricted to Solar commodity columns and Activity from-rows. Long form
    indexed by (Region_from, Activity, Region_to)."""
    e = db.query(matrices="e", scenarios=scenario)
    w = db.query(matrices="w", scenarios=scenario)
    edir = co2eq_series(e, cfg)
    cols = w.columns
    solar = cols[(cols.get_level_values(1) == "Commodity") & (cols.get_level_values(2) == "Solar")]
    sub = w[solar].multiply(edir.values, axis=0)
    sub = sub[sub.index.get_level_values(1) == "Activity"]
    sub.index = pd.MultiIndex.from_tuples([(r[0], r[2]) for r in sub.index],
                                          names=["Region_from", "Activity"])
    sub.columns = [c[0] for c in sub.columns]
    out = sub.stack()
    out.index = out.index.set_names(["Region_from", "Activity", "Region_to"])
    return out


def solar_price(db, cfg, scenario: str = "baseline", eur_per_kwh: bool = True) -> pd.Series:
    """Per-region price of solar electricity (Activity 'Solar Power Plant')."""
    p = db.query(matrices="p", scenarios=scenario)
    s = p.iloc[:, 0] if hasattr(p, "columns") else p
    idx = s.index
    sel = (idx.get_level_values(2) == "Solar Power Plant") & (idx.get_level_values(1) == "Activity")
    out = pd.Series({k[0]: float(v) for k, v in s[sel].items()})
    return out * TJ_TO_GKWH if eur_per_kwh else out


def value_added_by_factor(db, scenario: str = "baseline") -> pd.Series:
    """Total value added by (production factor, region), summed over activities."""
    V = db.query(matrices="V", scenarios=scenario)
    cols = V.columns
    keep = cols[cols.get_level_values(1) == "Activity"]
    m = V[keep]
    m.columns = m.columns.set_names(["Region", "Level", "Item"])
    by = m.T.groupby(level="Region").sum().T            # factor x region
    return by.stack().rename("value_added")             # (factor, region)


def employment_by_activity(db, scenario: str = "baseline") -> pd.Series:
    """Employment by (region, activity)."""
    E = db.query(matrices="E", scenarios=scenario)
    row = E.loc["Employment"] if "Employment" in E.index else None
    if row is None:
        return pd.Series(dtype=float)
    sel = row.index.get_level_values(1) == "Activity"
    r = row[sel]
    return pd.Series({(k[0], k[2]): float(v) for k, v in r.items()})


#: PV supply-chain commodities (the stages decomposed in the contribution figure)
PV_COMMODITIES = ["Solar", "PV modules", "Cells", "Wafer", "Ingot",
                  "Solar Grade silicon", "Metallurgical Grade silicon"]


def fc_ex_pv(db, scenario: str = "baseline", satellite: str = "GHG",
             threshold: float = 1e-9) -> pd.DataFrame:
    """Exploded commodity-side GHG footprint (MARIO ``fc_ex``) restricted to the PV
    supply-chain commodities, in tidy long form, dropping near-zero contributions.

    Columns: satellite, from_region, from_level, from_item (contributing activity),
    to_region, to_level, to_commodity (PV stage), ghg. This single table feeds the
    per-stage decomposition (by activity of origin) and the total footprint (sum)."""
    fc = db.fc_ex(satellite_accounts=satellite, scenario=scenario)
    pv = fc.columns[fc.columns.get_level_values(2).isin(PV_COMMODITIES)]
    sub = fc[pv]
    sub.index = sub.index.set_names(["satellite", "from_region", "from_level", "from_item"])
    sub.columns = sub.columns.set_names(["to_region", "to_level", "to_commodity"])
    long = (sub.stack(["to_region", "to_level", "to_commodity"], future_stack=True)
            .rename("ghg").reset_index())
    return long[long["ghg"].abs() > threshold].copy()


#: PV producing activities (the 7 stages), upstream -> downstream
PV_ACTIVITIES = ["Solar Power Plant", "PV modules production", "Cells production",
                 "Wafer production", "Ingot production",
                 "Solar Grade silicon production", "Metallurgical Grade silicon production"]


def onestep_decomp_pv(db, cfg, scenario: str = "baseline",
                      regions=("EU27", "CN"), threshold: float = 1e-12) -> pd.DataFrame:
    """One-step (first-tier) GHG decomposition of the PV producing activities, the
    data behind the thesis Fig.11 ("supply chain impact linkages"):

        D = diag(f_CO2eq) . z   +   diag(e_CO2eq)

    where f is the embodied GHG multiplier, e the direct GHG intensity and z the
    technical-coefficient (use) matrix. For each PV activity column the entries sum
    exactly to its footprint f_j (identity f = e + f.z), splitting the stage total
    into its own direct emissions (diag e) and the *full embodied* footprint of each
    first-tier input commodity (diag(f).z) — the six upstream PV commodities then
    collapse to a single "PV supply chain" category downstream.

    Contrast :func:`fc_ex_pv` (= diag(e).w), the FULL explosion to ultimate emitters.

    Returns tidy long form: scenario, to_region, to_activity, from_level, from_item,
    ghg. Columns restricted to ``regions``; contributions summed over the from-region.
    """
    f = co2eq_series(db.query(matrices="f", scenarios=scenario), cfg)
    e = co2eq_series(db.query(matrices="e", scenarios=scenario), cfg)
    z = db.query(matrices="z", scenarios=scenario)
    f = f.reindex(z.index).fillna(0.0)
    e = e.reindex(z.index).fillna(0.0)

    cols = z.columns
    sel = ((cols.get_level_values(1) == "Activity")
           & (cols.get_level_values(2).isin(PV_ACTIVITIES))
           & (cols.get_level_values(0).isin(regions)))
    D = z.loc[:, sel].multiply(f.values, axis=0)           # f_i * z_ij (commodity rows)
    flevel = D.index.get_level_values(1)
    fitem = D.index.get_level_values(2)

    rows = []
    for col in D.columns:
        to_region, _, to_act = col
        g = D[col].groupby([flevel, fitem]).sum()
        g = g[g.abs() > threshold]
        for (lvl, item), v in g.items():
            rows.append((scenario, to_region, to_act, lvl, item, float(v)))
        ev = float(e.get((to_region, "Activity", to_act), 0.0))   # diagonal direct
        if abs(ev) > threshold:
            rows.append((scenario, to_region, to_act, "Activity", to_act, ev))
    return pd.DataFrame(rows, columns=["scenario", "to_region", "to_activity",
                                       "from_level", "from_item", "ghg"])


def production_pv(db, scenario: str = "baseline") -> pd.Series:
    """Production X of the six PV commodities, per region."""
    X = db.query(matrices="X", scenarios=scenario)
    xs = X.iloc[:, 0] if hasattr(X, "columns") else X
    coms = ["PV modules", "Cells", "Wafer", "Ingot",
            "Solar Grade silicon", "Metallurgical Grade silicon"]
    sel = (xs.index.get_level_values(1) == "Commodity") & (xs.index.get_level_values(2).isin(coms))
    return pd.Series({(k[0], k[2]): float(v) for k, v in xs[sel].items()})


def eu_value_added(db, scenario: str = "baseline") -> float:
    """Total EU27 value added (sum of V over EU27 activities), M€."""
    V = db.query(matrices="V", scenarios=scenario)
    cols = V.columns
    eu = cols[(cols.get_level_values(0) == "EU27") & (cols.get_level_values(1) == "Activity")]
    return float(V[eu].values.sum())


def global_co2eq(db, cfg, scenario: str = "baseline") -> float:
    """Total global CO2eq emissions (E satellite rows with GWP)."""
    E = db.query(matrices="E", scenarios=scenario)
    tot = 0.0
    for gas, fac in _gwp(cfg).items():
        mask = E.index.to_series().str.contains(gas, case=False, na=False)
        if mask.any():
            tot += E.loc[mask].iloc[0].fillna(0).sum() * fac
    return float(tot)


# --------------------------------------------------------------------------- #
# top-down benchmark: solar PV footprint from the raw (un-augmented) EXIOBASE
# --------------------------------------------------------------------------- #
#: GHG satellites of the raw EXIOBASE hybrid SUT -> the model's GWP buckets
#: (matches the Satellite sheet of the aggregation workbook: fossil CO2 + CH4 + N2O,
#: 'air - Emiss' rows only; everything else is dropped as 'unused').
_TOPDOWN_GHG = {"Carbon dioxide, fossil (air - Emiss)": "Carbon dioxide",
                "CH4 (air - Emiss)": "CH4", "N2O (air - Emiss)": "N2O"}


def topdown_footprint(cfg, g_per_kwh: bool = True):
    """Top-down benchmark footprint of solar electricity, per region (gCO2eq/kWh).

    For now these are the published reference values
    (``reference/topdown_published.csv``), pending a clean re-derivation on the
    current base — the naive 'aggregate Solar activity' footprint is degenerate on
    this base (near-zero native Solar output -> exploding intensity), see
    :func:`topdown_footprint_enextsut`. Returns ``None`` if the file is absent.
    """
    from . import io
    p = io.repo_root() / "reference" / "topdown_published.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p).set_index("region")["footprint_gkwh"]
    return s if g_per_kwh else s / TJ_TO_GKWH


def topdown_price(cfg, eur_per_kwh: bool = True):
    """Top-down benchmark producer price of solar electricity, per region (EUR/kWh).

    Like :func:`topdown_footprint`, these are the published reference values
    (``reference/topdown_price_published.csv``, the legacy EXIOBASE 'Solar' activity
    price), since a clean re-derivation on the current base is degenerate (the
    aggregate 'Solar' has ~zero native output). Returns ``None`` if the file is absent.
    """
    from . import io
    p = io.repo_root() / "reference" / "topdown_price_published.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p).set_index("region")["price_eur_kwh"]
    return s if eur_per_kwh else s / TJ_TO_GKWH


def topdown_footprint_enextsut(cfg, g_per_kwh: bool = True):
    """Re-derivation attempt: footprint of the legacy aggregate 'Solar' activity of
    the base hybrid SUT, before the explicit PV supply chain. NOTE: currently
    degenerate (the aggregate 'Solar' has ~zero native output on this base), so it
    does not reproduce the published top-down — kept for debugging."""
    from . import io
    db = io.parse_base_db(cfg)
    io.aggregate_db(db, cfg)
    return solar_footprint(db, cfg, "baseline", g_per_kwh=g_per_kwh, activity="Solar")


def topdown_footprint_exiobase_raw(cfg, g_per_kwh: bool = True):
    """Alternative top-down from the *raw* EXIOBASE 3.3.18 hybrid SUT (2011 vintage,
    'Production of electricity by solar photovoltaic'), as an external benchmark.

    Region and GHG-satellite levels are aggregated in memory (an aggregation dict
    built on the raw EXIOBASE index, so it never references the model's added
    activities); Activity/Commodity stay native. Returns ``None`` if the raw
    EXIOBASE path (``data.exiobase_raw``) is not configured/available. Note the
    2011 vintage gives systematically different values than the eNextSUT base.
    """
    import mario
    path = cfg["data"].get("exiobase_raw")
    if not path or not Path(path).exists():
        return None
    db = mario.parse_exiobase(table="SUT", unit="Hybrid", path=str(path), extensions="all")
    reg = pd.read_excel(cfg["data"]["aggregation"], sheet_name="Region", index_col=0)
    reg.columns = ["Aggregation"]
    reg = reg.reindex(db.get_index("Region"))
    sat = pd.DataFrame(
        {"Aggregation": [_TOPDOWN_GHG.get(s, "unused") for s in db.get_index("Satellite account")]},
        index=db.get_index("Satellite account"))
    db.aggregate(io={"Region": reg, "Satellite account": sat},
                 levels=["Region", "Satellite account"],
                 ignore_nan=True, zero_output_epsilon=None, drop=["unused"])
    act = db.search("Activity", "photovoltaic")[0]
    return solar_footprint(db, cfg, "baseline", g_per_kwh=g_per_kwh, activity=act)
