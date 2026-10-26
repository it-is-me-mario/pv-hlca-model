"""Scenario operations with explicit conservation rules for new experiments.

The historical paper formulas remain in scenarios.py. These operations start
from an already traded database and therefore redistribute existing flows,
rather than applying the original pre-trade import transformation twice.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .hybridize import ELECTRICITY_COMMODITIES
from .scenarios import _import_matrix


def validate_regions(db, spec):
    regions = set(db.get_index("Region"))
    mentioned = set(spec.domestic_shares) | set(spec.sourcing) | set(spec.electricity_mix) | set(spec.electricity_demand_tj)
    for commodities in spec.sourcing.values():
        for suppliers in commodities.values():
            mentioned.update(suppliers)
    unknown = mentioned - regions
    if unknown:
        raise ValueError(f"Unknown regions: {', '.join(sorted(map(str, unknown)))}. Available: {', '.join(sorted(regions))}")


def apply_trade(db, cfg, scenario, spec):
    """Preserve each importing activity's total input of each changed commodity.

    Only intermediate PV sourcing changes. Final demand is unchanged. Domestic
    shortcuts preserve each activity's relative foreign shares; an initially
    autarkic activity uses the frozen baseline foreign structure as fallback.
    """
    if not spec.sourcing and not spec.domestic_shares:
        return
    u = db.query(matrices="u", scenarios=scenario).copy()
    regions = list(db.get_index("Region"))
    table = pd.read_csv(cfg["_import_structure_csv"])
    for importer in set(spec.sourcing) | set(spec.domestic_shares):
        cols = [c for c in u.columns if c[0] == importer and c[1] == "Activity"]
        commodities = set(spec.sourcing.get(importer, {})) | set(spec.domestic_shares.get(importer, {}))
        for commodity in commodities:
            rows = [(r, "Commodity", commodity) for r in regions]
            before = u.loc[rows, cols].copy()
            totals = before.sum(axis=0)
            shares = spec.sourcing.get(importer, {}).get(commodity)
            if shares is not None:
                for region, row in zip(regions, rows):
                    u.loc[row, cols] = totals.values * shares.get(region, 0.0)
            else:
                domestic = spec.domestic_shares[importer][commodity]
                foreign = [r for r in regions if r != importer]
                foreign_rows = [(r, "Commodity", commodity) for r in foreign]
                old = before.loc[foreign_rows]
                weights = old.div(old.sum(axis=0).replace(0, np.nan), axis=1)
                missing = weights.isna().all(axis=0) & (totals != 0)
                if missing.any() and domestic < 1:
                    historical = table[(table.scenario == "baseline") & (table.commodity == commodity)]
                    matrix = _import_matrix(historical)
                    fallback = matrix.loc[importer].reindex(foreign, fill_value=0) if importer in matrix.index else pd.Series(0., index=foreign)
                    if fallback.sum() <= 0:
                        raise ValueError(f"No foreign sourcing for {importer}/{commodity}; supply explicit sourcing shares")
                    weights.loc[:, missing] = np.tile((fallback / fallback.sum()).to_numpy()[:, None], (1, int(missing.sum())))
                u.loc[foreign_rows, cols] = weights.fillna(0).multiply(totals * (1 - domestic), axis=1).values
                u.loc[(importer, "Commodity", commodity), cols] = totals.values * domestic
    db.update_scenarios(scenario=scenario, u=u)
    db.reset_to_coefficients(scenario=scenario)


def apply_electricity(db, scenario, spec):
    """Set domestic electricity-input shares, conserving totals column by column.

    All nine sources participate; omitted sources get zero. Imported electricity
    stays unchanged. A separate addition (TJ) affects household final demand only.
    """
    if not spec.electricity_mix and not spec.electricity_demand_tj:
        return
    u = db.query(matrices="u", scenarios=scenario).copy()
    Yc = db.query(matrices="Yc", scenarios=scenario).copy()
    for region in set(spec.electricity_mix) | set(spec.electricity_demand_tj):
        rows = [(region, "Commodity", source) for source in ELECTRICITY_COMMODITIES]
        missing = [row[2] for row in rows if row not in u.index or row not in Yc.index]
        if missing:
            raise ValueError(f"Missing electricity commodities for {region}: {missing}")
        activities = [c for c in u.columns if c[0] == region and c[1] == "Activity"]
        consumers = [c for c in Yc.columns if c[0] == region]
        households = [c for c in consumers if c[2] == "Final consumption expenditure by households"]
        mix = spec.electricity_mix.get(region)
        if mix is not None:
            weights = np.array([mix.get(source, 0.0) for source in ELECTRICITY_COMMODITIES])
            u.loc[rows, activities] = weights[:, None] * u.loc[rows, activities].sum(axis=0).to_numpy()
            Yc.loc[rows, consumers] = weights[:, None] * Yc.loc[rows, consumers].sum(axis=0).to_numpy()
        addition = spec.electricity_demand_tj.get(region, 0)
        if addition:
            if not households:
                raise ValueError(f"No household final-demand column in {region}")
            if mix is None:
                current = Yc.loc[rows, households].sum(axis=1)
                if current.sum() <= 0:
                    raise ValueError(f"Supply electricity_mix for {region} to distribute additional demand")
                weights = (current / current.sum()).to_numpy()
            Yc.loc[rows, households] += weights[:, None] * addition / len(households)
    db.update_scenarios(scenario=scenario, u=u, Yc=Yc)
    db.reset_to_coefficients(scenario=scenario)
