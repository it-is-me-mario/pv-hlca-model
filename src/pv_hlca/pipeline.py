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


def build_database(cfg, params: Params = Params(), with_scenarios: bool = True):
    """Build the full hybrid SUT and (optionally) all scenarios for ``params``."""
    db = io.parse_base_db(cfg)
    io.aggregate_db(db, cfg)
    hybridize.build_hybrid_db(db, cfg, variant=params.capacity_factor,
                              module_efficiency=params.module_efficiency)
    if with_scenarios:
        scenarios.build_all_scenarios(db, cfg, mix_source=params.electricity_mix,
                                      upstream_reshoring=params.upstream_reshoring)
    return db
