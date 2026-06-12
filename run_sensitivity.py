"""Run the global sensitivity analysis and export every indicator.

Builds the hybrid database from Zenodo 18744457 and runs the sensitivity design used
in the paper: a one-at-a-time sweep around the central case over the five levers
(capacity factor, module efficiency, degradation rate, upstream-electricity LCI and
the upstream-reshoring share), plus the alternative 2030 grid. It writes all matrices
(f, p, X, V, E) tagged with the levers to ``outputs/sensitivity/``.

``--heavy`` additionally writes the disaggregated solar footprint
(``f_dis_solar.parquet``) and the per-stage / one-step decomposition data
(``fc_ex_*.parquet``, ``onestep_*.parquet``), which the breakdown, reconfiguration
and impact-linkage figures need.

    python run_sensitivity.py            # paper design (one-at-a-time slices; resumes)
    python run_sensitivity.py --full     # full Cartesian grid instead
    python run_sensitivity.py --heavy    # + disaggregated + decomposition data (all figures)
    python run_sensitivity.py --quick    # central case only (smoke test)
    python run_sensitivity.py --fresh    # ignore existing runs/, recompute all
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca import io, export                       # noqa: E402
from pv_hlca.params import Params                    # noqa: E402


def main(argv):
    heavy = "--heavy" in argv
    quick = "--quick" in argv
    fresh = "--fresh" in argv
    full = "--full" in argv
    cfg = io.load_config()
    if quick:
        grid = [Params()]
    elif full:
        grid = export.default_grid()
    else:
        grid = export.sensitivity_grid()
    n_cf = len({p.capacity_factor for p in grid})
    n_base = len({(p.capacity_factor, p.module_efficiency) for p in grid})
    print(f"grid: {len(grid)} runs, 1 add_sectors, {n_cf} solar shocks, "
          f"{n_base} module-efficiency bases, heavy={heavy}, fresh={fresh}", flush=True)

    t0 = time.time()
    out = export.run_and_export(cfg, grid, cfg["outputs"]["dir"] / "sensitivity",
                                heavy=heavy, resume=not fresh)
    if heavy and not quick:
        # central-case decomposition data needed by the breakdown / reconfiguration /
        # impact-linkage figures (one extra base build each)
        export.write_decomposition_data(cfg, out, resume=not fresh)
        export.write_onestep_data(cfg, out, resume=not fresh)
    print(f"done in {(time.time() - t0) / 60:.1f} min -> {out}")

    import pandas as pd
    for f in ["footprints", "prices", "production", "value_added", "employment", "headline"]:
        p = out / f"{f}.csv"
        if p.exists():
            print(f"  {f}: {pd.read_csv(p).shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
