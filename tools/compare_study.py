"""Compare a model export of paper_presets.yaml with the shipped study tables.

Usage: python tools/compare_study.py /path/to/export --report /path/to/report.json
This runs no model. It uses rtol=1e-8 and atol=1e-9 except employment,
where the absolute tolerance is 0.001 thousand persons (one person). Both the
strict comparison and the explicit unit-based tolerance are reported.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "footprints": (["scenario", "region"], ["footprint_gkwh"]),
    "prices": (["scenario", "region"], ["price_eur_kwh"]),
    "production": (["scenario", "region", "commodity"], ["production"]),
    "value_added": (["scenario", "region", "factor"], ["value_added"]),
    "employment": (["scenario", "region", "activity"], ["employment"]),
    "headline": (["scenario"], ["EU27_value_added_Meur", "global_co2eq"]),
}


def compare(path, reference=ROOT / "outputs/sensitivity", rtol=1e-8, atol=1e-9):
    report = {}
    for name, (keys, values) in TABLES.items():
        actual = pd.read_csv(Path(path) / f"{name}.csv")
        actual["scenario"] = actual["scenario"].replace({"all_domestic": "domestic"})
        expected = pd.read_csv(Path(reference) / f"{name}.csv")
        expected = expected[(expected.capacity_factor == "OWID") & (expected.electricity_mix == "WEO_STEPS")
                            & np.isclose(expected.module_efficiency, .195) & (expected.upstream_reshoring.isna())
                            & (expected.degradation_rate == 0) & (expected.lci_variant == "IEA")]
        left = actual.set_index(keys)[values].sort_index()
        right = expected.set_index(keys)[values].sort_index()
        if not left.index.is_unique or not right.index.is_unique or not left.index.equals(right.index):
            raise ValueError(f"{name}: scenario/region/category coverage differs")
        delta = (left - right).abs()
        table_atol = 0.001 if name == "employment" else atol
        strict = bool(np.isfinite(left.to_numpy()).all() and np.allclose(left, right, rtol=rtol, atol=atol))
        passed = bool(np.isfinite(left.to_numpy()).all() and np.allclose(left, right, rtol=rtol, atol=table_atol))
        report[name] = {"pass": passed, "rows": len(left), "max_absolute_difference": float(delta.to_numpy().max()),
                        "strict_numeric_pass": strict, "rtol": rtol, "atol": table_atol}
        if name == "employment":
            report[name]["max_difference_persons"] = float(delta.to_numpy().max() * 1000)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("export", type=Path)
    p.add_argument("--reference", type=Path, default=ROOT / "outputs/sensitivity")
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    report = compare(args.export, args.reference)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        args.report.write_text(rendered + "\n")
    raise SystemExit(0 if all(item["pass"] for item in report.values()) else 1)
