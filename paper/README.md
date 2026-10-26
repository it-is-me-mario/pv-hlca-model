# Reproduce the paper

Rinaldi, L., Merletti, R., Citterio, C., Golinucci, N. and Rocco, M. V. (2026).
**Environmental and socio-economic implications of solar photovoltaic reshoring
under the EU Net Zero Industry Act: a hybrid input–output assessment.**
[Journal of Industrial Ecology](https://doi.org/10.1007/s44498-026-00175-0).

## Fixed research artifacts

The article's Data availability statement identifies:

- **Archived code and processed results:** [Zenodo 20734983](https://doi.org/10.5281/zenodo.20734983),
  containing `pv-hlca-model-1.0.1.zip`, corresponding to [tag 1.0.1](https://github.com/it-is-me-mario/pv-hlca-model/tree/1.0.1).
- **Base hybrid-units database:** [Zenodo 18744457](https://doi.org/10.5281/zenodo.18744457).

Those snapshots remain the citation targets. The reusable-model development on
`main` does not redefine the published version. Release 1.0.0 also remains
available. Main includes subsequent environment and figure-numbering updates.

For the historical code, use a separate checkout:

```bash
git clone --branch 1.0.1 https://github.com/it-is-me-mario/pv-hlca-model.git pv-hlca-paper
cd pv-hlca-paper
git lfs pull
```

The Zenodo ZIP is the archived distribution. Git LFS objects may need to be
retrieved separately when using GitHub's source archives; confirm the source
database files against the fixed database record before rebuilding.

## Figures from the existing study outputs

The existing `outputs/sensitivity/`, `outputs/figures/`, `reference/`, full
pipeline notebook and root study scripts are retained. In an installed current
checkout:

```bash
python make_figures.py
```

This uses the available processed outputs. Main's figure script maps panels to
the manuscript numbering: Figure2a, Figure2b, Figure3, Figure4, Figure5a-b,
Figure5c-d and Figure6. **Figure 1 is a manually created schematic**, not generated
by this code. See the archived version for its original filenames and outputs.

## Rebuild the study

After [installation](../docs/installation.md), the current sensitivity driver
also obtains missing source files through the pinned Zenodo downloader. Download
ahead of time if desired:

```bash
pv-hlca download
python run_sensitivity.py --quick --fresh  # central case only
python run_sensitivity.py --heavy --fresh # study design + decomposition data
python make_figures.py
```

Use `--offline` with `run_sensitivity.py` to require local files or a verified
download cache. This convenience belongs to the current development version;
the archived 1.0.1 scripts retain their original manual data setup.

These legacy commands keep their original output location, `outputs/sensitivity/`.
Run them in a separate checkout or copy of the study if you want to preserve the
shipped outputs. `--fresh` avoids resuming cached historical results when checking
new code. The original full workflow is in
[`PV_HLCA_pipeline.ipynb`](../notebooks/PV_HLCA_pipeline.ipynb).

Reference technology: OWID regional yields, module efficiency 0.195, no degradation,
IEA PVPS inventory. Scenario set: `domestic`, `baseline` (observed trade), `NZIA`,
`baseline_2030`; central 2030 mix source `WEO_STEPS`. The sensitivity design remains
in `export.sensitivity_grid()`. NZIA sourcing is in `config/import_structure.csv`;
transport, construction and grid/demand assumptions are in `config/scenario_2030.yaml`.
The [preparation guide](../docs/database-preparation.md) explains how the base
database and PV inventories are assembled.

## Validation means two different comparisons

1. **Current code against the fixed study outputs:** regression checks should use
   the same base database, technology parameters, scenario prescriptions and units.
   See the [verification report](../docs/verification.md) for what was actually executed.
2. **Rebuilt model against older thesis reference CSVs:** `python validate.py RN`
   compares the RN baseline footprint with those older reference values. This is
   a different reference database and a declared **10% median absolute percentage
   deviation** threshold; passing it does not establish exact reproduction of
   the article's figures or every region. The original README documented that
   distinction and a separate MARIO 0.3.5 downstream cross-check. The cross-check
   environment is retained for historical investigation, not used by the new API.

The new single-run constructor now applies degradation and the LCI variant as
the batch sensitivity driver does. The validation caller's outdated argument
has also been corrected. These fixes apply to the current code; archived
releases are unchanged. Custom electricity-mix replacement has its own documented
conservation rule; the published 2030 grid prescription remains separate.
