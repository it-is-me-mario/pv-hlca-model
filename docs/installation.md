# Installation and data

Use Python 3.12 in a dedicated environment. From the repository root:

```bash
conda env create -f environment.yml
conda activate pv_hlca
python tools/install.py
pv-hlca check examples/eu_reshoring.yaml
```

Alternatively, with Python 3.12 already installed:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python tools/install.py
```

The installer installs `requirements-model.txt`, then MARIO 1.0.0 and this project
in editable mode. For the interactive notebook, also install JupyterLab if it is
not already available in the environment.

## Why is MARIO installed separately?

The PyPI metadata of `mariopy==1.0.0` pins pandas 3.0.2 and requires cvxlab, whose
available distribution pins pandas 2.3.3. A normal dependency resolution cannot
satisfy both. PV-HLCA uses MARIO's IO calculations without cvxlab optimisation.
`tools/install.py` therefore installs the explicit PV runtime first, then the
engine with `--no-deps`. The engine version remains 1.0.0. This workaround is
scoped to this model environment; optional cvxlab workflows are not installed.
`pip check` will still report MARIO's unsatisfied optional-optimisation requirement.

## Obtain the source database

No manual data setup or Zenodo account is needed. If neither a prepared bundle
nor complete local source files are available, `pv-hlca prepare` and `pv-hlca run`
download the six required files from the fixed
[Zenodo record 18744457](https://doi.org/10.5281/zenodo.18744457).
The record provides **comma-separated TXT matrices**, not Parquet. The downloader
verifies the published file sizes and MD5 checksums, then converts them to Parquet
in row chunks. It does not download the diagnostic ZIP or PDF. `VY` is absent
from this source and is handled by MARIO as in the original model.

The first download is **1.78 GB** and may take several minutes, depending on your
connection, before preparation and calculation begin. Allow about **3 GB of free
disk space** for retained original TXT files, converted matrices and the prepared
bundle, plus space for your outputs. The original TXT files are kept for provenance.
Interrupted transfers resume when you rerun the same command.

```bash
pv-hlca run examples/eu_reshoring.yaml
```

To download ahead of time, or place the source cache on another disk:

```bash
pv-hlca download --output /path/to/source-18744457
pv-hlca prepare --download-dir /path/to/source-18744457 --offline
pv-hlca run examples/eu_reshoring.yaml --offline
```

The default source cache is `models/source-18744457/`, relative to the working
directory. A completed cache is reused without network access and its Parquet
SHA-256 hashes are checked before reuse. `--offline` prohibits downloads and gives
an actionable error when neither a prepared bundle nor a valid local source exists.
The checked-in `config/zenodo-source.json` pins the record, download URLs, sizes and
checksums: no lookup of a changing “latest” record occurs.

### Existing local files

A complete **SUT coefficient** Parquet directory can still be used directly:
`z.parquet`, `v.parquet`, `e.parquet`, `Y.parquet`, `EY.parquet`, `units.parquet`
and optional `VY.parquet`. Place it in `inputs/db_from_zenodo/` or pass `--base-db`.
An explicit `--base-db` selects local files and disables automatic download fallback.
Do not substitute a newer database version in a reproduction run.

Some original files are tracked directly in Git and the large matrix uses Git LFS.
`git lfs pull` is an alternative when those objects are available. LFS pointers
are detected as missing data by the automatic workflow; they are never parsed
as matrices. Downloads go to their own cache and do not overwrite tracked inputs
or existing unmanaged Parquet directories.

```bash
pv-hlca prepare --base-db /path/to/SUT/parquets --prepared models/prepared
pv-hlca run examples/eu_reshoring.yaml --prepared models/prepared
```

If you receive a prepared bundle, the second command needs no raw input directory
or network access. Adding the downloader does not invalidate existing prepared bundles.
Preparation and model calculation are full MRIO operations; the first build is
more expensive than loading a prepared model. Runtime depends on your hardware.
