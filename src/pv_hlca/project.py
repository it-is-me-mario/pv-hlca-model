"""Project files and execution for the installable PV-HLCA model."""

import csv
from dataclasses import replace
from importlib.metadata import distribution
from importlib.resources import files
import os
from pathlib import Path
from shutil import copyfile, copytree
from tempfile import TemporaryDirectory
from uuid import uuid4

from openpyxl import Workbook
import yaml

from . import data, export, pipeline
from .params import Params, PARAMETER_INFO

PUBLICATION = "https://doi.org/10.1007/s44498-026-00175-0"
SCENARIOS = ("baseline", "NZIA", "baseline_2030", "domestic")
RESOURCES = files("pv_hlca").joinpath("resources")
INDICATORS = {
    "footprints": "Solar electricity footprint in g CO2eq/kWh",
    "prices": "Solar electricity producer price in EUR/kWh",
    "production": "PV commodity output in its declared MARIO unit",
    "value_added": "Value added in million EUR",
    "employment": "Employment by region and activity",
    "headline": "EU27 value added and global GHG emissions",
}


def _yaml(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _merge_section(default, changes, section):
    if not isinstance(changes, dict):
        raise ValueError(f"Expected a mapping for {section}")
    unknown = changes.keys() - default.keys()
    if unknown:
        raise ValueError(f"Unknown fields in {section}: {', '.join(sorted(map(str, unknown)))}")
    return default | changes


def _copy_defaults(source, destination):
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_defaults(child, destination / child.name)
    elif not destination.exists():
        destination.write_bytes(source.read_bytes())


def _write_workbook(source, target):
    """Translate text inputs to the workbook format used by MARIO."""
    workbook = Workbook(write_only=True)
    for path in sorted(source.glob("*.csv")):
        sheet = workbook.create_sheet(title=path.stem)
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            numeric = {"Quantity", "Market share", "Final consumption"}
            sheet.append([value or None for value in header])
            for row in reader:
                values = []
                for name, value in zip(header, row, strict=True):
                    if value and name in numeric:
                        try:
                            values.append(float(value))
                        except ValueError as exc:
                            raise ValueError(f"{path}:{reader.line_num}: invalid {name}: {value!r}") from exc
                    else:
                        values.append(value or None)
                sheet.append(values)
    workbook.save(target)


def _snapshot_inputs(root, paths):
    snapshots = {}
    hashes = {}
    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing input {name!r}: {path}")
        destination = root / name
        if path.is_dir():
            copytree(path, destination)
            for item in sorted(destination.rglob("*")):
                if item.is_file():
                    hashes[item.relative_to(root).as_posix()] = data.sha256(item)
        else:
            destination = destination.with_suffix(path.suffix)
            copyfile(path, destination)
            hashes[destination.name] = data.sha256(destination)
        snapshots[name] = destination
    return snapshots, hashes


def _pipeline_config(inputs, database, temporary):
    aggregation = temporary / "aggregation.xlsx"
    inventory = temporary / "pv_inventory.xlsx"
    _write_workbook(inputs["aggregation"], aggregation)
    _write_workbook(inputs["pv_inventory"], inventory)
    return {
        "base_db": {"_path": database, "format": "parquet", "table": "SUT",
                    "mode": "coefficients"},
        "data": {
            "aggregation": aggregation,
            "add_sectors": inventory,
            "capacity_factor_multipliers_owid": inputs["capacity_factor_multipliers_owid"],
            "capacity_factor_multipliers_rn": inputs["capacity_factor_multipliers_rn"],
        },
        "parameters": _yaml(inputs["parameters"]),
        "mappings": _yaml(inputs["mappings"]),
        "scenario_2030": _yaml(inputs["scenario_2030"]),
        "capacity_factor_row": _yaml(inputs["capacity_factor_row"]),
        "_import_structure_csv": inputs["trade_shares"],
    }


class Project:
    """PV model with editable input files, a shareable data cache and run records."""

    def __init__(self, workspace, *, cache_dir=None):
        self.workspace = Path(workspace).expanduser().resolve()
        default_cache = os.environ.get("MARIO_MODEL_CACHE") or Path.home() / ".cache" / "mario" / "models"
        self.cache_dir = Path(cache_dir if cache_dir is not None else default_cache).expanduser().resolve()
        self.config_path = self.workspace / "config.yaml"
        self._prepared = None
        self._prepared_key = None
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            _copy_defaults(RESOURCES.joinpath("inputs"), self.workspace / "inputs")
            _copy_defaults(RESOURCES.joinpath("config.yaml"), self.config_path)
        self._config()

    def _config(self):
        defaults = _yaml(RESOURCES.joinpath("config.yaml"))
        changes = _yaml(self.config_path)
        config = _merge_section(defaults, changes, "config.yaml")
        if config["model"] != "pv-hlca":
            raise ValueError(f"{self.config_path} is not a PV-HLCA project.")
        for section in ("parameters", "data", "inputs"):
            config[section] = _merge_section(defaults[section], config[section], section)
        return config

    def describe(self):
        """Return current effective parameters, available indicators and data provenance."""
        config = self._config()
        return {
            "model": "pv-hlca",
            "publication": PUBLICATION,
            "tags": ["Hybrid LCA", "Input-output model", "Energy transition", "EXIOBASE Hybrid"],
            "parameters": {
                name: {"description": description, "value": config["parameters"][name]}
                for name, description in PARAMETER_INFO.items()
            },
            "scenarios": SCENARIOS,
            "indicators": INDICATORS.copy(),
            "database": data.manifest(),
            "documentation": self.docs(),
        }

    def docs(self):
        """Return the documentation shipped with this model version."""
        return RESOURCES.joinpath("GUIDE.md")

    def fetch_data(self):
        """Download missing background matrices to the cache and verify them."""
        config = self._config()
        return data.resolve_data(config["data"], self.workspace, self.cache_dir, download=True)

    def build(self, *, download=False, **overrides):
        """Read the project files and return an ordinary MARIO Database."""
        import mario

        config = self._config()
        params = replace(Params(), **_merge_section(config["parameters"], overrides, "parameters"))
        params.validate()
        database = data.resolve_data(config["data"], self.workspace, self.cache_dir, download=download)
        paths = {key: (self.workspace / Path(value).expanduser()).resolve()
                 for key, value in config["inputs"].items()}

        runs = self.workspace / "runs"
        runs.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=runs) as staging:
            root = Path(staging)
            inputs_root = root / "inputs"
            inputs_root.mkdir()
            inputs, hashes = _snapshot_inputs(inputs_root, paths)
            with TemporaryDirectory() as working:
                cfg = _pipeline_config(inputs, database, Path(working))
                key = (database, mario.__version__, hashes)
                if self._prepared_key != key:
                    self._prepared = None
                    self._prepared_key = None
                    self._prepared = pipeline.prepare_database(cfg)
                    self._prepared_key = key
                db = pipeline.configure_database(self._prepared.copy(), cfg, params)
            config["parameters"] = params.as_dict()
            config["data"]["path"] = str(database)
            config["inputs"] = {key: path.relative_to(root).as_posix() for key, path in inputs.items()}
            _write_yaml(root / "config.yaml", config)

            installed = distribution("mario-pv-hlca")
            _write_yaml(root / "provenance.yaml", {
                "model_version": installed.version,
                "model_install_source": yaml.safe_load(installed.read_text("direct_url.json") or "null"),
                "mario_version": mario.__version__,
                "publication": PUBLICATION,
                "database": data.manifest(),
                "input_sha256": hashes,
            })
            run_dir = runs / uuid4().hex
            root.replace(run_dir)

        db.add_note(f"PV-HLCA run: {run_dir.name}")
        db._pv_hlca_run = run_dir
        return db

    def run_directory(self, db):
        """Return the saved configuration and input snapshot for this database."""
        path = getattr(db, "_pv_hlca_run", None)
        if path is None or path.parent != self.workspace / "runs":
            raise ValueError("Build this database with the current PV-HLCA project first.")
        return path

    def results(self, db, *, write=False):
        """Return the six PV result tables. Optionally write CSVs to the run directory."""
        path = self.run_directory(db)
        config = _yaml(path / "config.yaml")
        cfg = {"parameters": _yaml(path / config["inputs"]["parameters"])}
        tables = export.tables_for_run(db, cfg, Params(**config["parameters"]), SCENARIOS)
        if write:
            out = path / "results"
            out.mkdir(exist_ok=True)
            for name, table in tables.items():
                table.to_csv(out / f"{name}.csv", index=False)
        return tables
