from pathlib import Path

import pandas as pd
import pytest

from pv_hlca import io


def test_missing_source_unit_is_restored_with_original_scale(tmp_path):
    source = pd.DataFrame({"unit": ["kg", "1000 persons"]}, index=pd.MultiIndex.from_tuples([
        ("Satellite account", "Carbon dioxide, Cement (air - Emiss)"),
        ("Satellite account", "Employment"),
    ]))
    source.to_parquet(tmp_path / "units.parquet")

    class DB:
        units = {"Satellite account": pd.DataFrame({"unit": ["tonnes", "1000 persons"]}, index=["Carbon dioxide", "Employment"])}

        def get_index(self, level):
            return ["Carbon dioxide", "Employment", "Carbon dioxide, Cement (air - Emiss)"]

    db = DB()
    io.restore_source_units(db, {"base_db": {"_path": tmp_path}})
    assert db.units["Satellite account"].loc["Carbon dioxide, Cement (air - Emiss)", "unit"] == "kg"
    assert db.units["Satellite account"].loc["Carbon dioxide", "unit"] == "tonnes"


def test_git_lfs_pointer_is_reported_before_parsing(tmp_path):
    for name in ("z", "v", "e", "Y", "EY", "units"):
        (tmp_path / f"{name}.parquet").write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    with pytest.raises(ValueError, match="Git LFS pointer"):
        io.parse_base_db({"base_db": {"_path": tmp_path}})


def test_missing_database_has_actionable_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="--base-db"):
        io.parse_base_db({"base_db": {"_path": tmp_path}})
