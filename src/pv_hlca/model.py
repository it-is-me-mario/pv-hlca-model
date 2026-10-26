"""User-facing PV-HLCA model: parameters, independent scenarios, MARIO access."""
from __future__ import annotations

import copy
import json
import importlib.metadata
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import io, pipeline, prepared, scenarios, custom
from .experiment import Scenario
from .params import ModelParameters


class PVModel:
    """PV supply-chain model with a real-trade baseline and named scenarios.

    ``db`` is the underlying MARIO Database. The ``domestic`` scenario is retained
    as the pre-trade template required by the published presets; default exports
    contain the commercial baseline and the scenarios added by the user.
    """

    def __init__(self, db, cfg, parameters, provenance=None):
        self.db = db
        self.cfg = cfg
        self.parameters = parameters
        self.provenance = provenance or {}
        self.scenario_specs = {}
        self.db.clone_scenario(scenario="baseline", name="domestic")
        scenarios.build_baseline_trade(self.db, self.cfg)

    @classmethod
    def build(cls, parameters=None, *, cfg=None, prepared_path=None, download=True, source_path=None):
        """Build from source, or create/reuse a verified prepared bundle.

        Construct a new model when changing technology parameters. Each scenario
        added to that model shares those parameters and starts independently.
        Missing source files are downloaded and converted in ``source_path``;
        ``download=False`` requires local data or a verified complete cache.
        """
        parameters = parameters or ModelParameters()
        if not isinstance(parameters, ModelParameters):
            raise TypeError("parameters must be ModelParameters")
        cfg = copy.deepcopy(cfg if cfg is not None else io.load_config())
        provenance = {}
        if prepared_path is None or not (Path(prepared_path) / "manifest.json").is_file():
            from .download import source_config, DEFAULT_DIRECTORY
            cfg = source_config(cfg, download=download,
                                directory=source_path if source_path is not None else DEFAULT_DIRECTORY)
        if prepared_path is None:
            db = pipeline.prepare_database(cfg)
            provenance = {
                "source": cfg["base_db"].get("zenodo"), "recipe": prepared.recipe(cfg),
                "input_sha256": {f.name: prepared.sha256(f) for f in sorted(Path(cfg["base_db"]["_path"]).glob("*.parquet"))},
            }
        else:
            db, provenance = prepared.prepare(cfg, prepared_path)
        pipeline.apply_parameters(db, cfg, parameters)
        return cls(db, cfg, parameters, provenance)

    @classmethod
    def load(cls, path, parameters=None, *, cfg=None):
        """Load a prepared bundle without reading the original base database."""
        parameters = parameters or ModelParameters()
        if not isinstance(parameters, ModelParameters):
            raise TypeError("parameters must be ModelParameters")
        cfg = copy.deepcopy(cfg if cfg is not None else io.load_config())
        db, provenance = prepared.load(cfg, path)
        pipeline.apply_parameters(db, cfg, parameters)
        return cls(db, cfg, parameters, provenance)

    def add_scenario(self, spec: Scenario):
        """Add a scenario. A name already present is an error, never an overwrite."""
        if not isinstance(spec, Scenario):
            raise TypeError("spec must be a Scenario")
        spec = copy.deepcopy(spec)
        if spec.name in self.db.scenarios:
            raise ValueError(f"Scenario {spec.name!r} already exists; choose a new name")
        custom.validate_regions(self.db, spec)
        parent = "domestic" if spec.preset in ("domestic", "NZIA") else "baseline"
        self.db.clone_scenario(scenario=parent, name=spec.name)
        try:
            if spec.preset == "NZIA":
                scenarios.apply_nzia_shocks(self.db, self.cfg, spec.upstream_reshoring, scenario=spec.name)
            if spec.preset in ("NZIA", "baseline_2030"):
                scenarios.apply_paper_2030(self.db, self.cfg, spec.name, spec.grid_source)
            custom.apply_trade(self.db, self.cfg, spec.name, spec)
            custom.apply_electricity(self.db, spec.name, spec)
        except Exception:
            # A failed experiment must not remain available as a partial scenario.
            self.db.matrices.pop(spec.name, None)
            raise
        self.scenario_specs[spec.name] = spec.as_dict()
        return self

    def results(self, names=None, *, heavy=False):
        """Return tidy indicator tables for baseline and user scenarios.

        Tables: footprints, prices, production, value_added, employment, headline.
        ``heavy=True`` additionally returns disaggregated solar footprints.
        """
        from .export import _tables_for_run
        names = [names] if isinstance(names, str) else list(names) if names is not None else ["baseline", *self.scenario_specs]
        if not names or len(names) != len(set(names)):
            raise ValueError("Select at least one scenario, without duplicates")
        unknown = set(names) - set(self.db.scenarios)
        if unknown:
            raise ValueError(f"Unknown scenarios: {sorted(unknown)}")
        tables = _tables_for_run(self.db, self.cfg, self.parameters, names, heavy)
        tables["production"]["unit"] = tables["production"]["commodity"].map(self.db.units["Commodity"]["unit"])
        tables["employment"]["unit"] = str(self.db.units["Satellite account"].loc["Employment", "unit"])
        return tables

    def export(self, path, *, names=None, heavy=False, overwrite=False):
        """Export results plus all model/scenario assumptions and input checksums."""
        path = Path(path).expanduser().resolve()
        if path.exists() and any(path.iterdir()) and not overwrite:
            raise ValueError(f"{path} is not empty; choose a new output directory or --overwrite")
        names = [names] if isinstance(names, str) else list(names) if names is not None else ["baseline", *self.scenario_specs]
        tables = self.results(names, heavy=heavy)
        configs = {
            "parameters": self.cfg["parameters"], "mappings": self.cfg["mappings"],
            "scenario_2030": self.cfg["scenario_2030"], "capacity_factor_row": self.cfg["capacity_factor_row"],
        }
        employment_unit = str(self.db.units["Satellite account"].loc["Employment", "unit"])
        manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": self.parameters.as_dict(),
            "scenarios": self.scenario_specs,
            "exported_scenarios": names,
            "prepared_model": self.provenance,
            "model_configuration": configs,
            "input_sha256": {key: prepared.sha256(value) for key, value in self.cfg["data"].items()
                             if key != "exiobase_raw"},
            "trade_sha256": prepared.sha256(self.cfg["_import_structure_csv"]),
            "application_sha256": {file.name: prepared.sha256(file) for file in sorted(Path(__file__).parent.glob("*.py"))},
            "runtime": {name: importlib.metadata.version(name) for name in ("mariopy", "numpy", "pandas", "pyarrow")},
            "units": {"footprint_gkwh": "gCO2eq/kWh", "price_eur_kwh": "EUR/kWh",
                      "production": "commodity-specific hybrid units; inspect model.db.units",
                      "value_added": "M EUR", "employment": employment_unit,
                      "global_co2eq": "tonnes CO2eq"},
            "note": "Direct edits through model.db are supported; record those edits separately from these scenario definitions.",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pv-export-", dir=path.parent) as temp:
            staging = Path(temp)
            for name, table in tables.items():
                if name == "_f_dis":
                    table.to_parquet(staging / "f_dis_solar.parquet", index=False)
                else:
                    table.to_csv(staging / f"{name}.csv", index=False)
            manifest["files"] = {f.name: prepared.sha256(f) for f in sorted(staging.iterdir())}
            (staging / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
            path.mkdir(parents=True, exist_ok=True)
            # Invalidate the old completion manifest before replacing any results.
            # A failed write therefore cannot masquerade as a complete older run.
            (path / "run.json").unlink(missing_ok=True)
            for name in manifest["files"]:
                os.replace(staging / name, path / name)
            if overwrite:
                (path / "experiment.json").unlink(missing_ok=True)
                if not heavy:
                    (path / "f_dis_solar.parquet").unlink(missing_ok=True)
            os.replace(staging / "run.json", path / "run.json")
        return path
