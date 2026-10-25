"""Run a sensitivity grid and export all results, tagged with every sensitivity
lever as a column (capacity_factor, electricity_mix, module_efficiency,
upstream_reshoring) plus the scenario.

Outputs (tidy, in ``outdir``):
  footprints.csv       region solar-electricity footprint (gCO2eq/kWh)   [f]
  prices.csv           region solar-electricity price (EUR/kWh)          [p]
  production.csv       output of the six PV commodities, per region      [X]
  value_added.csv      value added by (production factor, region)        [V]
  employment.csv       employment by (region, activity)                  [E]
  headline.csv         per run: EU27 total value added, global CO2eq
  f_dis_solar.parquet  (heavy, optional) full disaggregated solar footprint

Execution model
---------------
The expensive hybrid base depends on *almost nothing*: ``parse -> aggregate ->
add_sectors`` is invariant across every lever, the solar shock depends only on
``capacity_factor`` and the module rescale only on ``module_efficiency``. So the
grid is walked as a tree::

    parse + aggregate + add_sectors          built ONCE
      -> apply_solar_shock(cf)               once per capacity factor
        -> apply_module_efficiency(eff)      once per (cf, eff)
           + remove_old_solar
          -> build_all_scenarios(mix, up)    once per run (irreducible)

Each run is written to ``runs/<run_key>/`` the moment it is computed (freeing
memory) and stamped with a ``_DONE`` marker written last. A crashed run leaves no
marker, so re-running resumes from where it stopped: completed runs are skipped,
and a whole ``(cf, eff)`` group that is already done never rebuilds its base.
``combine_runs`` stitches the per-run shards back into the tidy tables above.
"""
from __future__ import annotations
import copy
import time
from pathlib import Path
import pandas as pd

from . import io, hybridize, scenarios, indicators
from .params import Params


