"""Build the one-step PV GHG decomposition (thesis Fig.11 "supply chain impact
linkages") for the central case and write outputs/sensitivity/onestep_<scenario>.parquet.

Thin wrapper over pv_hlca.export.write_onestep_data (resume=True: scenarios already
on disk are skipped). See pv_hlca.indicators.onestep_decomp_pv for the method
(D = diag(f).z + diag(e)).

    python build_onestep.py            # all 4 central scenarios (resumes)
    python build_onestep.py --fresh    # recompute all
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca import io, export                                   # noqa: E402

if __name__ == "__main__":
    cfg = io.load_config()
    export.write_onestep_data(cfg, cfg["outputs"]["dir"] / "sensitivity",
                              resume="--fresh" not in sys.argv[1:])
