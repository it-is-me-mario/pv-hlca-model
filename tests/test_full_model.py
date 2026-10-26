"""Opt-in full-database contracts.

PV_HLCA_PREPARED=/path/to/bundle python -m pytest -q tests/test_full_model.py
Fast CI skips these when the external prepared database is absent.
"""
import os

import pandas as pd
import pytest

from pv_hlca import PVModel, ModelParameters, io, pipeline, prepared
from pv_hlca import export
from pv_hlca.params import Params

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.environ.get("PV_HLCA_PREPARED"), reason="external prepared model not configured")]


def test_reload_needs_no_source_database_and_parameters_are_effective():
    cfg = io.load_config(base_db="/nonexistent/source-is-not-needed")
    model = PVModel.load(os.environ["PV_HLCA_PREPARED"], cfg=cfg)
    before = model.db.query(matrices="u", scenarios="baseline")
    changed = PVModel.load(os.environ["PV_HLCA_PREPARED"], ModelParameters(degradation_rate=.005, lci_variant="NREL"), cfg=cfg)
    after = changed.db.query(matrices="u", scenarios="baseline")
    col = ("EU27", "Activity", "Solar Power Plant")
    module_rows = [r for r in before.index if r[2] == "PV modules"]
    ratio = after.loc[module_rows, col].sum() / before.loc[module_rows, col].sum()
    eta = (1 - (1-.005)**25) / (25*.005)
    assert ratio == pytest.approx(1/eta)
    elec_rows = [r for r in before.index if r[2] in ("Coal", "Gas", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other Fossil", "Other Renewables")]
    col = ("CN", "Activity", "Solar Grade silicon production")
    assert after.loc[elec_rows, col].sum() / before.loc[elec_rows, col].sum() == pytest.approx(72/49)
    assert model.db.units["Satellite account"].loc["Carbon dioxide, Cement (air - Emiss)", "unit"] == "kg"


def test_single_constructor_and_batch_apply_same_nondefault_parameters(monkeypatch, tmp_path):
    cfg = io.load_config()
    cfg["data"].pop("exiobase_raw", None)  # external top-down benchmark is a separate workflow
    bundle = os.environ["PV_HLCA_PREPARED"]
    monkeypatch.setattr(pipeline, "prepare_database", lambda cfg: prepared.load(cfg, bundle)[0])
    params = Params(capacity_factor="RN", module_efficiency=.22, degradation_rate=.005,
                    lci_variant="NREL", electricity_mix="EMBER", upstream_reshoring=.6)
    single = pipeline.build_database(cfg, params)
    captured = {}

    def capture(db, cfg, params, scenario_list, heavy):
        # Test coefficient equivalence without recomputing every derived indicator.
        for scenario in scenario_list:
            for block in ("u", "s", "va", "vc", "ea", "ec", "Ya", "Yc"):
                a = single.query(matrices=block, scenarios=scenario)
                b = db.query(matrices=block, scenarios=scenario)
                pd.testing.assert_frame_equal(a, b, rtol=1e-12, atol=1e-12)
        captured["matched"] = True
        return {name: pd.DataFrame() for name in export._TABLES}

    monkeypatch.setattr(export, "_tables_for_run", capture)
    export.run_and_export(cfg, [params], tmp_path, resume=False)
    assert captured["matched"]
