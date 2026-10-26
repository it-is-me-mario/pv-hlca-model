"""Install the PV runtime and pinned MARIO engine into an activated environment."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12 for this model environment (see docs/installation.md).")
    if sys.prefix == sys.base_prefix and not os.environ.get("CONDA_PREFIX"):
        raise SystemExit("Activate a dedicated conda or venv environment first; see docs/installation.md.")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-model.txt")], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "mariopy==1.0.0", "-e", str(ROOT)], check=True)
    import mario
    print(f"PV-HLCA installed with MARIO {mario.__version__}. Try: pv-hlca check examples/eu_reshoring.yaml")


if __name__ == "__main__":
    main()
