"""Acquire the fixed Zenodo source and convert its CSV-formatted TXT matrices.

Only the six required files are fetched. Downloads resume in .part files; the
published size and MD5 are checked before conversion. No extraction or pickle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import time
from http.client import HTTPException
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .io import repo_root

RECORD = 18744457
REQUIRED = ("z", "v", "e", "Y", "EY", "units")
DEFAULT_DIRECTORY = Path("models/source-18744457")
_CONVERTER = 1
_CHUNK_ROWS = 1024  # bound memory while avoiding thousands of tiny Parquet row groups


def _hash(path, algorithm="sha256"):
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _catalog():
    record = json.loads((repo_root() / "config/zenodo-source.json").read_text())
    if record["record_id"] != RECORD:
        raise ValueError("Expected the fixed Zenodo record 18744457")
    files = {f["key"]: f for f in record["files"]}
    for stem in REQUIRED:
        f = files[f"{stem}.txt"]
        if not re.fullmatch(r"md5:[0-9a-f]{32}", f["checksum"]) or f["size"] <= 0:
            raise ValueError(f"Invalid pinned Zenodo metadata for {stem}")
        if not f["links"]["self"].startswith(f"https://zenodo.org/api/records/{RECORD}/files/"):
            raise ValueError(f"Unexpected Zenodo URL for {stem}")
    return record


def _matches(path, entry):
    return (path.is_file() and path.stat().st_size == entry["size"]
            and _hash(path, "md5") == entry["checksum"].split(":", 1)[1])


def _download_file(entry, directory, progress=print):
    target = directory / entry["key"]
    if _matches(target, entry):
        progress(f"Verified cached {target.name}")
        return target
    if target.exists():
        raise ValueError(f"Checksum mismatch for {target}; move the damaged file aside and retry")
    part = target.with_suffix(target.suffix + ".part")
    for attempt in range(3):
        offset = part.stat().st_size if part.exists() else 0
        if offset > entry["size"]:
            raise ValueError(f"Oversized partial download: {part}")
        if offset == entry["size"]:
            if _matches(part, entry):
                os.replace(part, target)
                return target
            part.unlink()  # an uncommitted corrupt transfer, never a user's source file
            offset = 0
        headers = {"User-Agent": "PV-HLCA-model/1.1", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(entry["links"]["self"] + "?download=1", headers=headers)
        progress(f"Downloading {target.name}: {offset / 1e6:.1f}/{entry['size'] / 1e6:.1f} MB")
        try:
            with urlopen(request, timeout=60) as response:
                if response.status == 206:
                    expected = f"bytes {offset}-{entry['size'] - 1}/{entry['size']}"
                    if response.headers.get("Content-Range") != expected:
                        raise ValueError(f"Invalid resume response for {target.name}")
                elif response.status == 200:
                    offset = 0  # server ignored Range: safely restart the partial file
                else:
                    raise OSError(f"Unexpected HTTP {response.status} for {target.name}")
                last = time.monotonic()
                with part.open("ab" if offset else "wb") as stream:
                    count = offset
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > entry["size"]:
                            raise ValueError(f"Download exceeds published size: {target.name}")
                        stream.write(block)
                        if time.monotonic() - last >= 5:
                            progress(f"  {target.name}: {count / 1e6:.1f}/{entry['size'] / 1e6:.1f} MB")
                            last = time.monotonic()
            if not _matches(part, entry):
                raise OSError(f"Incomplete transfer or checksum mismatch for {target.name}")
            os.replace(part, target)
            progress(f"Verified {target.name}")
            return target
        except (OSError, URLError, HTTPException) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise OSError(f"Zenodo HTTP {exc.code} for {target.name}") from exc
            if attempt == 2:
                raise OSError(f"Could not download {target.name}; rerun to resume. {exc}") from exc
            time.sleep(attempt + 1)
    raise AssertionError("unreachable")


def _convert(source, target, progress=print):
    """Convert in row chunks, preserving index labels and round-trip float values."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    if source.stem == "units":
        pd.read_csv(source, index_col=[0, 1], keep_default_na=False).to_parquet(target)
        return
    index = [0, 1, 2] if source.stem in ("z", "Y") else [0]
    writer = None
    rows = 0
    try:
        for chunk in pd.read_csv(source, header=[0, 1, 2], index_col=index,
                                 keep_default_na=False, float_precision="round_trip", chunksize=_CHUNK_ROWS):
            chunk = chunk.astype(float)
            table = pa.Table.from_pandas(chunk, preserve_index=True)
            if writer is None:
                writer = pq.ParquetWriter(target, table.schema)
            writer.write_table(table)
            rows += len(chunk)
            if source.stem == "z":
                progress(f"  Converted {rows:,} rows of z.txt")
        if writer is None:
            raise ValueError(f"Empty source matrix: {source.name}")
    finally:
        if writer is not None:
            writer.close()


