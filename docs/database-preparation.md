# Database preparation and provenance

Preparation is accessible for transparency and reproduction, while the main user
workflow operates on the prepared model, technology parameters and scenarios.

```text
Zenodo 18744457: EXIOBASE-based hybrid-units SUT, extended with H2 and steel
  → download six TXT files, verify published size/MD5 and convert to Parquet
  → aggregate to 22 regions, value-added categories and satellite accounts
  → insert explicit PV activities and commodities from Add_sectors.xlsx
  → add the GHG satellite with the configured GWP factors
  → save parameter-independent prepared coefficients and manifest

Prepared model
  → regional yield, degradation, module efficiency and inventory assumptions
  → neutralise the legacy aggregate Solar activity
  → retain the domestic template and construct the observed-trade baseline
  → independent user scenarios
  → indicators and comparisons
```

## Source files

| File | Role |
|---|---|
| `config/paths.yaml` | Source database, input workbooks, reference and output paths |
| `config/zenodo-source.json` | Fixed source record, six file URLs, sizes and published checksums |
| `data/Aggregate_VA_SA_and_regions.xlsx` | Aggregation mappings |
| `data/Add_sectors.xlsx` | PV supply-chain activities, commodities and inventories |
| `config/parameters.yaml` | GWP, cost, lifetime and inventory constants |
| `config/mappings.yaml` | Regional names and parent activities for regionalisation |
| Frozen capacity-factor CSVs in `data/` | Regional yield alternatives |
| `config/import_structure.csv` | Baseline and NZIA sourcing assumptions |
| `config/scenario_2030.yaml` | Grid/demand sources and NZIA transport/construction constants |

The model retains the existing hybrid units and regional/technological scope.
Substituting another IO database or adding a PV technology requires updating and
validating the associated mappings and inventories.

## Automatic source acquisition

`pv-hlca download` writes `models/source-18744457/` by default. The record's TXT
matrices use comma-separated values with three column-header levels; they are
converted in row chunks with round-trip float parsing. The cache contains:

```text
models/source-18744457/
  zenodo-txt/        # verified originals; .part files allow interrupted downloads to resume
  *.parquet         # z, v, e, Y, EY and units
  zenodo-source.json # pinned source metadata, converter version, converted-file SHA-256 hashes
```

Only verified downloads are converted. The completion receipt is written after
all six Parquets are complete; subsequent use verifies their hashes without
contacting Zenodo. Downloaded source checksums are retained in this receipt;
the preparation manifest separately records the converted input hashes.
Existing local source directories and prepared bundles take precedence. See
[installation](installation.md) for cache paths and offline operation.

## Prepared bundles

`pv-hlca prepare --prepared models/prepared` writes:

```text
models/prepared/
  coefficients/     # MARIO-readable parquet matrices and units
  manifest.json     # stage, source, input hashes, recipe and coefficient hashes
```

Technology and scenario assumptions are applied **after** this boundary. Changing
module efficiency or trade assumptions therefore reuses the same preparation.
The manifest records the MARIO version, preparation code, aggregation and inventory
workbook hashes, GWP factors and original parquet checksums. Loading verifies the
recipe and coefficient checksums. An incompatible or incomplete bundle is rejected;
prepare a new one in another directory. The original base files are not needed
to load an existing bundle. Prepared bundles are currently generated locally or
shared as complete matching bundles by collaborators.

## MARIO 1.0.0 compatibility

The original formulation uses SUT coefficient blocks `u`, `s`, `va`, `vc`, `ea`,
`ec`, `Ya` and `Yc`. `z` is derived; scenario edits update native blocks and reset
to coefficients. Aggregation explicitly uses `zero_output_epsilon=None` to avoid
the original zero-output round-trip issue. The legacy Solar activity is neutralised
in place rather than removed through another aggregation. These compatibility
choices are retained, not silently changed while introducing the user interface.
Preparation also restores missing unit entries from the source metadata before
export. In particular, the retained cement CO2 satellite keeps its original kg
unit, distinct from the aggregated Carbon dioxide account in tonnes. Numeric
coefficients are unchanged by this metadata repair.

For historical results and the distinction between the archived study and the
older thesis baseline, see [Reproduce the paper](../paper/README.md).
