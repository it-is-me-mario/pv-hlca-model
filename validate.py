"""Validate the rebuilt pipeline against the published thesis results.

Runs the full pipeline from the Zenodo 18744457 base and compares the per-region
solar-electricity footprint to the published reference (reference/new_solar_
footprints_RN.csv, raw values; x3.6 -> gCO2eq/kWh).

Because the repo rebuilds from Zenodo 18744457 while the published numbers were
generated from a slightly older hybrid base (eNextSUT), agreement is expected to
be *marginal* (a few percent), not bit-exact.

    python validate.py            # RN variant
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca import io, pipeline, indicators  # noqa: E402
from pv_hlca.params import Params

TOL_MEDIAN = 10.0   # % — declared marginal tolerance vs the older published base


def main(variant: str = "RN") -> int:
    cfg = io.load_config()
    print(f"Building pipeline (variant={variant}) ...", flush=True)
    db = pipeline.build_database(cfg, Params(capacity_factor=variant))

    mine = indicators.solar_footprint(db, cfg, "baseline", g_per_kwh=False)
    refcol = {"RN": "new_footprints_RN", "OWID": "new_footprints_OWID"}[variant]
    reffile = {"RN": "new_solar_footprints_RN.csv",
               "OWID": "new_solar_footprints_OWID.csv"}[variant]
    ref = pd.read_csv(cfg["reference"]["_footprints_dir"] / reffile).set_index("Region")[refcol]

    cmp = pd.DataFrame({"mine": mine, "ref": ref}).dropna().sort_index()
    cmp["pct"] = (cmp["mine"] - cmp["ref"]) / cmp["ref"] * 100
    cmp["mine_gkwh"] = cmp["mine"] * 3.6
    cmp["ref_gkwh"] = cmp["ref"] * 3.6
    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
    print("\n=== Baseline solar footprint: rebuilt vs published reference ===")
    print(cmp.to_string())
    ad = cmp["pct"].abs()
    print(f"\nmedian |pct| = {ad.median():.2f}%   max |pct| = {ad.max():.2f}%")
    print(f"headline range (gCO2eq/kWh): {cmp['mine_gkwh'].min():.1f} - {cmp['mine_gkwh'].max():.1f}")

    ok = ad.median() <= TOL_MEDIAN
    print(f"\n{'PASS' if ok else 'FAIL'}: median deviation "
          f"{'<=' if ok else '>'} {TOL_MEDIAN}% (declared marginal tolerance).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "RN"))
