"""I/O and configuration for the PV-HLCA reproducible pipeline (mario 1.0.0)."""
from __future__ import annotations
from pathlib import Path
import yaml
import mario
import pandas as pd


def repo_root() -> Path:
    """Repo root = folder two levels above this file (src/pv_hlca/io.py)."""
    root = Path(__file__).resolve().parents[2]
    return root if (root / "config" / "paths.yaml").is_file() else Path(__file__).parent / "resources"


def load_config(path=None, *, base_db=None) -> dict:
    """Load paths.yaml plus the referenced config files, resolving paths to absolutes."""
    root = repo_root()
    source = Path(path).expanduser().resolve() if path is not None else root / "config" / "paths.yaml"
    cfg = yaml.safe_load(source.read_text())
    # An alternate paths.yaml uses the same root convention as the shipped file:
    # paths are relative to its config/ directory's parent.
    root = source.parent.parent

    def resolve(p: str) -> Path:
        return (root / p).resolve()

    cfg["_root"] = root
    cfg["base_db"]["_path"] = resolve(cfg["base_db"]["path"])
    if base_db is not None:
        cfg["base_db"]["_path"] = Path(base_db).expanduser().resolve()
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
    path = Path(b["_path"])
    required = ("z", "v", "e", "Y", "EY", "units")
    fmt = b.get("format", "parquet")
    if fmt == "parquet":
        for name in required:
            f = path / f"{name}.parquet"
            if not f.is_file():
                raise FileNotFoundError(f"Missing {f}. Download the SUT coefficient files from "
                                        f"{b.get('zenodo', 'Zenodo 18744457')} or pass --base-db PATH.")
            if f.stat().st_size < 1024 and f.read_bytes().startswith(b"version https://git-lfs"):
                raise ValueError(f"{f} is a Git LFS pointer. Run git lfs pull or download the actual database files.")
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


def restore_source_units(db, cfg):
    """Restore units of retained source labels omitted by MARIO's aggregation.

    In this source, the unaggregated cement CO2 satellite survives the numeric
    aggregation but loses its unit entry. Copy its actual source unit (kg),
    rather than assigning the aggregated CO2 unit (tonnes). No values change.
    Missing labels without a source unit are an error, never guessed.
    """
    source = pd.read_parquet(Path(cfg["base_db"]["_path"]) / "units.parquet")
    for level, table in list(db.units.items()):
        labels = db.get_index(level)
        for item in labels:
            if item not in table.index:
                key = (level, item)
                if key not in source.index:
                    raise ValueError(f"No source unit available for {level}/{item}")
                table.loc[item, "unit"] = source.loc[key, "unit"]
