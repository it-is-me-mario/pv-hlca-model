"""Scenario construction: baseline trade structure, domestic, NZIA, baseline_2030.

All trade/technology shocks act on Commodity -> Activity flows, i.e. the ``u``
(use) block in mario 1.0.0 (``z`` is derived and read-only for recompute). The
import-structure logic operates on ``u`` (rather than ``z``) and is validated
against the reference results.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

PV_IMPORT_COMMODITIES = [
    "PV modules", "Cells", "Wafer", "Ingot",
    "Solar Grade silicon", "Metallurgical Grade silicon",
]


# --------------------------------------------------------------------------- #
# import structure
# --------------------------------------------------------------------------- #
def _import_matrix(rows: pd.DataFrame) -> pd.DataFrame:
    """Build the importer x exporter share matrix for one commodity.

    Negative shares (self-supply) become ``1 - |share|``; the (importer, exporter)
    pairs are pivoted as in the reference implementation.
    """
    processed = []
    for _, r in rows.iterrows():
        share = r["share"]
        share = (1 - abs(share)) if share < 0 else share
        # the first element is the exporter, the second the importer
        processed.append((r["importer"], r["exporter"], share))
    df = pd.DataFrame(processed, columns=["Exporter", "Importer", "Share"])
    df = df.drop_duplicates(subset=["Exporter", "Importer"])
    return df.pivot(index="Importer", columns="Exporter", values="Share").fillna(0)


def apply_import_structure(u: pd.DataFrame, commodity: str, rows: pd.DataFrame,
                           regions: list) -> pd.DataFrame:
    """Redistribute the use of ``commodity`` across activities by import shares.

    Acts on the ``u`` block (rows = (region, Commodity, item); columns =
    (region, Activity, item)).
    """
    import_matrix = _import_matrix(rows)
    activity_cols = u.columns[u.columns.get_level_values(1) == "Activity"]

    for imp_region in regions:
        row = (imp_region, "Commodity", commodity)
        if row not in u.index:
            continue
        # Columns are independent. Transfer the entire row at once while keeping
        # the historical region order (including its sequential redistribution).
        # This avoids hundreds of thousands of scalar DataFrame lookups per run.
        values = u.loc[row, activity_cols].to_numpy(copy=True)
        if not np.any(values):
            continue
        u.loc[row, activity_cols] = 0.0
        if imp_region in import_matrix.index:
            for exp_region in import_matrix.columns:
                share = import_matrix.loc[imp_region, exp_region]
                if share > 0:
                    new_row = (exp_region, "Commodity", commodity)
                    if new_row in u.index:
                        u.loc[new_row, activity_cols] += values * share
    return u


#: upstream PV commodities (everything below module assembly)
UPSTREAM_COMMODITIES = ["Cells", "Wafer", "Ingot",
                        "Solar Grade silicon", "Metallurgical Grade silicon"]


def _override_eu_upstream(rows: pd.DataFrame, commodity: str, domestic_share: float) -> pd.DataFrame:
    """Rewrite EU27's import structure for an upstream commodity to a target EU
    domestic share (self-supply), rescaling its external sourcing to
    (1 - domestic_share) proportionally.

    NB: in import_structure.csv the 'importer' column holds the *exporting*
    region and 'exporter' the *importing* one — ``_import_matrix`` swaps them
    when pivoting — so EU27-as-importer rows are those with exporter == 'EU27'.
    """
    eu = rows[rows["exporter"] == "EU27"]            # EU27 as importing region
    other = rows[rows["exporter"] != "EU27"]
    sourcing = eu[eu["importer"] != "EU27"]          # EU27 buying from abroad
    src_total = sourcing["share"].sum()
    # positive self share: equivalent to the CSV's negative encoding for any
    # domestic_share in [0, 1], and well-defined at exactly 1.0 (where -(1-ds)
    # would be -0.0 and fail the `share < 0` self test in _import_matrix)
    new = [{"scenario": "NZIA", "commodity": commodity, "importer": "EU27",
            "exporter": "EU27", "share": domestic_share}]
    if src_total > 0:
        for _, r in sourcing.iterrows():
            new.append({"scenario": "NZIA", "commodity": commodity,
                        "importer": r["importer"], "exporter": "EU27",
                        "share": r["share"] / src_total * (1.0 - domestic_share)})
    return pd.concat([other, pd.DataFrame(new)], ignore_index=True)


def _apply_imports_to_scenario(db, cfg, scenario: str, struct_scenario: str,
                               upstream_reshoring: float | None = None) -> pd.DataFrame:
    """Apply the import_structure.csv rows for ``struct_scenario`` to ``scenario``'s u.

    If ``upstream_reshoring`` is given, EU27's domestic share of the upstream PV
    commodities is overridden to that value (upstream reshoring sensitivity).
    """
    table = pd.read_csv(cfg["_import_structure_csv"])
    table = table[table["scenario"] == struct_scenario]
    regions = list(db.get_index("Region"))
    u = db.query(matrices="u", scenarios=scenario).copy()
    for commodity in PV_IMPORT_COMMODITIES:
        rows = table[table["commodity"] == commodity]
        if upstream_reshoring is not None and commodity in UPSTREAM_COMMODITIES:
            rows = _override_eu_upstream(rows, commodity, upstream_reshoring)
        if len(rows):
            u = apply_import_structure(u, commodity, rows, regions)
    return u


# --------------------------------------------------------------------------- #
# scenario builders
# --------------------------------------------------------------------------- #
def build_baseline_trade(db, cfg) -> None:
    """Apply the real (China-dominated) import structure to the baseline u-block."""
    u = _apply_imports_to_scenario(db, cfg, "baseline", "baseline")
    db.update_scenarios(scenario="baseline", u=u)
    db.reset_to_coefficients(scenario="baseline")


def apply_nzia_shocks(db, cfg, upstream_reshoring: float | None = None, *, scenario="NZIA") -> None:
    """Apply the NZIA import structure + EU transport decrease and construction
    increase to an existing 'NZIA' scenario (cloned earlier from the pre-import
    baseline). ``upstream_reshoring`` optionally forces EU27's domestic
    share of the upstream PV commodities."""
    u = _apply_imports_to_scenario(db, cfg, scenario, "NZIA",
                                   upstream_reshoring=upstream_reshoring)
    assumptions = cfg["scenario_2030"].get("nzia", {})
    # oceanic transport decrease (x0.6) for EU27 PV production activities
    sea = ("EU27", "Commodity", "Sea and coastal water transportation services")
    constr = ("EU27", "Commodity", "Construction work (45)")
    for com in PV_IMPORT_COMMODITIES:
        act = ("EU27", "Activity", f"{com} production")
        if sea in u.index and act in u.columns:
            u.loc[sea, act] *= assumptions.get("sea_transport_multiplier", 0.6)
    # construction-work increase for EU27 module/cell/wafer plants (M€/m2)
    construction = assumptions.get("construction_coefficients", {
        "PV modules production": 0.00001,
        "Cells production": 0.00002,
        "Wafer production": 0.000025,
    })
    for act_item, value in construction.items():
        act = ("EU27", "Activity", act_item)
        if constr in u.index and act in u.columns:
            u.loc[constr, act] = value
    db.update_scenarios(scenario=scenario, u=u)
    db.reset_to_coefficients(scenario=scenario)


def _project_region_grid_2030(Yc, u, region: str, target: dict, const: float) -> None:
    """In place: rescale one region's electricity mix (use-block u + final demand Yc)
    to the 2030 ``target`` shares. Generalisation of the EU27 grid-projection logic.

    ``const`` is the absolute household electricity-demand increment (TJ) added on top
    of the mix rotation (which is demand-neutral). Pass ``const=0.0`` to project the
    2030 mix only, leaving the region's demand level untouched."""
    house = [c for c in Yc.columns if c[0] == region
             and c[2] == "Final consumption expenditure by households"]
    cons = [c for c in Yc.columns if c[0] == region]
    acts = [c for c in u.columns if c[0] == region]
    sources = list(target.keys())
    gen = {}
    for s in sources:
        row = (region, "Commodity", s)
        gen[s] = float(Yc.loc[row, house].values.sum()) if row in Yc.index else 0.0
    total = sum(gen.values())
    cur = {s: (gen[s] / total if total else 0.0) for s in sources}
    mult = {s: (target[s] / cur[s] if cur[s] > 0 else 0.0) for s in sources}
    for s in sources:
        f = mult[s]
        if not (np.isfinite(f) and f > 0):
            continue
        row = (region, "Commodity", s)
        if row in Yc.index:
            Yc.loc[row, cons] *= f
            Yc.loc[row, house] += const * target[s]
        if row in u.index:
            u.loc[row, acts] *= f


