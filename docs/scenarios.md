# Define scenarios

Each `Scenario` starts independently from a preset under the experiment's shared
technology parameters. `baseline` and `domestic` are reserved database names.
Choose a new name for every added scenario.

## Reference presets

| `preset` | Starting point and changes |
|---|---|
| `baseline` (default) | Hybrid PV model with the frozen observed trade structure. |
| `domestic` | Pre-trade PV template: local PV supply-chain production. |
| `baseline_2030` | Commercial baseline plus the published 2030 grid and EU household-demand prescription. |
| `NZIA` | Published PV sourcing, EU transport and construction assumptions, plus the same 2030 grid/demand prescription. |

For the 2030 presets, `grid_source` selects `WEO_STEPS` (EU27 and CN) or `EMBER`
(EU27). The existing demand addition is EU-calibrated. With the NZIA preset,
`upstream_reshoring: 0.6` sets the EU share of all five upstream PV commodities.
The preset constants are visible in `config/scenario_2030.yaml` and trade data in
`config/import_structure.csv`.

After constructing the preset, the model applies your custom trade changes,
then your custom electricity changes. An explicit `electricity_demand_tj` value
adds to the demand already present in that preset. Use `baseline` for an
experiment that does not include the paper's 2030 demand increment.

## Domestic shares

```yaml
- name: eu_modules_and_cells
  domestic_shares:
    EU27:
      PV modules: 0.60
      Cells: 0.40
```

This redistributes the intermediate use of the selected PV commodities by EU
activities. Each activity's total input of that commodity is conserved. Remaining
foreign shares retain their relative proportions. If an activity starts with no
foreign sourcing, the frozen baseline foreign structure is used as a fallback;
if none exists, specify suppliers explicitly.

Valid commodities: `PV modules`, `Cells`, `Wafer`, `Ingot`, `Solar Grade silicon`,
`Metallurgical Grade silicon`. Region codes are the model's 22 aggregate regions;
inspect them with `model.db.get_index("Region")`.

## Explicit suppliers

```yaml
- name: eu_module_suppliers
  sourcing:
    EU27:
      PV modules:
        EU27: 0.60
        CN: 0.30
        WA: 0.10
```

Keys are **importing region → commodity → supplying region → share**. Missing
suppliers receive zero. Shares must sum to one. Do not give both `sourcing` and
`domestic_shares` for the same region and commodity. These operations change
intermediate sourcing, leaving final-demand sourcing unchanged.

## Custom electricity mixes

```yaml
- name: eu_cleaner_grid
  electricity_mix:
    EU27:
      Nuclear: 0.20
      Solar: 0.30
      Wind: 0.40
      Hydro: 0.10
  electricity_demand_tj:
    EU27: 3600
```

A custom mix specifies the domestic electricity inputs used by that region's
activities and final consumers. It preserves each column's total domestic
electricity input before the separate demand addition; imported electricity is
unchanged. Omitted sources receive zero, including a source present in the
starting mix. The demand addition is TJ allocated to household final demand.

Valid sources: `Coal`, `Gas`, `Other Fossil`, `Nuclear`, `Solar`, `Wind`, `Hydro`,
`Bioenergy`, `Other Renewables`. A source initially absent can receive a positive
share if the corresponding model commodity exists.

**Custom mix replacement and the published grid prescription are distinct
operations.** The paper presets retain the original source-specific rescaling
based on household electricity shares. Custom replacement enforces the supplied
shares and conserves each column's total. This allows new experiments without
silently changing the published scenario formulas.
