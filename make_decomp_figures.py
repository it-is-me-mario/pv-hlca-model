"""Render both PV-footprint decomposition figures for the baseline and domestic
scenarios from the data already on disk:

  fig_decomp_<scenario>   exploded decomposition to ULTIMATE emitters (diag(e).w),
                          source outputs/sensitivity/fc_ex_<scenario>.parquet
  fig_onestep_<scenario>  one-step "supply chain impact linkages" (diag(f).z+diag(e),
                          thesis Fig.11), source outputs/sensitivity/onestep_<scenario>.parquet

Colours are coordinated across both figures via figures.CATEGORY_COLORS (MARIO palette).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca import io, figures                                  # noqa: E402

SCENARIOS = ("baseline", "domestic")

if __name__ == "__main__":
    cfg = io.load_config()
    sens = cfg["outputs"]["dir"] / "sensitivity"
    figs = cfg["outputs"]["dir"] / "figures"
    for scen in SCENARIOS:
        _, p1 = figures.fig_decomp(sens, figs, scenario=scen)
        _, p2 = figures.fig_onestep(sens, figs, scenario=scen)
        print(f"{scen}: {p1.name}, {p2.name}")