def _log(msg: str) -> None:
    """Pipeline-level progress log, distinct from mario's INFO/WARNING lines."""
    print(f"[export {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s" if seconds < 90 else f"{seconds / 60:.1f}min"


#: per-run tidy CSV shards (name -> filename)
_TABLES = ("footprints", "prices", "production", "value_added", "employment", "headline")
_HEAVY_FILE = "f_dis_solar.parquet"
_DONE = "_DONE"


def _run_key(p: Params) -> str:
    """Deterministic, filesystem-safe identifier for one run (one Params)."""
    up = "as-pub" if p.upstream_reshoring is None else f"{p.upstream_reshoring:.2f}"
    return (f"cf={p.capacity_factor}__mix={p.electricity_mix}"
            f"__eff={p.module_efficiency:.3f}__up={up}__deg={p.degradation_rate:.3f}"
            f"__lci={p.lci_variant}")


def _is_done(run_dir: Path) -> bool:
    return (run_dir / _DONE).exists()


# --------------------------------------------------------------------------- #
# heavy-base construction (the lever-invariant prefix)
# --------------------------------------------------------------------------- #
def _build_base(cfg):
    """parse -> aggregate -> add PV sectors -> calc_ghg. Invariant across all levers."""
    from .pipeline import prepare_database
    return prepare_database(cfg)


# --------------------------------------------------------------------------- #
# indicators for one run -> tidy tables
# --------------------------------------------------------------------------- #
def _tables_for_run(db, cfg, p: Params, scenario_list, heavy: bool) -> dict:
    """Compute every indicator for one fully-built run and return a dict of
    {name: DataFrame}. ``db`` must already have all scenarios built."""
    tag = p.as_dict()
    foot, price, prod, va, emp, head, fdis = [], [], [], [], [], [], []

    for scen in scenario_list:
        if scen not in db.scenarios:
            continue
        for region, v in indicators.solar_footprint(db, cfg, scen, g_per_kwh=True).items():
            foot.append({**tag, "scenario": scen, "region": region, "footprint_gkwh": float(v)})
        for region, v in indicators.solar_price(db, cfg, scen, eur_per_kwh=True).items():
            price.append({**tag, "scenario": scen, "region": region, "price_eur_kwh": float(v)})
        for (region, com), v in indicators.production_pv(db, scen).items():
            prod.append({**tag, "scenario": scen, "region": region,
                         "commodity": com, "production": float(v)})
        for (factor, region), v in indicators.value_added_by_factor(db, scen).items():
            va.append({**tag, "scenario": scen, "factor": factor,
                       "region": region, "value_added": float(v)})
        for (region, act), v in indicators.employment_by_activity(db, scen).items():
            emp.append({**tag, "scenario": scen, "region": region,
                        "activity": act, "employment": float(v)})
        head.append({**tag, "scenario": scen,
                     "EU27_value_added_Meur": indicators.eu_value_added(db, scen),
                     "global_co2eq": indicators.global_co2eq(db, cfg, scen)})
        if heavy:
            fd = indicators.f_dis_solar(db, cfg, scen).rename("CO2eq").reset_index()
            for k, val in {**tag, "scenario": scen}.items():
                fd[k] = val
            fdis.append(fd)

    out = {"footprints": pd.DataFrame(foot), "prices": pd.DataFrame(price),
           "production": pd.DataFrame(prod), "value_added": pd.DataFrame(va),
           "employment": pd.DataFrame(emp), "headline": pd.DataFrame(head)}
    if heavy:
        out["_f_dis"] = pd.concat(fdis, ignore_index=True) if fdis else pd.DataFrame()
    return out


def _write_run(run_dir: Path, tables: dict, heavy: bool) -> None:
    """Write one run's shards then stamp ``_DONE`` (written last = atomic resume)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in _TABLES:
        df = tables[name]
        if not df.empty:
            df.to_csv(run_dir / f"{name}.csv", index=False)
    if heavy:
        fd = tables.get("_f_dis")
        if fd is not None and not fd.empty:
            fd.to_parquet(run_dir / _HEAVY_FILE)
    (run_dir / _DONE).write_text("ok\n")


# --------------------------------------------------------------------------- #
# combine per-run shards into the tidy top-level tables
# --------------------------------------------------------------------------- #
def combine_runs(outdir, *, heavy: bool = False) -> Path:
    """Concatenate every completed ``runs/<key>/`` shard into the tidy tables at
    ``outdir``. Idempotent; safe to call after a partial run to get what's done."""
    outdir = Path(outdir)
    runs_dir = outdir / "runs"
    done = sorted(d for d in runs_dir.glob("*") if d.is_dir() and _is_done(d))
    _log(f"combining {len(done)} completed run shard(s)")
    for name in _TABLES:
        parts = [pd.read_csv(d / f"{name}.csv") for d in done if (d / f"{name}.csv").exists()]
        if parts:
            pd.concat(parts, ignore_index=True).to_csv(outdir / f"{name}.csv", index=False)
    if heavy:
        parts = [pd.read_parquet(d / _HEAVY_FILE) for d in done if (d / _HEAVY_FILE).exists()]
        if parts:
            pd.concat(parts, ignore_index=True).to_parquet(outdir / _HEAVY_FILE)
    return outdir


# --------------------------------------------------------------------------- #
# decomposition data: exploded GHG footprint (fc_ex) for the central case
# --------------------------------------------------------------------------- #
def write_decomposition_data(cfg, outdir, *,
                             scenario_list=("baseline", "NZIA", "baseline_2030", "domestic"),
                             resume: bool = True) -> Path:
    """Build the central case (OWID, WEO_STEPS, 0.195, no reshoring) and write the
    exploded GHG footprint of the PV commodities per scenario to
    ``fc_ex_<scenario>.parquet`` — the source for the per-stage decomposition
    figures. Heavy (one full base build, ~minutes); skipped scenarios already on
    disk when ``resume`` (unless none present)."""
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    want = [s for s in scenario_list if not (resume and (outdir / f"fc_ex_{s}.parquet").exists())]
    if not want:
        _log("decomposition data already present")
        return outdir
    t = time.time()
    _log("building central case for decomposition (parse+aggregate+add_sectors+calc_ghg+shock) ...")
    db = _build_base(cfg)
    hybridize.apply_solar_shock(db, cfg, "OWID")  # central case
    hybridize.apply_module_efficiency(db, cfg, 0.195)
    hybridize.remove_old_solar(db, cfg)
    scenarios.build_all_scenarios(db, cfg, mix_source="WEO_STEPS", upstream_reshoring=None)
    for scen in scenario_list:
        if scen in db.scenarios:
            indicators.fc_ex_pv(db, scen).to_parquet(outdir / f"fc_ex_{scen}.parquet")
            _log(f"fc_ex_{scen}.parquet written")
    _log(f"decomposition data done in {_fmt(time.time() - t)}")
    return outdir


# --------------------------------------------------------------------------- #
# one-step decomposition data (thesis Fig.11 "supply chain impact linkages")
# --------------------------------------------------------------------------- #
def write_onestep_data(cfg, outdir, *,
                       scenario_list=("baseline", "NZIA", "baseline_2030", "domestic"),
                       regions=("EU27", "CN"), resume: bool = True) -> Path:
    """Build the central case (OWID, WEO_STEPS, 0.195, no reshoring) and write the
    one-step GHG decomposition (``diag(f).z + diag(e)``) of the PV stages per scenario
    to ``onestep_<scenario>.parquet`` — the source for :func:`pv_hlca.figures.fig_onestep`.
    Heavy (one full base build, ~minutes); validates that each stage's contributions
    sum to its footprint f_j. Skips scenarios already on disk when ``resume``."""
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    want = [s for s in scenario_list if not (resume and (outdir / f"onestep_{s}.parquet").exists())]
    if not want:
        _log("one-step decomposition data already present")
        return outdir
    t = time.time()
    _log("building central case for one-step decomposition ...")
    db = _build_base(cfg)
    hybridize.apply_solar_shock(db, cfg, "OWID")  # central case
    hybridize.apply_module_efficiency(db, cfg, 0.195)
    hybridize.remove_old_solar(db, cfg)
    scenarios.build_all_scenarios(db, cfg, mix_source="WEO_STEPS", upstream_reshoring=None)
    for scen in scenario_list:
        if scen in db.scenarios:
            df = indicators.onestep_decomp_pv(db, cfg, scen, regions=regions)
            df.to_parquet(outdir / f"onestep_{scen}.parquet")
            _log(f"onestep_{scen}.parquet written ({len(df)} rows)")
    _log(f"one-step decomposition data done in {_fmt(time.time() - t)}")
    return outdir


# --------------------------------------------------------------------------- #
# top-down benchmark (raw EXIOBASE, lever-invariant -> computed once)
# --------------------------------------------------------------------------- #
def _write_topdown(cfg, outdir: Path, *, resume: bool = True) -> None:
    """Compute the top-down solar footprint once and write ``topdown.csv``.

    Lever-invariant (it is the raw EXIOBASE benchmark), so it is computed a single
    time and skipped on resume if already present. A no-op when the raw EXIOBASE
    path is not configured."""
    out = outdir / "topdown.csv"
    if resume and out.exists():
        return
    t = time.time()
    # Recompute the benchmark from the raw EXIOBASE 3.3.18 hybrid SUT (reproducible),
    # rather than reading the legacy published values (whose provenance/GHG-account
    # selection could not be reproduced). Same DB the prices match; fossil CO2 + CH4 +
    # N2O via the satellite aggregation, AR6 GWP.
    fp = indicators.topdown_footprint_exiobase_raw(cfg, g_per_kwh=True)
    if fp is None:
        _log("top-down skipped (exiobase_raw not configured/available)")
        return
    pd.DataFrame({"model": "topdown", "region": fp.index,
                  "footprint_gkwh": fp.values}).to_csv(out, index=False)
    _log(f"top-down benchmark written ({len(fp)} regions) in {_fmt(time.time() - t)}")


# --------------------------------------------------------------------------- #
# the driver
# --------------------------------------------------------------------------- #
def run_and_export(cfg, params_list, outdir, *,
                   scenario_list=("baseline", "NZIA", "baseline_2030", "domestic"),
                   heavy: bool = False, resume: bool = True) -> Path:
    """Run every Params in ``params_list`` and write all indicators to ``outdir``.

    Walks the lever tree so the heavy base (``parse -> aggregate -> add_sectors``)
    is built once, the solar shock once per ``capacity_factor`` and the module
    rescale once per ``(capacity_factor, module_efficiency)``. Each run is written
    immediately under ``outdir/runs/`` and stamped ``_DONE``.

    With ``resume=True`` (default) runs already stamped ``_DONE`` are skipped, so
    an interrupted grid restarts from the middle; a fully-done ``(cf, eff)`` group
    never rebuilds its base. Set ``resume=False`` to recompute everything.
    """
    outdir = Path(outdir)
    runs_dir = outdir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    _write_topdown(cfg, outdir, resume=resume)        # raw-EXIOBASE benchmark, once

    # which runs still need doing
    todo, skipped = [], 0
    for p in params_list:
        if resume and _is_done(runs_dir / _run_key(p)):
            skipped += 1
        else:
            todo.append(p)
    _log(f"{len(params_list)} runs total | {skipped} already done (resume={resume}) "
         f"| {len(todo)} to run | heavy={heavy}")
    if not todo:
        _log("nothing to run; combining existing shards")
        combine_runs(outdir, heavy=heavy)
        return outdir

    # group todo by (capacity factor, degradation), then module efficiency: the
    # solar shock depends on both cf and degradation (both scale the per-TJ yield)
    by_cf: dict = {}
    for p in todo:
        by_cf.setdefault((p.capacity_factor, p.degradation_rate), {}) \
             .setdefault(p.module_efficiency, []).append(p)
    n_solar = len(by_cf)
    n_eff = sum(len(v) for v in by_cf.values())
    _log(f"plan: 1 base build, {n_solar} solar shock(s), {n_eff} module-efficiency base(s)")

    base = None                                    # built lazily, exactly once
    n_done = 0
    for (cf, deg), by_eff in by_cf.items():
        db_cf = None                               # built once per (capacity factor, degradation)
        for eff, members in by_eff.items():
            if base is None:
                t = time.time()
                _log("building hybrid base (parse + aggregate + add_sectors) ...")
                base = _build_base(cfg)
                _log(f"hybrid base ready in {_fmt(time.time() - t)}")
            if db_cf is None:
                t = time.time()
                db_cf = copy.deepcopy(base)
                hybridize.apply_solar_shock(db_cf, cfg, variant=cf, degradation_rate=deg)
                _log(f"solar shock cf={cf} deg={deg} ready in {_fmt(time.time() - t)}")
            t = time.time()
            db = copy.deepcopy(db_cf)
            hybridize.apply_module_efficiency(db, cfg, eff)
            hybridize.remove_old_solar(db, cfg)
            clean = copy.deepcopy(db.matrices["baseline"])
            _log(f"base cf={cf} deg={deg} eff={eff} ready in {_fmt(time.time() - t)} "
                 f"-> {len(members)} run(s)")
            for p in members:
                t = time.time()
                db.matrices = {"baseline": copy.deepcopy(clean)}
                hybridize.apply_lci_variant(db, cfg, p.lci_variant)   # per-run upstream-electricity LCI
                scenarios.build_all_scenarios(db, cfg, mix_source=p.electricity_mix,
                                              upstream_reshoring=p.upstream_reshoring)
                tables = _tables_for_run(db, cfg, p, scenario_list, heavy)
                _write_run(runs_dir / _run_key(p), tables, heavy)
                n_done += 1
                _log(f"[{n_done}/{len(todo)}] {p.label()} -> written "
                     f"({_fmt(time.time() - t)}, elapsed {_fmt(time.time() - t_start)})")
            del db, clean                          # free the per-(cf,eff) base
        del db_cf

    t = time.time()
    combine_runs(outdir, heavy=heavy)
    _log(f"combined shards -> tidy tables in {_fmt(time.time() - t)}")
    _log(f"DONE: {n_done} run(s) in {_fmt(time.time() - t_start)} -> {outdir}")
    return outdir


# convenient default grid covering all levers
def default_grid() -> list[Params]:
    from .params import grid
    return grid(
        Params(),
        capacity_factor=["RN", "OWID"],
        electricity_mix=["WEO_STEPS", "EMBER"],
        module_efficiency=[0.195, 0.22, 0.24],
        upstream_reshoring=[None, 0.4, 0.8],
    )


def sensitivity_grid() -> list[Params]:
    """Sensitivity design: the central case plus three purpose-built blocks, *not* a
    full Cartesian product (which would be hundreds of runs, most uninterpretable).

    Central case = OWID, WEO_STEPS, 0.195, no forced upstream, no degradation, IEA LCI.

    Block 1 — one-at-a-time (OAT): the central case with a *single* uncertainty lever
      moved, isolating each lever's marginal effect. Source for the lever-ranking
      (tornado) figure. Levers: capacity factor, module efficiency, degradation, LCI.

    Block 2 — envelope corners: the absolute min/max of the per-region footprint sits
      at the corners of the uncertainty cube (each physical lever is a monotone,
      separable factor on the footprint), so four corners suffice to bound every
      region exactly — without the full cube. Two corners per capacity-factor side,
      because the capacity factor is the one non-monotone lever (RN raises 18 regions
      but lowers CN/CH/NO). Module efficiency, degradation and LCI are taken at their
      footprint-raising / footprint-lowering extremes.

    Block 3 — scenario axes: the policy levers (these are analysis choices, not
      uncertainty). upstream_reshoring is scanned 0..1 (R1.7 leakage threshold, R2.3a)
      and the alternative 2030 grid mix (EMBER) is added as one OAT point.

    Params is a frozen dataclass (hashable), so the union deduplicates shared points.
    Base builds are shared by (capacity_factor, degradation_rate).
    """
    central = Params()

    # Block 1 — OAT (one uncertainty lever moved from central)
    oat = [
        Params(capacity_factor="RN"),
        Params(module_efficiency=0.22),
        Params(module_efficiency=0.24),
        Params(degradation_rate=0.005),
        Params(lci_variant="NREL"),
        Params(electricity_mix="EMBER"),          # alternative 2030 grid (scenario axis)
    ]

    # Block 2 — four envelope corners (footprint-raising = eff 0.195, deg 0.005, NREL;
    # footprint-lowering = eff 0.24, deg 0.0, IEA), one pair per capacity-factor side
    corners = [
        Params(capacity_factor="RN",   module_efficiency=0.195, degradation_rate=0.005, lci_variant="NREL"),
        Params(capacity_factor="OWID", module_efficiency=0.195, degradation_rate=0.005, lci_variant="NREL"),
        Params(capacity_factor="OWID", module_efficiency=0.24,  degradation_rate=0.0,   lci_variant="IEA"),
        Params(capacity_factor="RN",   module_efficiency=0.24,  degradation_rate=0.0,   lci_variant="IEA"),
    ]

    # Block 3 — upstream reshoring scan (0.4 == as-published, already the central NZIA)
    upstream = [Params(upstream_reshoring=v) for v in (0.0, 0.2, 0.6, 0.8, 1.0)]

    runs = {central, *oat, *corners, *upstream}
    return sorted(runs, key=lambda p: p.label())
