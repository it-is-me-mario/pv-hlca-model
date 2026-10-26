import json
from types import SimpleNamespace

import pandas as pd
import pytest

from pv_hlca import io, ModelParameters
from pv_hlca.model import PVModel
from pv_hlca.prepared import sha256


def test_export_records_checksums_units_and_replaces_only_generated_files(tmp_path):
    model = object.__new__(PVModel)
    model.cfg, model.parameters = io.load_config(), ModelParameters()
    model.provenance, model.scenario_specs = {}, {}
    model.db = SimpleNamespace(units={"Satellite account": pd.DataFrame({"unit": ["1000 persons"]}, index=["Employment"])})
    model.results = lambda *args, **kwargs: {"footprints": pd.DataFrame({"scenario": ["baseline"], "footprint_gkwh": [42.]})}
    out = tmp_path / "run"
    out.mkdir()
    (out / "notes.txt").write_text("User notes must survive an overwrite")
    (out / "f_dis_solar.parquet").write_text("stale heavy result")
    (out / "experiment.json").write_text("stale input experiment")
    with pytest.raises(ValueError, match="not empty"):
        model.export(out)
    model.export(out, overwrite=True)
    manifest = json.loads((out / "run.json").read_text())
    assert manifest["files"]["footprints.csv"] == sha256(out / "footprints.csv")
    assert manifest["units"]["employment"] == "1000 persons"
    assert (out / "notes.txt").read_text() == "User notes must survive an overwrite"
    assert not (out / "f_dis_solar.parquet").exists()
    assert not (out / "experiment.json").exists()
