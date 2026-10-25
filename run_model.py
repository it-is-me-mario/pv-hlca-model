"""Use the model directly from a checkout, with the same CLI as pv-hlca."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pv_hlca.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
