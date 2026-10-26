# Use the model

An experiment combines **technology parameters shared by all its scenarios** with
**independent scenario definitions**. Every scenario starts from its selected
preset; scenarios listed later do not inherit changes from earlier ones.

## 1. Install and obtain a prepared model

Follow [installation](installation.md). If you received a complete prepared bundle
from a collaborator using this code version, place it at `models/prepared/`.
Otherwise the first `run` downloads any missing source from the fixed Zenodo record
(1.78 GB), verifies it, converts its TXT matrices and prepares the model automatically.
You can also download and prepare it explicitly:

```bash
pv-hlca download
pv-hlca prepare --offline --prepared models/prepared
```

Preparation is the expensive step. The bundle is independent of technology
parameters, trade scenarios and grid assumptions. It contains coefficient parquet
files and a manifest recording source checksums and the preparation recipe.
Subsequent runs can use `--offline`; no download is needed with a matching prepared
bundle. Existing source Parquets remain supported through `--base-db /path/to/SUT/parquets`.

## 2. Define an experiment

Copy `examples/eu_reshoring.yaml` to `examples/my_experiment.yaml`. For example:

```yaml
title: My PV supply-chain experiment
parameters:
  capacity_factor: OWID
  module_efficiency: 0.22
  degradation_rate: 0.005
  lci_variant: IEA
scenarios:
  - name: eu_modules_60
    domestic_shares:
      EU27:
        PV modules: 0.60
```

Fractions are entered as `0.60`, not `60`. Each sourcing distribution and electricity
mix must sum to one. Unknown fields, invalid fractions and duplicate scenario
names are rejected. The database's region labels are checked when loading it.

```bash
pv-hlca check examples/my_experiment.yaml
pv-hlca run examples/my_experiment.yaml --output outputs/my_experiment
```

You can also use `python run_model.py` in place of `pv-hlca` from the repository root.

## 3. Compare outcomes

| Table | Main result | Unit |
|---|---|---|
| `footprints.csv` | PV-electricity footprint by producing region | gCO2eq/kWh |
| `prices.csv` | PV-electricity producer price by region | EUR/kWh |
| `production.csv` | Production by region and PV commodity | `unit` column: m2 or kg for the PV stages |
| `value_added.csv` | Value added by region and factor | M EUR |
| `employment.csv` | Employment by region and activity | `unit` column: 1000 persons |
| `headline.csv` | EU value added and global GHG emissions | M EUR and tonnes CO2eq |

These are model indicators, including embodied supply-chain effects. Producer
prices are model-implied prices, rather than a complete project-finance LCOE.
Economy-wide totals should be compared between scenarios sharing the same
technology parameters and demand assumptions.

```python
import pandas as pd

f = pd.read_csv("outputs/my_experiment/footprints.csv")
comparison = f.pivot(index="region", columns="scenario", values="footprint_gkwh")
comparison["change_percent"] = 100 * (comparison.eu_modules_60 / comparison.baseline - 1)
print(comparison.loc[["EU27", "CN"]])
```

`run.json` records technology parameters, scenario specifications, prepared-model
provenance and units. `experiment.json` records the validated input experiment.
Use `--heavy` for the disaggregated solar footprint. A non-empty output directory
is protected unless you explicitly pass `--overwrite`.

## 4. Go beyond the configuration

Open [Use_the_model.ipynb](../notebooks/Use_the_model.ipynb) to inspect, change and plot
an experiment interactively. `model.db` exposes the MARIO Database so you can query
matrices, add other shocks or calculate additional indicators. Record direct
database edits alongside your analysis: the YAML manifest only describes changes
made through the scenario interface.

See [parameters](parameters.md), [scenarios](scenarios.md), [API](api.md) and
[database preparation](database-preparation.md) for the next level of detail.