def _verify_converted(destination):
    receipt_path = destination / "zenodo-source.json"
    if not receipt_path.is_file():
        return False
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("record_id") != RECORD or receipt.get("converter_version") != _CONVERTER:
        raise ValueError(f"Incompatible Zenodo source receipt: {receipt_path}")
    if receipt.get("files") != _catalog()["files"]:
        raise ValueError(f"Source receipt does not match the pinned Zenodo file catalog: {receipt_path}")
    expected = {f"{name}.parquet" for name in REQUIRED}
    if set(receipt.get("parquet_sha256", {})) != expected:
        raise ValueError(f"Incomplete Zenodo source receipt: {receipt_path}")
    for name, digest in receipt["parquet_sha256"].items():
        if not (destination / name).is_file() or _hash(destination / name) != digest:
            raise ValueError(f"Converted source checksum mismatch: {destination / name}")
    return True


def download_database(destination=DEFAULT_DIRECTORY, *, progress=print):
    """Return a verified local parquet directory. A complete cache needs no network.

    Downloaded original TXT files are retained in zenodo-txt/ for transparency and
    retry. Existing unmanaged parquet directories are never overwritten.
    """
    destination = Path(destination).expanduser().resolve()
    if _verify_converted(destination):
        progress(f"Using verified Zenodo source: {destination}")
        return destination
    state = destination / ".zenodo-download.json"
    if state.exists() and json.loads(state.read_text()) != {"record_id": RECORD, "converter_version": _CONVERTER}:
        raise ValueError(f"Incompatible incomplete download: {state}")
    if any(destination.glob("*.parquet")) and not state.exists():
        raise ValueError(f"{destination} contains unmanaged parquet files; choose an empty download directory")
    destination.mkdir(parents=True, exist_ok=True)
    catalog = _catalog()
    state.write_text(json.dumps({"record_id": RECORD, "converter_version": _CONVERTER}) + "\n")
    original = destination / "zenodo-txt"
    original.mkdir(exist_ok=True)
    files = {entry["key"]: entry for entry in catalog["files"]}
    progress(f"Zenodo {RECORD}: six source files, {sum(f['size'] for f in files.values()) / 1e9:.2f} GB on first download")
    for stem in REQUIRED:
        _download_file(files[f"{stem}.txt"], original, progress)
    output_hashes = {}
    for stem in REQUIRED:
        progress(f"Converting {stem}.txt to Parquet")
        part = destination / f"{stem}.parquet.part"
        _convert(original / f"{stem}.txt", part, progress)
        os.replace(part, destination / f"{stem}.parquet")
        output_hashes[f"{stem}.parquet"] = _hash(destination / f"{stem}.parquet")
    receipt = {**catalog, "converter_version": _CONVERTER, "parquet_sha256": output_hashes}
    temp = destination / "zenodo-source.json.part"
    temp.write_text(json.dumps(receipt, indent=2) + "\n")
    os.replace(temp, destination / "zenodo-source.json")
    state.unlink()
    progress(f"Source database ready: {destination}")
    return destination


def _complete_source(cfg):
    extension = "parquet" if cfg["base_db"].get("format", "parquet") == "parquet" else "txt"
    root = Path(cfg["base_db"]["_path"])
    for name in REQUIRED:
        path = root / f"{name}.{extension}"
        if not path.is_file() or path.stat().st_size == 0:
            return False
        if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
            return False
    return True


def source_config(cfg, *, download=True, directory=DEFAULT_DIRECTORY, progress=print):
    """Select an existing local source or obtain the fixed source when missing."""
    if _complete_source(cfg):
        return cfg
    directory = Path(directory).expanduser().resolve()
    if download:
        path = download_database(directory, progress=progress)
    else:
        if not _verify_converted(directory):
            raise FileNotFoundError("Source database unavailable in offline mode. Run pv-hlca download first "
                                    "or supply an existing --base-db directory.")
        path = directory
        progress(f"Using verified Zenodo source: {path}")
    updated = copy.deepcopy(cfg)
    updated["base_db"].update({"_path": path, "format": "parquet",
                               "zenodo": f"https://zenodo.org/records/{RECORD}"})
    return updated
