"""Small numerical contracts for new scenario operations (no external dataset)."""
import copy

import numpy as np
import pandas as pd
import pytest

from pv_hlca import ModelParameters, Scenario
from pv_hlca import custom
from pv_hlca.hybridize import ELECTRICITY_COMMODITIES
from pv_hlca.model import PVModel
from pv_hlca.scenarios import apply_import_structure, _import_matrix


class MiniDB:
    def __init__(self):
        self.regions = ["EU27", "CN", "US"]
        items = ["PV modules", "Cells", "Other input", *ELECTRICITY_COMMODITIES]
        rows = pd.MultiIndex.from_product([self.regions, ["Commodity"], items])
        cols = pd.MultiIndex.from_product([self.regions, ["Activity"], ["PV modules production", "Solar Power Plant"]])
        u = pd.DataFrame(0., index=rows, columns=cols).sort_index().sort_index(axis=1)
        for region in self.regions:
            u.loc[(region, "Commodity", "Coal"), (region, "Activity", "Solar Power Plant")] = 6
            u.loc[(region, "Commodity", "Gas"), (region, "Activity", "Solar Power Plant")] = 4
            u.loc[(region, "Commodity", "Cells"), (region, "Activity", "PV modules production")] = 5
        u.loc[("EU27", "Commodity", "PV modules"), ("EU27", "Activity", "Solar Power Plant")] = 1
        u.loc[("CN", "Commodity", "PV modules"), ("EU27", "Activity", "Solar Power Plant")] = 6
        u.loc[("US", "Commodity", "PV modules"), ("EU27", "Activity", "Solar Power Plant")] = 3
        yc_cols = pd.MultiIndex.from_product([self.regions, ["Consumption category"], ["Final consumption expenditure by households", "Other demand"]])
        Yc = pd.DataFrame(0., index=rows, columns=yc_cols).sort_index().sort_index(axis=1)
        for region in self.regions:
            Yc.loc[(region, "Commodity", "Coal"), (region, "Consumption category", "Final consumption expenditure by households")] = 60
            Yc.loc[(region, "Commodity", "Gas"), (region, "Consumption category", "Final consumption expenditure by households")] = 40
        self.matrices = {"baseline": {"u": u, "Yc": Yc}}

    @property
    def scenarios(self):
        return list(self.matrices)

    def get_index(self, name):
        assert name == "Region"
        return self.regions

    def query(self, matrices, scenarios):
        return self.matrices[scenarios][matrices]

    def update_scenarios(self, scenario, **matrices):
        self.matrices[scenario].update(matrices)

    def reset_to_coefficients(self, scenario):
        pass

    def clone_scenario(self, scenario, name):
        self.matrices[name] = copy.deepcopy(self.matrices[scenario])


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "imports.csv"
    pd.DataFrame([
        {"scenario": "baseline", "commodity": "Cells", "importer": "EU27", "exporter": "EU27", "share": .2},
        {"scenario": "baseline", "commodity": "Cells", "importer": "CN", "exporter": "EU27", "share": .6},
        {"scenario": "baseline", "commodity": "Cells", "importer": "US", "exporter": "EU27", "share": .2},
    ]).to_csv(path, index=False)
    return {"_import_structure_csv": path}


def test_sourcing_conserves_input_per_activity_and_other_commodities(cfg):
    db = MiniDB()
    before = db.query("u", "baseline").copy()
    spec = Scenario("target", sourcing={"EU27": {"PV modules": {"EU27": .6, "CN": .4}}})
    custom.apply_trade(db, cfg, "baseline", spec)
    after = db.query("u", "baseline")
    pd.testing.assert_series_equal(before.sum(), after.sum())
    col = ("EU27", "Activity", "Solar Power Plant")
    assert after.loc[("EU27", "Commodity", "PV modules"), col] == 6
    assert after.loc[("CN", "Commodity", "PV modules"), col] == 4
    assert after.loc[("US", "Commodity", "PV modules"), col] == 0
    pd.testing.assert_frame_equal(before.loc[:, before.columns.get_level_values(0) != "EU27"],
                                  after.loc[:, after.columns.get_level_values(0) != "EU27"])


@pytest.mark.parametrize("share", [0, .6, 1])
def test_domestic_share_preserves_foreign_proportions_and_endpoints(cfg, share):
    db = MiniDB()
    custom.apply_trade(db, cfg, "baseline", Scenario("target", domestic_shares={"EU27": {"PV modules": share}}))
    u = db.query("u", "baseline")
    col = ("EU27", "Activity", "Solar Power Plant")
    assert u.loc[("EU27", "Commodity", "PV modules"), col] == pytest.approx(10 * share)
    assert u.loc[("CN", "Commodity", "PV modules"), col] == pytest.approx(10 * (1-share) * 2/3)
    assert u.loc[("US", "Commodity", "PV modules"), col] == pytest.approx(10 * (1-share) / 3)


