# Verification — 25–26 October 2026

These checks cover the reusable-model development. They do not claim that every
published sensitivity combination or every historical notebook was rerun.

## Executed checks

| Check | Result |
|---|---|
| Fast tests | 54 passed; two external-data tests are skipped unless explicitly enabled |
| Downloader contracts | Resume and ignored Range responses, retries, checksum rejection, real chunked conversion, verified cache reuse, offline failure, LFS detection, local-file protection and model/CLI wiring |
| Full-database contracts | Two passed using a prepared bundle built from the existing Zenodo 18744457 coefficient files |
| New user notebook | All seven code cells executed, including scenario creation, six indicator tables, plot and export |
| Custom grid CLI experiment | Both scenarios executed in a clean environment, including zero coal share, explicit suppliers and separate demand addition |
| Paper presets | All four presets recalculated at reference technology assumptions; six result tables compared with the existing study outputs |
| Installation | `tools/install.py` succeeded in a fresh Python 3.12 venv without inherited site packages |
| Distribution | Wheel built; installed wheel loaded its bundled resources and the prepared model from outside the checkout |
| Existing bundle compatibility | The previously generated 22-region bundle still loads with the downloader changes; preparation recipe unchanged |
| Documentation | Local Markdown links, notebook syntax and whitespace checked |

The full-database contracts verify that the bundle loads without access to the
raw source directory, that degradation and NREL electricity intensity affect the
expected coefficients, and that **single construction and batch sensitivity
produce matching native coefficient blocks**. The latter uses RN capacity factors,
22% efficiency, 0.5% degradation, NREL inventory, EMBER grid and 60% upstream sourcing.
The invariant preparation stage is loaded from the same verified bundle in both
paths; native transformations and scenario construction run normally.

The model notebook is saved with its executed outputs. The README image is taken
from that execution. No machine-specific source paths are embedded in the notebook.
Those saved outputs are from 25 October; the 26 October edit documents automatic
acquisition and sets its cache path, without changing the experiment or rerunning
the seven cells.

## Source acquisition — 26 October 2026

All six required TXT files were downloaded from the public fixed record, with
their sizes and published MD5 checksums verified. The automatic converter produced
the six source Parquets. Every row/column label and unit was compared with the
previously available local Parquets; all numeric cells were compared at
`rtol=1e-12, atol=1e-15`. Maximum absolute difference was **5.30e-23** in native
coefficient units, attributable to float parsing. The matrices are numerically
equivalent within this tolerance, rather than byte-identical files. See the
[source comparison](../verification/zenodo-source-comparison.json).
The optional local `VY` matrix is entirely zero; the source record omits it and
MARIO supplies the same zero default.

A fresh preparation and experiment then ran **outside the checkout, from an
installed wheel, in offline mode**, using only this verified source cache. The
previous prepared bundle was not used. Baseline and a custom 60% EU module-sourcing
scenario exported all six tables; their hashes and input provenance were verified.
The new baseline agrees with the previous prepared-model run at `rtol=1e-8`,
`atol=1e-9`, with the same explicit `0.001` thousand-person employment tolerance.
See the [end-to-end report](../verification/zenodo-end-to-end.json).
Fresh preparation plus calculation took **10 min 14 s** on the validation machine,
excluding download and conversion; this is not a hardware-independent runtime bound.

## Agreement with the existing study tables

The [machine-readable comparison](../verification/study-comparison.json) reports
coverage, tolerances and maximum differences for all six tables. It compares the
four reference presets, not the older thesis CSVs used by `validate.py`.

- Footprints: 88 rows, maximum difference **3.18e-8 gCO2eq/kWh**.
- Prices: 88 rows, maximum difference **2.82e-10 EUR/kWh**.
- Production: 528 rows; value added: 352 rows; headline totals: four rows.
  These also pass `rtol=1e-8, atol=1e-9` in their native units.
- Employment: 18,040 rows, maximum difference **0.0001248 thousand persons**, or
  **0.125 persons**. This table does **not** pass the strict comparison above.
  Its explicit absolute acceptance tolerance is **0.001 thousand persons (one
  person)**, with the same relative tolerance. The report retains both results.

This is numerical agreement within the stated tolerances, not bit-exact identity.
Archived study outputs, input inventories, reference CSVs and the original full
pipeline notebook have not been overwritten by the development verification.
The satellite coefficients were also checked to be exactly unchanged by the
source-unit metadata repair required for prepared-model export/reload.

## Repeat the checks

```bash
python -m pip install pytest
python -m pytest -q
python tools/check_docs.py

PV_HLCA_PREPARED=/path/to/prepared python -m pytest -q tests/test_full_model.py

pv-hlca run examples/paper_presets.yaml --prepared /path/to/prepared --output outputs/preset_check
python tools/compare_study.py outputs/preset_check --report outputs/preset_check/comparison.json
```

CI runs the fast contracts, documentation checks and wheel build without
downloading the full external database. The full sensitivity grid, heavy
disaggregated exports, original A-to-Z notebook and MARIO 0.3.5 historical
cross-check were not executed in this development pass.

The published citation target remains
[Zenodo 20734983 / tag 1.0.1](https://doi.org/10.5281/zenodo.20734983).
