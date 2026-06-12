"""Sensitivity parameters for the PV-HLCA model.

Every field of :class:`Params` is one axis of the global sensitivity analysis.
The defaults reproduce the central case. A full sensitivity run is the Cartesian
product of the values supplied per axis (see ``export.run_and_export``).

Axes & references
-----------------
- ``capacity_factor``  : 'RN' (Renewables Ninja, deterministic) | 'OWID'.
- ``electricity_mix``  : 2030 grid projection source for baseline_2030 / NZIA —
  'WEO_STEPS' (IEA WEO 2025 STEPS, EU27+CN) | 'EMBER' (Ember, EU27 only).
- ``module_efficiency``: PV module efficiency. 0.195 = reference (195 W/m²);
  0.22 = current commercial c-Si weighted average (Fraunhofer ISE PV Report 2025);
  0.24 ≈ 2030 mainstream (ITRPV). Scales the area-proportional module inputs by
  ``module_efficiency_ref / module_efficiency``.
- ``upstream_reshoring``: EU27 domestic share of the *upstream* PV commodities
  (cells/wafer/ingot/silicon) in the NZIA scenario. ``None`` = reference
  (upstream stays import-dominated); a value in [0, 1] forces that EU self-share.
- ``degradation_rate``: annual PV power degradation rate. 0.0 = reference
  (constant lifetime output, as published); 0.005 = 0.5%/yr (Jordan & Kurtz 2013),
  which lowers the mean lifetime yield to eta = (1-(1-d)^N)/(N*d) and scales every
  per-TJ inventory coefficient by 1/eta (so the per-kWh footprint rises by ~6%).
- ``lci_variant``: upstream-stage electricity inventory. 'IEA' = reference
  (IEA PVPS Task 12 2020, baked into Add_sectors.xlsx); 'NREL' = scale each upstream
  stage's electricity coefficient to the NREL (Smith et al. 2024) value (SoG-Si x1.47,
  ingot x1.20, wafer x0.49). The Excel inventory is never modified.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from itertools import product
from typing import Iterable


@dataclass(frozen=True)
class Params:
    capacity_factor: str = "OWID"
    electricity_mix: str = "WEO_STEPS"
    module_efficiency: float = 0.195
    upstream_reshoring: float | None = None
    degradation_rate: float = 0.0
    lci_variant: str = "IEA"

    def label(self) -> str:
        up = "as-pub" if self.upstream_reshoring is None else f"{self.upstream_reshoring:.2f}"
        return (f"cf={self.capacity_factor} mix={self.electricity_mix} "
                f"eff={self.module_efficiency:.3f} up={up} deg={self.degradation_rate:.3f} "
                f"lci={self.lci_variant}")

    def as_dict(self) -> dict:
        return {"capacity_factor": self.capacity_factor,
                "electricity_mix": self.electricity_mix,
                "module_efficiency": self.module_efficiency,
                "upstream_reshoring": self.upstream_reshoring,
                "degradation_rate": self.degradation_rate,
                "lci_variant": self.lci_variant}


def grid(base: Params = Params(), **axes: Iterable) -> list[Params]:
    """Cartesian product of parameter values around ``base``.

    Example
    -------
    >>> grid(capacity_factor=["RN", "OWID"], electricity_mix=["WEO_STEPS", "EMBER"])
    returns 4 Params. Axes not listed keep their value from ``base``.
    """
    names = list(axes.keys())
    combos = product(*[list(v) for v in axes.values()])
    return [replace(base, **dict(zip(names, c))) for c in combos]
