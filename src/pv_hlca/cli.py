"""Command-line entry points for preparing and using the PV model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import io, prepared
from .experiment import Experiment
from .model import PVModel


def main(argv=None):
    parser = argparse.ArgumentParser(description="PV-HLCA: parameterise the PV supply chain and compare scenarios")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Validate an experiment without loading the database")
    check.add_argument("experiment", type=Path)
    prep = commands.add_parser("prepare", help="Prepare a reusable database bundle once")
    run = commands.add_parser("run", help="Run an experiment and export comparisons")
    for command in (prep, run):
        command.add_argument("--prepared", type=Path, default=Path("models/prepared"), help="Prepared bundle directory (default: models/prepared)")
        command.add_argument("--base-db", type=Path, help="Original SUT parquet directory; only needed for preparation")
        command.add_argument("--config", type=Path, help="Advanced: alternate config/paths.yaml")
        command.add_argument("--verbose", action="store_true", help="Show detailed MARIO calculation logs")
    run.add_argument("experiment", type=Path)
    run.add_argument("--output", type=Path, help="Results directory (default: outputs/<experiment file stem>)")
    run.add_argument("--heavy", action="store_true", help="Also compute disaggregated footprints")
    run.add_argument("--overwrite", action="store_true", help="Replace existing result files in the output directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            experiment = Experiment.load(args.experiment)
            print(json.dumps(experiment.as_dict(), indent=2))
            print("Experiment is valid. Region availability is checked when loading the model.")
            return 0
        cfg = io.load_config(args.config, base_db=args.base_db)
        import mario
        mario.set_log_verbosity("info" if args.verbose else "error")
        if args.command == "prepare":
            if not (args.prepared / "manifest.json").is_file():
                print("Preparing the PV database for first use; this can take several minutes.", flush=True)
            db, manifest = prepared.prepare(cfg, args.prepared)
            print(f"Prepared model: {args.prepared.resolve()} ({len(db.get_index('Region'))} regions)")
            print(f"Base source: {manifest['source']}")
            return 0
        experiment = Experiment.load(args.experiment)  # validate before expensive preparation
        output = args.output or Path("outputs") / args.experiment.stem
        if output.exists() and any(output.iterdir()) and not args.overwrite:
            raise ValueError(f"{output} is not empty; choose --output or use --overwrite")
        print(f"{experiment.title}: loading model with {len(experiment.scenarios)} scenario(s)", flush=True)
        if not (args.prepared / "manifest.json").is_file():
            print("Preparing the PV database for first use; this can take several minutes.", flush=True)
        model = PVModel.build(experiment.parameters, cfg=cfg, prepared_path=args.prepared)
        for spec in experiment.scenarios:
            print(f"Adding {spec.name} (from {spec.preset})", flush=True)
            model.add_scenario(spec)
        out = model.export(output, heavy=args.heavy, overwrite=args.overwrite)
        (out / "experiment.json").write_text(json.dumps(experiment.as_dict(), indent=2) + "\n")
        print(f"Results and assumptions: {out}")
        print("Compare footprints.csv and prices.csv by scenario; run.json records provenance and units.")
        return 0
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"PV-HLCA: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
