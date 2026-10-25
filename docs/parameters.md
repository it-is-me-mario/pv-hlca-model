# Technology parameters

`ModelParameters` describes technology assumptions shared across an experiment.
Build or load a new model to change them; scenario operations do not change these
assumptions halfway through a comparison.

| Parameter | Default | Effect |
|---|---|---|
| `capacity_factor` | `OWID` | Choose the frozen regional solar-yield multipliers; alternative `RN` uses Renewables Ninja. |
| `module_efficiency` | `0.195` | Scale area-dependent plant inputs by `0.195 / efficiency`. For example, `0.22` means 22%. |
| `degradation_rate` | `0.0` | Annual fractional power loss; `0.005` means 0.5%/year over the configured lifetime. |
| `lci_variant` | `IEA` | Use the reference upstream-electricity inventory or `NREL` stage-specific electricity intensities. |

Efficiency must be greater than zero and at most one; degradation must be at least
zero and less than one. Values must be finite. These checks enforce mathematical
validity, rather than scientific plausibility for every value in that interval.
The published sensitivity analysis considered efficiencies 0.195, 0.22 and 0.24,
and degradation rates 0 and 0.005. Extrapolations remain the analyst's assumptions.

Module efficiency changes the area-dependent PV-module and end-of-life inputs.
It leaves the IRENA-based plant value-added coefficients unchanged, following the
model's existing formulation. Degradation scales lifetime-normalised inputs by
the inverse mean lifetime yield, including regional solar-yield scaling.
The NREL variant changes upstream electricity intensity while preserving the
regional electricity mix. Inventories in the Excel workbook remain unchanged.

`config/parameters.yaml` documents underlying constants: 25-year lifetime, IRENA
cost assumptions, exchange rate, GWP factors and reference inventory intensities.
Changing these is an advanced change to the model specification; some quantities
are calibrated together in the inventory. It is not equivalent to changing the
four supported experiment parameters independently. Document and validate those
changes before interpreting results.

Policy choices belong in [scenario definitions](scenarios.md), including the
electricity-mix source and upstream reshoring. The legacy `Params` object keeps
these fields together for the original sensitivity and paper commands. Both
paths use the same technology transformations, including degradation and LCI.
