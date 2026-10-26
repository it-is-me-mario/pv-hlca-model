"""Portable, checksummed parameter-independent PV database bundles (no pickle)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import importlib.metadata

import mario

from . import io, pipeline


FORMAT_VERSION = 1


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def recipe(cfg):
    """Preparation identity, independent of absolute paths and user scenarios."""
    code = Path(__file__).parent
    return {
        "mariopy": importlib.metadata.version("mariopy"),
        "gwp_factors": cfg["parameters"]["gwp_factors"],
        "data": {key: sha256(cfg["data"][key]) for key in ("aggregation", "add_sectors")},
        "code": {name: sha256(code / name) for name in ("io.py", "pipeline.py", "hybridize.py", "prepared.py")},
    }


def read_manifest(path):
    source = Path(path) / "manifest.json"
    if not source.is_file():
        raise FileNotFoundError(f"No prepared-model manifest at {source}. Run prepare first.")
    manifest = json.loads(source.read_text())
    if manifest.get("format_version") != FORMAT_VERSION or manifest.get("stage") != "before_technology_parameters":
        raise ValueError(f"Unsupported prepared-model format in {source}")
    return manifest


def load(cfg, path):
    """Load and verify a bundle; the original large input database is not needed."""
    path = Path(path).expanduser().resolve()
    manifest = read_manifest(path)
    if manifest["recipe"] != recipe(cfg):
        raise ValueError("Prepared model uses a different preparation recipe or MARIO version. "
                         "Prepare a new bundle in another directory with this checkout.")
    files = manifest.get("files", {})
    required = {f"coefficients/{name}.parquet" for name in ("z", "v", "e", "Y", "EY", "units")}
    if not required <= files.keys():
        raise ValueError("Prepared model manifest is missing required coefficient files")
    for name, expected in files.items():
        file = (path / name).resolve()
        if not file.is_relative_to(path) or not file.is_file() or sha256(file) != expected:
            raise ValueError(f"Prepared model checksum failed: {name}")
    db = mario.parse_from_parquet(path=str(path / "coefficients"), table="SUT", mode="coefficients")
    return db, manifest


def prepare(cfg, path):
    """Prepare once, export coefficients and write a manifest last, atomically.

    Existing valid bundles are loaded. An existing incomplete or incompatible
    bundle is never silently reused or overwritten.
    """
    path = Path(path).expanduser().resolve()
    if (path / "manifest.json").exists():
        return load(cfg, path)
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"{path} is not an empty bundle directory; choose another --prepared path")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = pipeline.prepare_database(cfg)
    inputs = {file.name: sha256(file) for file in sorted(Path(cfg["base_db"]["_path"]).glob("*.parquet"))}
    with tempfile.TemporaryDirectory(prefix=f".{path.name}-", dir=path.parent) as temp:
        staging = Path(temp) / "bundle"
        db.to_parquet(path=str(staging), flows=False, coefficients=True)
        files = {str(file.relative_to(staging)): sha256(file)
                 for file in sorted(staging.rglob("*.parquet"))}
        manifest = {
            "format_version": FORMAT_VERSION,
            "stage": "before_technology_parameters",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": cfg["base_db"].get("zenodo"),
            "input_sha256": inputs,
            "recipe": recipe(cfg),
            "files": files,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if path.exists():  # only the empty directory accepted above
            path.rmdir()
        staging.rename(path)
    return db, manifest
