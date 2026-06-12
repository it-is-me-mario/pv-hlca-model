"""I/O and configuration for the PV-HLCA reproducible pipeline (mario 1.0.0)."""
from __future__ import annotations
from pathlib import Path
import yaml
import mario


def repo_root() -> Path:
    """Repo root = folder two levels above this file (src/pv_hlca/io.py)."""
    return Path(__file__).resolve().parents[2]


def load_config() -> dict:
    """Load paths.yaml plus the referenced config files, resolving paths to absolutes."""
    root = repo_root()
    cfg = yaml.safe_load((root / "config" / "paths.yaml").read_text())

    def resolve(p: str) -> Path:
        return (root / p).resolve()

    cfg["_root"] = root
    cfg["base_db"]["_path"] = resolve(cfg["base_db"]["path"])
    for k, v in cfg["data"].items():
        cfg["data"][k] = resolve(v)
    for k, v in cfg["outputs"].items():
        cfg["outputs"][k] = resolve(v)
    # load nested config files
    cfg["parameters"] = yaml.safe_load(resolve(cfg["config"]["parameters"]).read_text())
    cfg["mappings"] = yaml.safe_load(resolve(cfg["config"]["mappings"]).read_text())
    cfg["scenario_2030"] = yaml.safe_load(resolve(cfg["config"]["scenario_2030"]).read_text())
    cfg["capacity_factor_row"] = yaml.safe_load(resolve(cfg["config"]["capacity_factor_row"]).read_text())
    cfg["_import_structure_csv"] = resolve(cfg["config"]["import_structure"])
    cfg["reference"]["_footprints_dir"] = resolve(cfg["reference"]["footprints_dir"])
    cfg["reference"]["_results_full"] = (root / cfg["reference"]["results_full"]).resolve()
    return cfg


def parse_base_db(cfg: dict):
    """Parse the base hybrid-units SUT (EXIOBASE+H2+green steel) from Zenodo 18744457.

    The base DB is distributed as parquet (faster than txt). Falls back to txt.
    """
    b = cfg["base_db"]
    fmt = b.get("format", "parquet")
    if fmt == "parquet":
        return mario.parse_from_parquet(path=str(b["_path"]), table=b["table"], mode=b["mode"])
    return mario.parse_from_txt(path=str(b["_path"]), table=b["table"], mode=b["mode"])


def aggregate_db(db, cfg) -> None:
    """Aggregate value-added categories, satellite accounts and regions (48 -> 22).

    In place. Uses the aggregation workbook (Aggregate_VA_SA_and_regions.xlsx).

    NOTE: zero_output_epsilon=None disables the SUT zero-output flow override, which
    in mario 1.0.0 mis-divides non-zero supply by epsilon (1e-30) and produces market
    shares ~1e38 -> singular Leontief -> globally degenerate footprints.
    """
    db.aggregate(io=str(cfg["data"]["aggregation"]), ignore_nan=True, zero_output_epsilon=None)
