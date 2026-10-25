import math
from pathlib import Path

import pytest

from pv_hlca import Experiment, ModelParameters, Scenario
from pv_hlca.hybridize import _lifetime_yield_factor
from pv_hlca.params import Params


@pytest.mark.parametrize("values", [
    {"module_efficiency": 0}, {"module_efficiency": -0.2},
    {"module_efficiency": 22}, {"module_efficiency": True},
    {"degradation_rate": 1}, {"degradation_rate": float("nan")},
    {"module_efficiency": float("inf")}, {"capacity_factor": "typo"},
    {"lci_variant": "unknown"},
])
def test_invalid_technology_is_rejected_before_build(values):
    with pytest.raises(ValueError):
        ModelParameters(**values)
    with pytest.raises(ValueError):
        Params(**values)


@pytest.mark.parametrize("values", [
    {"sourcing": {"EU27": {"Cells": {"CN": 0.8}}}},
    {"electricity_mix": {"EU27": {"Solar": 1.1, "Gas": -0.1}}},
    {"electricity_mix": {"EU27": {"typo": 1}}},
    {"domestic_shares": {"EU27": {"typo": 0.5}}},
    {"domestic_shares": {"EU27": {"Cells": math.nan}}},
    {"sourcing": {"EU27": {"Cells": {"EU27": 1}}}, "domestic_shares": {"EU27": {"Cells": 0.5}}},
    {"electricity_demand_tj": {"EU27": -1}},
    {"electricity_demand_tj": {"EU27": True}},
    {"upstream_reshoring": 0.5}, {"preset": "unknown"},
])
def test_invalid_scenarios_fail_early(values):
    with pytest.raises(ValueError):
        Scenario("example", **values)


def test_all_shipped_experiments_are_loadable():
    for path in Path("examples").glob("*.yaml"):
        experiment = Experiment.load(path)
        assert experiment.scenarios
        assert experiment.as_dict()["parameters"]["module_efficiency"] > 0


@pytest.mark.parametrize("body", [
    "paramaters: {}", "parameters: {module_efficieny: 0.22}",
    "scenarios: [{name: a}, {name: a}]", "scenarios: [{name: baseline}]",
    "scenarios: [{name: x, domestic_share: 0.5}]", "scenarios: {}",
])
def test_yaml_typos_and_duplicate_names_are_not_ignored(tmp_path, body):
    path = tmp_path / "experiment.yaml"
    path.write_text(body)
    with pytest.raises(ValueError):
        Experiment.load(path)


def test_degradation_has_known_lifetime_mean():
    assert _lifetime_yield_factor(0, 25) == 1
    assert _lifetime_yield_factor(0.05, 2) == pytest.approx(0.975)
