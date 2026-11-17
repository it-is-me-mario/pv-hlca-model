# PV-HLCA

## Publication

Rinaldi, L., Merletti, R., Citterio, C., Golinucci, N., & Rocco, M. V. (2026).
[Environmental and socio-economic implications of solar photovoltaic reshoring under the EU Net Zero Industry Act](https://doi.org/10.1007/s44498-026-00175-0).
*Journal of Industrial Ecology*.

The model adds a photovoltaic supply chain to EXIOBASE Hybrid extended with
green steel and hydrogen. It estimates regional solar electricity footprints,
prices, output, value added and employment under alternative trade and grid
assumptions.

## Install and run

With the MARIO model API available, install the model from a Python session:

    import mario
    mario.models.install("pv-hlca")

Restart Python and open a project:

    import mario

    model = mario.model_setup("pv-hlca", workspace="./pv-study")
    model.fetch_data()
    db = model.build()
    results = model.results(db, write=True)
    print(results["footprints"].query("region == 'EU27'"))

The model can also be used directly with MARIO 1.3.4:

    from pv_hlca.project import Project

    model = Project("./pv-study")

Use `mario.models.install("pv-hlca", ref="your-branch")` to install an
experimental branch, tag or full commit. To edit the code, clone the
repository, check out the branch and run `python -m pip install -e .` from
its root. Use separate Python environments for different model versions.
Set `GIT_LFS_SKIP_SMUDGE=1` when cloning if you plan to use the data cache.

## Data

The background is the [Green steel 1.3.2 release](https://doi.org/10.5281/zenodo.18744457).
The [versioned Parquet copy](https://github.com/it-is-me-mario/pv-hlca-model/tree/70c7d5a6fe52a44c88b4df1a7c74137f9e7bf75b/inputs/db_from_zenodo)
used by the model is about 250 MB. Installation includes only code and small
text inputs. `fetch_data()` downloads and checks the background matrices.
Use `build(download=True)` to fetch them as part of the build, or set
`data.path` in `config.yaml` to a folder holding the same matrices.

The default cache is `~/.cache/mario/models`. Set `MARIO_MODEL_CACHE` or pass
`cache_dir` when opening a project to share an existing cache. The prepared
SUT is reused during the current session while the input files are unchanged.

The default is the central case of the archived workflow. The repository
documents a difference between this background and the older one used for
the original reference results. See the [scientific archive](https://zenodo.org/records/20734983).

## Change model inputs

On first use, the model creates `config.yaml` and `inputs/` in the workspace.

| Parameter | Default | Meaning |
| --- | --- | --- |
| `capacity_factor` | `OWID` | Regional yield source. `RN` selects Renewables Ninja. |
| `module_efficiency` | `0.195` | Module efficiency as a fraction. |
| `degradation_rate` | `0.0` | Annual output degradation as a fraction. |
| `lci_variant` | `IEA` | Upstream electricity inventory. `NREL` selects the alternative. |
| `electricity_mix` | `WEO_STEPS` | Projection for EU27 and China. `EMBER` changes the EU27 mix. |
| `upstream_reshoring` | `null` | NZIA EU27 domestic share of upstream stages. `null` preserves reference sourcing. |

Set `parameters.module_efficiency` to `0.22` in the YAML or use
`model.build(module_efficiency=0.22)`. Python arguments override the YAML for
that run. Parameter defaults come from the installed model.

The `inputs/pv_inventory/` CSV files mirror the original inventory workbook.
`Master.csv` assigns production and inventory tables to activities. Each
inventory table lists quantities, units and the matching database items.
`inputs/aggregation/` maps labels of each MARIO classification. Alternative
groupings must retain the labels and dimensions required by the inventories,
grid assumptions, indicators and trade scenarios.

`inputs/trade_shares.csv` retains the historical headings.
The `importer` field holds the **origin** region and `exporter` the **destination**.
A negative domestic value encodes 1 minus its absolute value. Each sourcing
pattern is specific to a scenario, commodity and destination. The input
directory also holds the 2030 grid, regional capacity factors and GWP factors.

For deeper changes to the background or sector structure, adapt the pipeline
on a model branch and verify its results.

## Results and provenance

`build()` returns a standard MARIO SUT with `baseline`, `domestic`, `NZIA` and
`baseline_2030` scenarios. `results()` returns a dictionary of pandas tables.
Use `model.describe()` for indicator names, units and current parameters.
`model.docs()` gives the path to this guide from your installed version.

`model.run_directory(db)` holds the resolved YAML, a copy of the inputs and
their hashes, the background revision and file hashes, and the installed
software versions. `write=True` saves six result CSVs in its `results/` folder.
