"""Resolve the versioned background data for an installed PV project."""

from hashlib import file_digest
from importlib.resources import files
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import yaml


def manifest():
    resource = files("pv_hlca").joinpath("resources", "database.yaml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _matches(path, digest):
    return path.is_file() and sha256(path) == digest


def _download(url, destination, digest):
    with NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
        partial = Path(stream.name)
        try:
            with urlopen(url, timeout=90) as response:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            stream.close()
            if not _matches(partial, digest):
                raise OSError(f"SHA-256 mismatch for {url}")
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)


def resolve_data(spec, workspace, cache_dir, *, download):
    """Use a verified local copy or retrieve the pinned background data."""
    source = manifest()
    if spec["source"] != source["id"]:
        raise ValueError(f"Unsupported background {spec['source']!r}. Use {source['id']!r}.")
    local_path = spec["path"]
    if local_path is None:
        root = cache_dir / source["id"] / source["revision"]
    else:
        root = (workspace / Path(local_path).expanduser()).resolve()

    for name, checksum in source["files"].items():
        destination = root / name
        if _matches(destination, checksum):
            continue
        if local_path is not None:
            raise ValueError(f"Missing or different background file: {destination}")
        if not download:
            raise FileNotFoundError(f"Missing or invalid {destination}. Run model.fetch_data() first.")
        root.mkdir(parents=True, exist_ok=True)
        host = "media.githubusercontent.com/media" if name in source["lfs_files"] else "raw.githubusercontent.com"
        url = f"https://{host}/{source['repository']}/{source['revision']}/{source['directory']}/{name}"
        _download(url, destination, checksum)
    return root
