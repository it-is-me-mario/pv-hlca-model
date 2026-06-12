"""One-off: extract hard-coded data from the thesis script main_mario_EU_new.py
into clean config files (csv/yaml) for the reproducible repo. Faithful by exec.
Run once with any python that has pandas + pyyaml."""
import re, csv
from pathlib import Path

THESIS = Path("/Users/lorenzorinaldi/Library/CloudStorage/OneDrive-PolitecnicodiMilano/Documenti/publications/2025_Merletti_PV HLCA/Tesi/Mario/main_mario_EU_new.py")
REPO = Path("/Users/lorenzorinaldi/Library/CloudStorage/OneDrive-PolitecnicodiMilano/Documenti/publications/2025_Merletti_PV HLCA/pv_hlca_repro")
L = THESIS.read_text().splitlines(keepends=True)

def block(a, b):  # 1-indexed inclusive
    return "".join(L[a-1:b])

# ---- IRENA / shock parameters (284-323) ----
ns = {}
exec(block(284, 323), ns)
import yaml
params = {
    'W_per_m2': ns['W_per_m2'],
    'usd_to_eur': ns['usd_to_eur'],
    'use_of_PV_m2_per_TJ': ns['use_of_PV'],
    'lifetime_years': ns['lifetime_years'],
    'om_labor_share': ns['om_labor_share'],
    'gwp_factors': {'Carbon dioxide': 1, 'N2O': 265, 'CH4': 28},
    'kWh_per_TJ_to_g_factor': 3.6,
    'irena': {
        'total_capex_usd_per_w': ns['Total_capex_usd_per_w'],
        'installation_labor_fraction': ns['Installation_labor_fraction'],
        'pv_modules_fraction': ns['PV_modules_fraction'],
        'o_and_m_usd_per_kw_year': ns['O_and_M_dollars_per_kW'],
    },
}
(REPO / "config" / "parameters.yaml").write_text(
    "# PV-HLCA parameters — extracted verbatim from thesis script (IRENA 2024, etc.)\n"
    + yaml.safe_dump(params, sort_keys=False, allow_unicode=True))
print("wrote config/parameters.yaml")

# ---- child->parent mapping + short_to_full (347-462) ----
ns2 = {'np': __import__('numpy'), 'pd': __import__('pandas')}
# only the two dict literals
exec(block(359, 409), ns2)   # short_to_full
exec(block(454, 462), ns2)   # child_parent_map
maps = {'region_code_to_full_name': ns2['short_to_full'],
        'new_activity_parent': ns2['child_parent_map']}
(REPO / "config" / "mappings.yaml").write_text(
    "# Region code->OWID name and new-activity->parent-activity (VA/employment regionalization)\n"
    + yaml.safe_dump(maps, sort_keys=False, allow_unicode=True))
print("wrote config/mappings.yaml")

# ---- import structures baseline (603-868) and NZIA (945-1210) ----
def extract_imports(a, b):
    nse = {}
    exec(block(a, b), nse)
    return nse['import_data_dict']  # commodity -> list[(importer, exporter, share)]

def dump_imports(d, scenario, writer):
    for commodity, lst in d.items():
        seen = set()
        for importer, exporter, share in lst:
            # de-dup identical rows that come from shared lists (wafer/ingot share one list)
            key = (scenario, commodity, importer, exporter)
            if key in seen:
                continue
            seen.add(key)
            writer.writerow([scenario, commodity, importer, exporter, share])

base = extract_imports(603, 868)
nzia = extract_imports(945, 1210)
with open(REPO / "config" / "import_structure.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["scenario", "commodity", "importer", "exporter", "share"])
    dump_imports(base, "baseline", w)
    dump_imports(nzia, "NZIA", w)
print("wrote config/import_structure.csv  (baseline+NZIA)")

# ---- 2030 EU27 stated-policy electricity mix (1355-1365) ----
ns3 = {}
exec(block(1355, 1365), ns3)
mix = {'EU27_2030_stated_policy_shares': ns3['energy_mix_EU27_2030_stated_policy'],
       'source': 'Ember New Generation 2022 (https://ember-energy.org/app/uploads/2022/06/Report-New-Generation-23.06.22.pdf)',
       'household_demand_constant_460x3600': True}
(REPO / "config" / "scenario_2030.yaml").write_text(
    "# EU27 2030 stated-policy electricity mix (used to rescale Y and use-block for *_2030 and NZIA)\n"
    + yaml.safe_dump(mix, sort_keys=False, allow_unicode=True))
print("wrote config/scenario_2030.yaml")

# ---- RoW capacity factors (Renewables Ninja) for OWID path (122-130) ----
ns4 = {}
exec(block(122, 131), ns4)
print("RoW CF:", ns4.get('Capacity_factor_RoW'))
(REPO / "config" / "capacity_factor_row.yaml").write_text(
    "# Rest-of-World capacity factors (estimated from Renewables Ninja), OWID path\n"
    + yaml.safe_dump({'capacity_factor_RoW': ns4['Capacity_factor_RoW']}, sort_keys=False))
print("wrote config/capacity_factor_row.yaml")
print("DONE")
