# PV-HLCA — hybrid LCA of the solar-PV supply chain

Reproducible pipeline for the paper *"Extending EXIOBASE through explicit solar PV
supply-chain modelling: implications for the EU Net Zero Industry Act"* (Merletti et al.).

It embeds an explicit photovoltaic (PV) supply chain into a hybrid-units MRIO
(EXIOBASE extended with hydrogen and green steel) and computes the carbon footprint,
price, production, value added and employment of solar electricity across world regions
and policy scenarios, on `mario==1.0.0`. The whole study is **parametric**: each modelling
choice is a named lever and the analysis is a global sensitivity sweep over their values.

## Quick start

```bash
conda env create -f environment.yml
conda activate pv_hlca
```

Download the base hybrid-units database from **Zenodo record 18744457**
(<https://zenodo.org/records/18744457>) and place its SUT parquet files in
`inputs/db_from_zenodo/` (the folder is git-ignored; the path is set in `config/paths.yaml`).
Then either open the notebook, which runs everything from the raw database to the figures, or
use the headless drivers:

```bash
jupyter lab notebooks/PV_HLCA_pipeline.ipynb   # full pipeline, A→Z (parse → figures)

python run_sensitivity.py            # paper sensitivity design -> outputs/sensitivity/
python run_sensitivity.py --heavy    # + disaggregated footprint & decomposition data (all figures)
python run_sensitivity.py --quick    # central case only (smoke test)
python make_figures.py               # figures as paper-numbered TIFFs (Figure2 … Figure9)
```

The central (reference) case is OWID capacity factors, the WEO_STEPS 2030 grid applied to
both the EU27 and China, 19.5 % module efficiency, no degradation, and the IEA PVPS upstream
inventory; every other point of the analysis is a one-lever variation around it.

## Pipeline

```
base hybrid-units SUT (Zenodo 18744457, parquet)
  └─ aggregate ............ 48→22 regions + value-added (8→4) + satellite (363→25)
  └─ add_sectors .......... insert the PV activities / commodities (Add_sectors.xlsx)
  └─ solar shock .......... capacity-factor scaling, IRENA value added, module efficiency
  └─ remove legacy Solar .. Solar Power Plant becomes the sole producer of 'Solar'
  └─ scenarios ............ domestic · baseline (real trade) · NZIA · baseline_2030
  └─ indicators ........... footprint, price, X / V / E, disaggregated f_dis / p_dis
```

Headline output: per-region solar-electricity footprint in gCO₂eq/kWh, plus the
production / value-added / employment effects of the reshoring and 2030-grid scenarios.

## Sensitivity levers

Each modelling choice is a named lever (a field of `Params`, see `src/pv_hlca/params.py`):

| lever | values | meaning |
|---|---|---|
| `capacity_factor` | `OWID`, `RN` | source of the regional solar-yield scaling |
| `module_efficiency` | `0.195`, `0.22`, `0.24` | PV module efficiency (scales area-proportional inputs) |
| `degradation_rate` | `0.0`, `0.005` | annual PV power degradation (0 = constant output) |
| `lci_variant` | `IEA`, `NREL` | upstream-stage electricity inventory |
| `upstream_reshoring` | `None`, `0.0 … 1.0` | forced EU domestic share of the upstream PV stages (NZIA) |
| `electricity_mix` | `WEO_STEPS`, `EMBER` | source of the projected 2030 grid (central: WEO_STEPS, EU27 + China) |

`export.sensitivity_grid()` is the design used in the paper: a one-at-a-time sweep around the
central case plus a 0→100 % upstream-reshoring scan. `export.default_grid()` is the full
Cartesian product, and `grid(Params(), <axis>=[...])` builds any custom design. The hybrid
base depends only on (`capacity_factor`, `degradation_rate`); the export rebuilds it once per
such group and reuses it across the cheaper scenario levers.

## Outputs

`export.run_and_export` writes tidy tables to `outputs/sensitivity/`, each row tagged with
every lever and the scenario:

| file | matrix | content |
|---|---|---|
| `footprints.csv` | f | region solar-electricity footprint (gCO₂eq/kWh) |
| `prices.csv` | p | region solar-electricity price (EUR/kWh) |
| `production.csv` | X | output of the PV commodities, per region |
| `value_added.csv` | V | value added by production factor and region |
| `employment.csv` | E | employment by region and activity |
| `headline.csv` | — | EU total value added and global CO₂eq, per run |
| `f_dis_solar.parquet` | — | disaggregated solar footprint (heavy export only) |
| `fc_ex_<scenario>.parquet` | — | per-stage exploded footprint (`write_decomposition_data`) |
| `onestep_<scenario>.parquet` | — | one-step impact-linkage decomposition (`write_onestep_data`) |

`figures.make_all` turns these into the publication figures (`outputs/figures/`), each saved
as PNG (200 dpi) and TIFF (600 dpi). `make_figures.py` additionally saves them under the
paper figure numbers (`Figure2.tiff … Figure9.tiff`).

## Layout

```
config/      paths.yaml, parameters.yaml (IRENA, GWP, 195 W/m², …), mappings.yaml,
             import_structure.csv (baseline + NZIA), scenario_2030.yaml, capacity_factor_row.yaml
data/        Add_sectors.xlsx, Aggregate_VA_SA_and_regions.xlsx, Mapping_activities.xlsx,
             capacity-factor inputs (Renewables Ninja + frozen OWID multipliers)
inputs/      db_from_zenodo/ — base hybrid-units SUT (download from Zenodo; git-ignored)
src/pv_hlca/ io · hybridize · scenarios · indicators · export · figures · params · pipeline
notebooks/   PV_HLCA_pipeline.ipynb — the full pipeline (also a template for new analyses)
run_sensitivity.py   headless driver for the sensitivity grid
validate.py          build + compare the baseline footprint to the reference results
reference/   per-region reference footprints / prices (for validation)
outputs/     generated results and figures (git-ignored)
```

Hard-coded parameters of the reference implementation are externalised to `config/`
(`extract_support_data.py` regenerates them).

## Implementation notes (mario 1.0.0)

- **SUT scenarios are stored as coefficient blocks** `u, s, va, vc, ea, ec, Ya, Yc`;
  `z` is derived. Every trade/technology shock therefore edits the **use block `u`**
  (Commodity→Activity), then `update_scenarios(scenario, u=…)` + `reset_to_coefficients`.
- **`aggregate(..., zero_output_epsilon=None)`** — *required*. With the mario 1.0.0
  default (`1e-30`) the SUT zero-output flow override divides non-zero hybrid-unit supply
  by epsilon during the coefficient↔flow round-trip, yielding market shares `s` ~1e38, a
  singular Leontief inverse and globally degenerate footprints. `None` is the fix.
- **Legacy `Solar` activity** is neutralised in place (zero `u`/`s`/`va`/`ea`) rather than
  dropped from the index — a second `aggregate` drop corrupts the supply market share in
  1.0.0, so `Solar Power Plant` is left as the sole producer of the `Solar` commodity.

## Validation

`validate.py` rebuilds from Zenodo 18744457 and compares the baseline solar footprint to
the reference results. The downstream pipeline (scenarios + indicators) was additionally
cross-checked on `mario==0.3.5` against the reference, matching to 0.00% (RN capacity
factor). The full rebuild on 18744457 agrees within a declared tolerance (it is not
bit-exact, because the base-DB version differs from the one used for the original results).

## Environments

- `environment.yml` — `mario==1.0.0` (primary).
- `environment-cross-check.yml` — `mario==0.3.5` (verification only).
