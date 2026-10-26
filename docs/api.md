# Python API

```python
from pv_hlca import PVModel, ModelParameters, Scenario, Experiment
```

## Model parameters

`ModelParameters(capacity_factor="OWID", module_efficiency=0.195,
degradation_rate=0.0, lci_variant="IEA")` validates technology assumptions.
See [parameter meanings and limits](parameters.md).

## Load or build a model

```python
parameters = ModelParameters(module_efficiency=0.22)
model = PVModel.load("models/prepared", parameters)
```

- `PVModel.load(path, parameters=None, *, cfg=None)` verifies and loads an existing
  bundle. It does not read the original base database.
- `PVModel.build(parameters=None, *, cfg=None, prepared_path=None, download=True,
  source_path=None)` builds from source; if `prepared_path` is supplied it creates
  or reuses that bundle. Missing sources are downloaded from the fixed Zenodo
  record and converted automatically. `source_path` selects the download cache
  (default `models/source-18744457`). Set `download=False` for offline operation.
  An existing prepared bundle does not need source acquisition.
- `io.load_config(path=None, *, base_db=None)` loads advanced source configuration.
  Relative paths in a custom `config/paths.yaml` resolve against its parent root,
  matching the repository layout. `base_db` overrides only the raw input directory.

```python
from pv_hlca import io
cfg = io.load_config(base_db="/path/to/SUT/parquets")
model = PVModel.build(parameters, cfg=cfg, prepared_path="models/prepared", download=False)
```

Or start with no database files:

```python
model = PVModel.build(parameters, prepared_path="models/prepared")
```

`pv_hlca.download.download_database(destination="models/source-18744457")`
downloads, verifies and converts only the source, returning its resolved path.
It reuses a verified complete cache offline. Preparation remains a separate stage.

## Add independent scenarios

`Scenario(name, preset="baseline", grid_source="WEO_STEPS",
upstream_reshoring=None, domestic_shares={}, sourcing={}, electricity_mix={},
electricity_demand_tj={})` describes one scenario. All mapping defaults are
independent empty dictionaries. Meanings and precedence are in [scenarios](scenarios.md).

```python
model.add_scenario(Scenario(
    "eu_modules_60", domestic_shares={"EU27": {"PV modules": 0.60}}
))
```

`add_scenario` returns the model. Existing names cannot be overwritten. A failed
addition is removed; the baseline and other scenarios remain available.

## Results and MARIO access

- `model.results(names=None, *, heavy=False)` returns a dictionary of tidy
  DataFrames. By default, names are `baseline` and all scenarios you added.
  `domestic` remains available explicitly as the pre-trade reference.
- `model.export(path, *, names=None, heavy=False, overwrite=False)` writes six
  CSV tables and `run.json`. Heavy mode adds `f_dis_solar.parquet`.
- `model.db` is the underlying MARIO Database. Query matrices, clone scenarios
  and apply advanced operations directly. Pass the names of directly added
  MARIO scenarios explicitly to `results` or `export` and document those edits.

```python
db = model.db
regions = db.get_index("Region")
use = db.query(matrices="u", scenarios="baseline")
tables = model.results(["baseline", "eu_modules_60"])
model.export("outputs/python_experiment")
```

## Run a YAML experiment from Python

```python
experiment = Experiment.load("examples/eu_reshoring.yaml")
model = PVModel.load("models/prepared", experiment.parameters)
for spec in experiment.scenarios:
    model.add_scenario(spec)
tables = model.results()
```

## Preparation and legacy interfaces

`pipeline.prepare_database(cfg)` returns the parameter-independent MARIO
Database. `prepared.prepare(cfg, path)` saves or loads a verified bundle;
`prepared.load(cfg, path)` only loads. Both return `(db, manifest)`.

The original `pipeline.build_database(cfg, params=Params(), with_scenarios=True)`
continues to build all four paper scenarios. `with_scenarios=False` preserves its
historical meaning: a technology-adjusted **pre-trade** database. The public
`PVModel` baseline always has the observed trade structure. `variant=` remains
accepted for older validation callers; prefer `Params(capacity_factor=...)`.