def build_2030(db, cfg, mix_source: str = "WEO_STEPS") -> None:
    """baseline_2030: clone baseline, then project the 2030 electricity mix for every
    region defined in the chosen ``mix_source`` (e.g. EU27 and CN under WEO_STEPS).
    Applied to baseline_2030 AND NZIA (both become 2030 scenarios).

    The 2030 *mix* is rotated for every projected region (demand-neutral), but the
    absolute demand-growth increment is EU-calibrated (~+17% of EU electricity demand)
    and therefore applied to the EU27 only; other regions (e.g. CN) keep their 2024
    demand level while their grid is decarbonised to the 2030 mix."""
    db.clone_scenario(scenario="baseline", name="baseline_2030")
    for scen in ["baseline_2030", "NZIA"]:
        apply_paper_2030(db, cfg, scen, mix_source)


def apply_paper_2030(db, cfg, scenario, mix_source="WEO_STEPS"):
    """Apply the published grid/demand prescription to one existing scenario.

    Kept separate from custom mix rotation so historical presets retain their
    original numerical prescription. See docs/scenarios.md for the distinction.
    """
    table = cfg["scenario_2030"]["electricity_mix_2030"][mix_source]
    regions_mix = {k: v for k, v in table.items() if not k.startswith("_")}
    const = float(cfg["scenario_2030"].get("household_demand_constant", 460 * 3600))
    demand_region = cfg["scenario_2030"].get("demand_growth_region", "EU27")
    Yc = db.query(matrices="Yc", scenarios=scenario).copy()
    u = db.query(matrices="u", scenarios=scenario).copy()
    for region, target in regions_mix.items():
        _project_region_grid_2030(Yc, u, region, target,
                                  const if region == demand_region else 0.0)
    db.update_scenarios(scenario=scenario, Yc=Yc, u=u)
    db.reset_to_coefficients(scenario=scenario)


def build_all_scenarios(db, cfg, mix_source: str = "WEO_STEPS",
                        upstream_reshoring: float | None = None) -> None:
    """Full scenario set on a hybridised baseline DB. Order:
    domestic and NZIA are cloned from the PRE-import baseline; then the baseline
    gets the real import structure; then NZIA gets its reshoring shocks; finally
    baseline_2030 is cloned from the post-import baseline and the 2030 mix is
    applied to baseline_2030 and NZIA."""
    db.clone_scenario(scenario="baseline", name="domestic")   # autarkic PV
    db.clone_scenario(scenario="baseline", name="NZIA")       # before baseline import
    build_baseline_trade(db, cfg)
    apply_nzia_shocks(db, cfg, upstream_reshoring=upstream_reshoring)
    build_2030(db, cfg, mix_source=mix_source)
