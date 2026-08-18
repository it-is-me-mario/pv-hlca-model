"""Regenerate every manuscript figure panel from the data on disk and save it ONLY
under the current paper's figure/panel number, as high-res TIFF, so the files can be
dropped straight into the manuscript or combined into the final multi-panel figures.

Each figure function also writes a content-named copy via figures._save; to avoid
littering the figures dir with those, we redirect the internal save to a throwaway
temp directory and keep only the paper-numbered copy in the real output dir.

Figure 1 (the methodological schematic) is hand-drawn and not produced here.

    python make_figures.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca import io, figures                                  # noqa: E402

# paper figure number -> (callable returning (fig, path), short description)
SPECS = [
    ("Figure2a", lambda s, f: figures.fig1(s, f, scenario="baseline"),           "footprint validation"),
    ("Figure2b", lambda s, f: figures.fig_prices(s, f, scenario="baseline"),     "producer prices (+ top-down)"),
    ("Figure3", lambda s, f: figures.fig_breakdown(s, f, scenario="baseline"),   "footprint breakdown"),
    ("Figure4", lambda s, f: figures.fig_onestep(s, f, scenario="baseline"),     "supply-chain impact linkages"),
    ("Figure5a-b", lambda s, f: figures.fig_stages(s, f),                        "supply-chain reconfiguration"),
    ("Figure5c-d", lambda s, f: figures.fig_va_employment(s, f),                 "value added + employment"),
    ("Figure6", lambda s, f: figures.fig_sensitivity(s, f),                      "sensitivity + upstream scan"),
]

if __name__ == "__main__":
    cfg = io.load_config()
    sens = cfg["outputs"]["dir"] / "sensitivity"
    figs = cfg["outputs"]["dir"] / "figures"
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)                       # absorbs the content-named copies
        for name, fn, desc in SPECS:
            try:
                fig, _ = fn(sens, scratch)        # internal _save -> throwaway dir
                figures._save(fig, figs, name)    # keep only the paper-numbered copy
                print(f"{name}: {desc}")
            except Exception as e:
                print(f"{name}: SKIPPED ({desc}) -> {type(e).__name__}: {e}")
