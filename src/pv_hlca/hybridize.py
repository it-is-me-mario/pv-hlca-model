"""Hybridisation stage: add the explicit PV supply chain to the aggregated base
and apply the solar shock, then remove the legacy aggregate 'Solar' activity.

mario 1.0.0 port note
---------------------
In mario 1.0.0 a SUT scenario in coefficient mode is stored as coefficient
*blocks* (u=use, s=supply, va/vc=value added, ea/ec=satellite, Ya/Yc=final
demand); ``z`` is *derived* from u/s and is therefore read-only for recompute.
All shock operations act on Commodity->Activity flows, i.e. the
``u`` block (and the activity-side ``va``/``ea`` blocks). We modify those blocks
and call ``update_scenarios`` + ``reset_to_coefficients`` so f/w recompute.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

DISTR = "Distribution and trade services of electricity"
OLD_SOLAR = "Solar"
SOLAR_PP = "Solar Power Plant"
NEW_ACTIVITIES = [
    "PV modules production", "Cells production", "Wafer production",
    "Ingot production", "Solar Grade silicon production",
    "Metallurgical Grade silicon production",
]
FACTOR_CAPEX = "Operating surplus: Consumption of fixed capital"
FACTOR_LABOR = "Compensation of employees"


# --------------------------------------------------------------------------- #
# add_sectors
# --------------------------------------------------------------------------- #
def add_pv_sectors(db, cfg) -> None:
    """Insert the 18 PV activities / 16 commodities from Add_sectors.xlsx."""
    db.read_add_sectors_excel(path=str(cfg["data"]["add_sectors"]), read_inventories=True)
    db.add_sectors()


# --------------------------------------------------------------------------- #
# capacity-factor multipliers
# --------------------------------------------------------------------------- #
def load_cf_multipliers(db, cfg, variant: str = "RN") -> dict:
    """Return {region_code: capacity_factor_multiplier} for 'RN' or 'OWID'."""
    if variant == "RN":
        df = pd.read_csv(cfg["data"]["capacity_factor_multipliers_rn"])
        m = dict(zip(df["Entity"], df["Capacity_factor_multiplier"]))
        return {r: m[r] for r in db.get_index("Region") if r in m}
    elif variant == "OWID":
        df = pd.read_csv(cfg["data"]["capacity_factor_multipliers_owid"])
        full = dict(zip(df["Entity"], df["Capacity_factor_multiplier"]))
        code2full = cfg["mappings"]["region_code_to_full_name"]
        out = {}
        for r in db.get_index("Region"):
            name = code2full.get(r, r)
            if name in full:
                out[r] = full[name]
        return out
    raise ValueError(f"unknown variant {variant!r}")


# --------------------------------------------------------------------------- #
# IRENA-based regional value added for the Solar Power Plant
# --------------------------------------------------------------------------- #
def _solar_value_added(cfg) -> pd.DataFrame:
    p = cfg["parameters"]
    W = p["W_per_m2"]; usd_eur = p["usd_to_eur"]; use = p["use_of_PV_m2_per_TJ"]
    life = p["lifetime_years"]; om_share = p["om_labor_share"]
    capex = p["irena"]["total_capex_usd_per_w"]
    labfr = p["irena"]["installation_labor_fraction"]
    pvfr = p["irena"]["pv_modules_fraction"]
    om = p["irena"]["o_and_m_usd_per_kw_year"]
    rows = []
    for c, tot_usd_w in capex.items():
        total_eur_TJ = tot_usd_w * usd_eur * W * use
        capex_minus = total_eur_TJ * (1 - labfr[c] - pvfr[c])
        install_labor = total_eur_TJ * labfr[c]
        om_labor = om[c] * om_share / 1000 * usd_eur * W * use * life
        rows.append({
            "Country": c,
            "capex_eur_per_TJ": capex_minus,
            "labor_eur_per_TJ": install_labor + om_labor,
        })
    return pd.DataFrame(rows).set_index("Country")


# --------------------------------------------------------------------------- #
# the solar shock
# --------------------------------------------------------------------------- #
def _lifetime_yield_factor(degradation_rate: float, lifetime_years: int) -> float:
    """Mean lifetime yield relative to a constant-output plant under a constant
    annual degradation ``d``: eta = (1/N) * sum_{t=0..N-1} (1-d)^t. Returns 1.0
    for d=0 (the published constant-output assumption)."""
    d = float(degradation_rate)
    if d <= 0.0:
        return 1.0
    n = int(lifetime_years)
    return (1.0 - (1.0 - d) ** n) / (n * d)


def apply_solar_shock(db, cfg, variant: str = "RN", degradation_rate: float = 0.0) -> None:
    """Distribution copy + IRENA VA + capacity-factor scaling + VA/employment
    regionalisation for the new PV activities. Operates on u/va/ea blocks.

    ``degradation_rate`` (annual, e.g. 0.005) lowers the mean lifetime yield by
    ``eta`` and therefore scales every per-TJ inventory coefficient by an extra
    ``1/eta`` — exactly where the capacity factor is applied, since both act on the
    lifetime electricity generated per unit of installed hardware."""
    regions = list(db.get_index("Region"))
    commodities = list(db.get_index("Commodity"))
    u = db.query(matrices="u", scenarios="baseline").copy()
    va = db.query(matrices="va", scenarios="baseline").copy()
    ea = db.query(matrices="ea", scenarios="baseline").copy()
    mult = load_cf_multipliers(db, cfg, variant)
    eta = _lifetime_yield_factor(degradation_rate, cfg["parameters"]["lifetime_years"])

    def urow(region, item):   return (region, "Commodity", item)
    def ucol(region, item):   return (region, "Activity", item)

    # 0) copy distribution use old Solar -> Solar Power Plant (block, all regions)
    distr_rows = [urow(r, DISTR) for r in regions]
    old_cols = [ucol(r, OLD_SOLAR) for r in regions]
    new_cols = [ucol(r, SOLAR_PP) for r in regions]
    u.loc[distr_rows, new_cols] = u.loc[distr_rows, old_cols].values

    # 0.3) fill regions with zero distribution by the average of non-zero ones
    diag = {r: float(u.loc[urow(r, DISTR), ucol(r, SOLAR_PP)]) for r in regions}
    avg = float(np.mean([v for v in diag.values() if v != 0]))
    for r in regions:
        if diag[r] == 0:
            u.loc[urow(r, DISTR), ucol(r, SOLAR_PP)] = avg

    # 1) IRENA regional value added for Solar Power Plant
    vadf = _solar_value_added(cfg)
    for r in regions:
        if r in vadf.index:
            va.loc[FACTOR_CAPEX, ucol(r, SOLAR_PP)] = vadf.loc[r, "capex_eur_per_TJ"] / 1e6
            va.loc[FACTOR_LABOR, ucol(r, SOLAR_PP)] = vadf.loc[r, "labor_eur_per_TJ"] / 1e6

    # 2) capacity-factor scaling (all commodity inputs except distribution; va; ea)
    non_distr_rows = [urow(r, c) for r in regions for c in commodities if c != DISTR]
    for r in regions:
        if r not in mult:
            continue
        inv = 1.0 / (mult[r] * eta)        # CF scaling + (optional) degradation 1/eta
        u.loc[non_distr_rows, ucol(r, SOLAR_PP)] *= inv
        va.loc[:, ucol(r, SOLAR_PP)] *= inv
        ea.loc[:, ucol(r, SOLAR_PP)] *= inv

    # 3) regionalise VA and employment for the other new activities by parent
    parents = cfg["mappings"]["new_activity_parent"]
    emp = "Employment"
    for child, parent in parents.items():
        if child == SOLAR_PP:
            parent_is_solar = True
        else:
            parent_is_solar = (parent == OLD_SOLAR)
        parent_cols = [ucol(r, parent) for r in regions if (r, "Activity", parent) in va.columns]
        v_parent_mean = va[parent_cols].replace(0, np.nan).mean(axis=1)        # per factor
        e_parent_row = ea.loc[emp, parent_cols]
        e_parent_mean = e_parent_row[e_parent_row != 0].mean()
        for r in regions:
            ccol = ucol(r, child); pcol = ucol(r, parent)
            if not parent_is_solar and ccol in va.columns and pcol in va.columns:
                pv = va[pcol].values
                if not (pd.isnull(pv).any() or np.isinf(pv).any() or (pv == 0).all()):
                    coeff = np.where(pv == 0, 1, pv / v_parent_mean.values) if (pv == 0).any() else pv / v_parent_mean.values
                    va[ccol] = va[ccol].values * coeff
            # employment
            if ccol in ea.columns and pcol in ea.columns:
                pe = ea.loc[emp, pcol]
                if not (pd.isna(pe) or np.isinf(pe) or pe == 0 or pd.isna(e_parent_mean) or e_parent_mean == 0):
                    ea.loc[emp, ccol] *= pe / e_parent_mean

    db.update_scenarios(scenario="baseline", u=u, va=va, ea=ea)
    db.reset_to_coefficients(scenario="baseline")


# --------------------------------------------------------------------------- #
# neutralise the legacy aggregate 'Solar' activity
# --------------------------------------------------------------------------- #
def remove_old_solar(db, cfg) -> None:
    """Neutralise the legacy aggregate 'Solar' activity so that 'Solar Power Plant'
    becomes the sole producer of the 'Solar' commodity.

    The legacy activity is made fully inert (zero use inputs, zero supply, zero
    value added and zero satellite). It stays in the index but contributes nothing;
    on a healthy DB this is harmless and yields s[:, Solar] == 1 (sole producer) and
    fa(Solar Power Plant) == fc(Solar).

    (Dropping it from the index via a second ``aggregate`` is avoided: mario 1.0.0
    breaks the supply market share / unit metadata on a double aggregation.)
    """
    regions = list(db.get_index("Region"))
    u = db.query(matrices="u", scenarios="baseline").copy()
    s = db.query(matrices="s", scenarios="baseline").copy()
    va = db.query(matrices="va", scenarios="baseline").copy()
    ea = db.query(matrices="ea", scenarios="baseline").copy()
    old = [(r, "Activity", OLD_SOLAR) for r in regions]
    u.loc[:, old] = 0.0       # no inputs
    va.loc[:, old] = 0.0      # no value added
    ea.loc[:, old] = 0.0      # no direct emissions
    s.loc[old, :] = 0.0       # produces nothing -> Solar Power Plant becomes sole Solar producer
    db.update_scenarios(scenario="baseline", u=u, s=s, va=va, ea=ea)
    db.reset_to_coefficients(scenario="baseline")


# --------------------------------------------------------------------------- #
# module efficiency (area-proportional module inputs)
# --------------------------------------------------------------------------- #
# Inputs of the Solar Power Plant that scale with module *area* per unit of
# electricity (m2/TJ). Higher efficiency -> fewer m2 -> smaller footprint.
# The IRENA value added is efficiency-invariant (W/m2 up cancels m2/TJ down), so
# it is left untouched.
AREA_PROPORTIONAL_INPUTS = ["PV modules", "PV end of life management"]


def apply_module_efficiency(db, cfg, efficiency: float) -> None:
    """Scale the area-proportional module inputs of every Solar Power Plant by
    module_efficiency_ref / efficiency."""
    ref = float(cfg["parameters"].get("module_efficiency_ref", 0.195))
    if efficiency is None or abs(efficiency - ref) < 1e-12:
        return
    factor = ref / efficiency
    u = db.query(matrices="u", scenarios="baseline").copy()
    for r in db.get_index("Region"):
        col = (r, "Activity", SOLAR_PP)
        if col not in u.columns:
            continue
        for com in AREA_PROPORTIONAL_INPUTS:
            row = (r, "Commodity", com)
            if row in u.index:
                u.loc[row, col] *= factor
    db.update_scenarios(scenario="baseline", u=u)
    db.reset_to_coefficients(scenario="baseline")


# --------------------------------------------------------------------------- #
# LCI sensitivity: upstream-stage electricity intensity (IEA PVPS vs NREL)
# --------------------------------------------------------------------------- #
# The inventory's "Electricity" input is not a single DB commodity: add_sectors
# distributes it over the per-source electricity vectors below according to each
# region's grid mix. Scaling all of them by the same factor scales the stage's
# total electricity intensity while preserving the regional mix.
ELECTRICITY_COMMODITIES = [
    "Coal", "Gas", "Hydro", "Nuclear", "Solar", "Wind",
    "Bioenergy", "Other Fossil", "Other Renewables",
]


def apply_lci_variant(db, cfg, variant: str = "IEA") -> None:
    """Switch the electricity intensity of the upstream PV stages between the
    reference IEA PVPS inventory (already baked into the DB) and the NREL values.

    ``variant='IEA'`` is a no-op. ``variant='NREL'`` scales every electricity-vector
    input of each '<stage> production' activity by nrel/iea (config
    ``lci_electricity_kwh_per_kg``), for every region — preserving the regional grid
    mix. Acts on the ``u`` block; the Excel inventory is never touched."""
    if variant is None or variant.upper() == "IEA":
        return
    if variant.upper() != "NREL":
        raise ValueError(f"unknown lci_variant {variant!r} (expected 'IEA' or 'NREL')")
    table = cfg["parameters"]["lci_electricity_kwh_per_kg"]
    regions = list(db.get_index("Region"))
    u = db.query(matrices="u", scenarios="baseline").copy()
    for stage, vals in table.items():
        ratio = float(vals["nrel"]) / float(vals["iea"])
        if abs(ratio - 1.0) < 1e-12:
            continue
        col_act = f"{stage} production"
        elec_rows = [(r, "Commodity", c) for r in regions for c in ELECTRICITY_COMMODITIES
                     if (r, "Commodity", c) in u.index]
        cols = [(r, "Activity", col_act) for r in regions if (r, "Activity", col_act) in u.columns]
        u.loc[elec_rows, cols] *= ratio
    db.update_scenarios(scenario="baseline", u=u)
    db.reset_to_coefficients(scenario="baseline")


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
def build_hybrid_db(db, cfg, variant: str = "RN", module_efficiency: float | None = None) -> None:
    """In place: add PV sectors, apply solar shock, (optionally) rescale module
    inputs for a non-reference efficiency, then remove legacy Solar."""
    add_pv_sectors(db, cfg)
    apply_solar_shock(db, cfg, variant)
    if module_efficiency is not None:
        apply_module_efficiency(db, cfg, module_efficiency)
    remove_old_solar(db, cfg)
