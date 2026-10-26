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
import math


def _fraction(name, value, *, positive=False, below_one=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not (0 <= value <= 1) or (positive and value == 0) or (below_one and value == 1):
        raise ValueError(f"{name} must be {'>' if positive else '>='} 0 and {'<' if below_one else '<='} 1")


@dataclass(frozen=True)
class ModelParameters:
    """Technology assumptions, independent of a policy scenario.

    Efficiencies and degradation are fractions (0.22 and 0.005, respectively).
    Inventory and capacity-factor sources are the frozen inputs shipped here.
    """
    capacity_factor: str = "OWID"
    module_efficiency: float = 0.195
    degradation_rate: float = 0.0
    lci_variant: str = "IEA"

    def __post_init__(self):
        if self.capacity_factor not in ("OWID", "RN"):
            raise ValueError("capacity_factor must be OWID or RN")
        if self.lci_variant not in ("IEA", "NREL"):
            raise ValueError("lci_variant must be IEA or NREL")
        _fraction("module_efficiency", self.module_efficiency, positive=True)
        _fraction("degradation_rate", self.degradation_rate, below_one=True)

    def as_dict(self):
        return {k: getattr(self, k) for k in (
            "capacity_factor", "module_efficiency", "degradation_rate", "lci_variant")}


@dataclass(frozen=True)
class Params:
    capacity_factor: str = "OWID"
    electricity_mix: str = "WEO_STEPS"
    module_efficiency: float = 0.195
    upstream_reshoring: float | None = None
    degradation_rate: float = 0.0
    lci_variant: str = "IEA"

    def __post_init__(self):
        ModelParameters(self.capacity_factor, self.module_efficiency,
                        self.degradation_rate, self.lci_variant)
        if self.electricity_mix not in ("WEO_STEPS", "EMBER"):
            raise ValueError("electricity_mix must be WEO_STEPS or EMBER")
        if self.upstream_reshoring is not None:
            _fraction("upstream_reshoring", self.upstream_reshoring)

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
