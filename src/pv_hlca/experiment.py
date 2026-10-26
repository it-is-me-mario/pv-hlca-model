"""Validated, portable definitions of a user's model experiment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import yaml

from .params import ModelParameters, _fraction
from .hybridize import ELECTRICITY_COMMODITIES
from .scenarios import PV_IMPORT_COMMODITIES


def _mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _shares(values, label, *, allowed=None):
    _mapping(values, label)
    if not values:
        raise ValueError(f"{label} must not be empty")
    for name, share in values.items():
        if not isinstance(name, str) or (allowed is not None and name not in allowed):
            raise ValueError(f"Unknown {label} label {name!r}")
        _fraction(f"{label}.{name}", share)
    if abs(sum(values.values()) - 1) > 1e-8:
        raise ValueError(f"{label} shares must sum to 1 (got {sum(values.values()):.10g})")


@dataclass(frozen=True)
class Scenario:
    """One independent scenario, starting from a named reference preset.

    ``sourcing`` is {importing_region: {PV_commodity: {supplier: share}}}.
    ``domestic_shares`` is a shortcut preserving relative foreign sourcing.
    ``electricity_mix`` replaces the domestic mix with explicit shares; demand
    additions are TJ of household electricity, separate from the mix rotation.
    """
    name: str
    preset: str = "baseline"
    grid_source: str = "WEO_STEPS"
    upstream_reshoring: float | None = None
    domestic_shares: dict = field(default_factory=dict)
    sourcing: dict = field(default_factory=dict)
    electricity_mix: dict = field(default_factory=dict)
    electricity_demand_tj: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", self.name):
            raise ValueError("Scenario name must start with a letter and contain only letters, digits, _ or -")
        if self.preset not in ("baseline", "domestic", "NZIA", "baseline_2030"):
            raise ValueError(f"Unknown preset {self.preset!r}")
        if self.grid_source not in ("WEO_STEPS", "EMBER"):
            raise ValueError("grid_source must be WEO_STEPS or EMBER")
        if self.upstream_reshoring is not None:
            _fraction("upstream_reshoring", self.upstream_reshoring)
            if self.preset != "NZIA":
                raise ValueError("upstream_reshoring applies to the NZIA preset; use domestic_shares for other scenarios")
        for region, values in _mapping(self.domestic_shares, "domestic_shares").items():
            for commodity, share in _mapping(values, f"domestic_shares.{region}").items():
                if commodity not in PV_IMPORT_COMMODITIES:
                    raise ValueError(f"Unknown PV commodity {commodity!r}")
                _fraction(f"domestic_shares.{region}.{commodity}", share)
        for region, values in _mapping(self.sourcing, "sourcing").items():
            for commodity, shares in _mapping(values, f"sourcing.{region}").items():
                if commodity not in PV_IMPORT_COMMODITIES:
                    raise ValueError(f"Unknown PV commodity {commodity!r}")
                if commodity in self.domestic_shares.get(region, {}):
                    raise ValueError(f"Specify either sourcing or domestic_shares for {region}/{commodity}")
                _shares(shares, f"sourcing.{region}.{commodity}")
        for region, shares in _mapping(self.electricity_mix, "electricity_mix").items():
            _shares(shares, f"electricity_mix.{region}", allowed=ELECTRICITY_COMMODITIES)
        for region, value in _mapping(self.electricity_demand_tj, "electricity_demand_tj").items():
            import math
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"electricity_demand_tj.{region} must be finite and non-negative")

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Experiment:
    parameters: ModelParameters = field(default_factory=ModelParameters)
    scenarios: tuple[Scenario, ...] = ()
    title: str = "PV-HLCA experiment"

    @classmethod
    def load(cls, path):
        raw = yaml.safe_load(Path(path).read_text())
        _mapping(raw, "experiment")
        unknown = raw.keys() - {"parameters", "scenarios", "title"}
        if unknown:
            raise ValueError(f"Unknown experiment fields: {', '.join(sorted(unknown))}")
        params = _mapping(raw.get("parameters", {}), "parameters")
        items = raw.get("scenarios", [])
        if not isinstance(items, list):
            raise ValueError("scenarios must be a list")
        try:
            parameters = ModelParameters(**params)
            scenarios = tuple(Scenario(**_mapping(item, "scenario")) for item in items)
        except TypeError as exc:
            raise ValueError(f"Invalid experiment field: {exc}") from exc
        names = [s.name for s in scenarios]
        if len(names) != len(set(names)) or set(names) & {"baseline", "domestic"}:
            raise ValueError("Scenario names must be unique; baseline and domestic are reserved")
        return cls(parameters, scenarios, str(raw.get("title", "PV-HLCA experiment")))

    def as_dict(self):
        return {"title": self.title, "parameters": self.parameters.as_dict(),
                "scenarios": [s.as_dict() for s in self.scenarios]}
