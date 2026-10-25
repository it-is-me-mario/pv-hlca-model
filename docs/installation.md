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

The fixed source is [Zenodo record 18744457](https://doi.org/10.5281/zenodo.18744457).
Use the **SUT coefficient** parquet directory, containing `z.parquet`, `v.parquet`,
`e.parquet`, `Y.parquet`, `EY.parquet`, `units.parquet` and `VY.parquet` when present.
Do not substitute a newer database version in a reproduction run.

- Put the files in `inputs/db_from_zenodo/`, or pass `--base-db /path/to/the/files`.
- A Git checkout includes some files directly and large ones through Git LFS;
  `git lfs pull` retrieves the actual large objects.
- A small text file beginning `version https://git-lfs...` is a pointer, not the
  database. The model reports this before attempting to parse it.

```bash
pv-hlca prepare --base-db /path/to/SUT/parquets --prepared models/prepared
pv-hlca run examples/eu_reshoring.yaml --prepared models/prepared
```

If you receive a prepared bundle, the second command needs no raw input directory.
Preparation and model calculation are full MRIO operations; the first build is
more expensive than loading a prepared model. Runtime depends on your hardware.