def test_autarkic_activity_can_use_historical_foreign_shares(cfg):
    db = MiniDB()
    custom.apply_trade(db, cfg, "baseline", Scenario("target", domestic_shares={"EU27": {"Cells": .4}}))
    u = db.query("u", "baseline")
    col = ("EU27", "Activity", "PV modules production")
    assert u.loc[("EU27", "Commodity", "Cells"), col] == 2
    assert u.loc[("CN", "Commodity", "Cells"), col] == pytest.approx(2.25)
    assert u.loc[("US", "Commodity", "Cells"), col] == pytest.approx(.75)


def test_custom_grid_can_zero_a_source_and_introduce_an_absent_source():
    db = MiniDB()
    before_u = db.query("u", "baseline").copy()
    before_y = db.query("Yc", "baseline").copy()
    custom.apply_electricity(db, "baseline", Scenario("grid", electricity_mix={"EU27": {"Solar": 1.0}}))
    u, y = db.query("u", "baseline"), db.query("Yc", "baseline")
    pd.testing.assert_series_equal(before_u.sum(), u.sum())
    pd.testing.assert_series_equal(before_y.sum(), y.sum())
    assert u.loc[("EU27", "Commodity", "Solar"), ("EU27", "Activity", "Solar Power Plant")] == 10
    assert u.loc[("EU27", "Commodity", "Coal")].sum() == 0
    pd.testing.assert_frame_equal(before_u.loc["CN"], u.loc["CN"])


def test_demand_increment_is_separate_from_mix_and_in_TJ():
    db = MiniDB()
    custom.apply_electricity(db, "baseline", Scenario("grid", electricity_mix={"EU27": {"Solar": .7, "Wind": .3}}, electricity_demand_tj={"EU27": 50}))
    y = db.query("Yc", "baseline")
    household = ("EU27", "Consumption category", "Final consumption expenditure by households")
    assert y[household].sum() == pytest.approx(150)
    assert y.loc[("EU27", "Commodity", "Solar"), household] == pytest.approx(105)
    assert y.loc[("EU27", "Commodity", "Wind"), household] == pytest.approx(45)


def test_model_scenarios_are_independent_and_baseline_cannot_be_overwritten(cfg):
    # Start at the already calibrated/traded boundary, avoiding preparation in this small test.
    model = object.__new__(PVModel)
    model.db, model.cfg, model.parameters = MiniDB(), cfg, ModelParameters()
    model.scenario_specs = {}
    before = model.db.query("u", "baseline").copy()
    model.add_scenario(Scenario("a", domestic_shares={"EU27": {"PV modules": .6}}))
    model.add_scenario(Scenario("b", domestic_shares={"EU27": {"PV modules": .2}}))
    pd.testing.assert_frame_equal(before, model.db.query("u", "baseline"))
    col = ("EU27", "Activity", "Solar Power Plant")
    assert model.db.query("u", "a").loc[("EU27", "Commodity", "PV modules"), col] == 6
    assert model.db.query("u", "b").loc[("EU27", "Commodity", "PV modules"), col] == 2
    with pytest.raises(ValueError, match="already exists"):
        model.add_scenario(Scenario("baseline"))
    with pytest.raises(ValueError, match="Unknown regions"):
        model.add_scenario(Scenario("bad", domestic_shares={"XX": {"Cells": .2}}))
    assert "bad" not in model.db.scenarios


def test_vectorised_paper_trade_retains_original_scalar_order_and_values():
    db = MiniDB()
    original = db.query("u", "baseline").copy()
    rng = np.random.default_rng(18)
    original.loc[:, :] = rng.uniform(0, 1, original.shape)
    rows = pd.DataFrame([
        {"importer": supplier, "exporter": importer, "share": share}
        for importer, suppliers in {
            "EU27": {"EU27": .2, "CN": .5, "US": .3},
            "CN": {"CN": .8, "US": .2},
            "US": {"EU27": .1, "CN": .2, "US": .7},
        }.items() for supplier, share in suppliers.items()
    ])
    expected = original.copy()
    matrix = _import_matrix(rows)
    # Frozen scalar prescription from the published implementation.
    for importer in db.regions:
        row = (importer, "Commodity", "PV modules")
        for col in expected.columns:
            value = expected.loc[row, col]
            if value == 0:
                continue
            expected.loc[row, col] = 0.0
            for supplier in matrix.columns:
                share = matrix.loc[importer, supplier]
                if share > 0:
                    expected.loc[(supplier, "Commodity", "PV modules"), col] += value * share
    actual = apply_import_structure(original, "PV modules", rows, db.regions)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
