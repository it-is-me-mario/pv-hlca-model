"""End-to-end orchestration of the PV-HLCA pipeline (mario 1.0.0).

    base (Zenodo 18744457, parquet)
      -> aggregate (48->22 regions, VA, satellite; zero_output_epsilon=None)
      -> add PV sectors
      -> solar shock (capacity factor, IRENA value added, distribution copy)
      -> (optional) rescale module inputs for module efficiency
      -> neutralise legacy 'Solar' activity
      -> scenarios: domestic, baseline (real trade), NZIA, baseline_2030

A single run is fully described by a :class:`~pv_hlca.params.Params`;
``build_database`` builds one. The efficient grid driver (tree-walked base reuse,
per-run export, resume) lives in :func:`pv_hlca.export.run_and_export`.
"""
from __future__ import annotations
from . import io, hybridize, scenarios
from .params import Params


def prepare_database(cfg):
    """Prepare the aggregated SUT and insert the PV inventories."""
    db = io.parse_base_db(cfg)
    io.aggregate_db(db, cfg)
    hybridize.add_pv_sectors(db, cfg)
    db.calc_ghg(gwp=dict(cfg["parameters"]["gwp_factors"]), label="GHG")
    return db


def apply_technology(db, cfg, module_efficiency):
    hybridize.apply_module_efficiency(db, cfg, module_efficiency)
    hybridize.remove_old_solar(db, cfg)


def apply_scenarios(db, cfg, params, *, with_scenarios=True):
    hybridize.apply_lci_variant(db, cfg, params.lci_variant)
    if with_scenarios:
        scenarios.build_all_scenarios(db, cfg, mix_source=params.electricity_mix,
                                      upstream_reshoring=params.upstream_reshoring)


def configure_database(db, cfg, params, *, with_scenarios=True):
    """Apply one parameter set to a fresh copy of the prepared SUT."""
    hybridize.apply_solar_shock(db, cfg, params.capacity_factor, params.degradation_rate)
    apply_technology(db, cfg, params.module_efficiency)
    apply_scenarios(db, cfg, params, with_scenarios=with_scenarios)
    return db


def build_database(cfg, params: Params = Params(), with_scenarios: bool = True):
    """Build the full hybrid SUT and (optionally) all scenarios for ``params``."""
    return configure_database(prepare_database(cfg), cfg, params,
                              with_scenarios=with_scenarios)
