"""Additive, provenance-aware biological production projections.

This module never changes the saved mission, creates edible inventory, infers
nutrients from images, or commands hardware. Literature coefficients are
terrestrial benchmarks; resource, startup and commissioning inputs are reviewed
scenario assumptions. Unknown coefficients stay unknown. Catalyst experiments
without harvest/composition data remain research records rather than food.
"""
from __future__ import annotations

from copy import deepcopy
from math import isclose, isfinite

from .crop_advisor import _headroom, _unallocated_stores
from .model import HabitatConfig, Scenario
from .nutrition import active_crew_context
from .planner import PlanResult

EPS = 1e-8
NUTRIENT_UNITS = {"protein": "g", "iron": "mg", "vitamin_c": "mg", "zeaxanthin": "mg"}
SCOPE = ("Additional biological production projection using literature and reviewed inputs; "
         "not measured harvest, consumed food, clinical supplementation or hardware control. "
         "The saved mission and its food allocations are unchanged.")


def _profile(id, name, category, organism, strain, unit, status, description,
             defaults, reference, limitations, *, simulatable=True):
    return {"id": id, "name": name, "category": category, "organism": organism,
            "strain": strain, "capacity_unit": unit, "evidence_status": status,
            "description": description, "literature_defaults": defaults,
            "references": [reference], "limitations": limitations,
            "simulatable": simulatable, "food_qualification": "Not established for this habitat batch"}


_PROFILES = [
    _profile("limnospira_pc8005", "Limnospira protein photobioreactor", "microbial_protein",
        "Limnospira indica (cyanobacterium; Spirulina-type)", "PC8005", "L",
        "terrestrial_matched_run_reference",
        "Continuous-culture protein biomass benchmark from the MELiSSA 83 L ground photobioreactor.",
        {"biomass_g_per_unit_day": .492, "biomass_basis": "dry", "protein_fraction": .42,
         "media_l_per_unit_day": .6},
        {"title": "Garcia-Gragera et al., continuous Limnospira culture (2021/2022)",
         "url": "https://enviromicro-journals.onlinelibrary.wiley.com/doi/10.1111/1751-7915.13882",
         "detail": "Matched Run 6: 0.82 g dry biomass/L × dilution 0.025/h × 24 h = 0.492 g/L/day; protein 42.0% dry weight (Table 3). Gross medium throughput 0.6 L/L/day. Not the cross-run maximum productivity or maximum protein percentage."},
        ["Ground steady-state benchmark; linear scale transfer is an assumption, not a calibrated small-reactor model.",
         "Startup, total water and electrical use require reviewed inputs. Gross medium flow is not net freshwater use with measured recovery.",
         "No active vitamin B12, oxygen production, CO2 removal or food-quality credit is inferred."]),
    _profile("wolffia_globosa", "Wolffia enriched-medium culture", "assisted_aquatic_plant",
        "Wolffia globosa (aquatic flowering plant)", "Study-specific Chlorella-medium tanks", "m2",
        "terrestrial_net_growth_reference",
        "Watermeal nutrient-production candidate; medium enrichment is nutrient supply, not a chemical catalyst.",
        {"biomass_g_per_unit_day": 42.14, "biomass_basis": "fresh",
         "dry_matter_fraction": 4.83 / 42.14, "protein_fraction": .461},
        {"title": "Cultivation of Wolffia globosa and functional food development (2025)",
         "url": "https://www.nature.com/articles/s41598-025-22032-z",
         "detail": "Chlorella-medium tanks: week-one net growth 42.14 g fresh/m2/day, corresponding 4.83 g dry/m2/day; protein 46.10% dry weight. Eight weekly fresh rates are used with weekly harvests. Starter biomass is excluded. The week-one dry fraction and medium-level protein percentage are transferred across weeks as an explicit assumption."},
        ["Fresh biomass cannot be multiplied directly by dry-weight protein percentage.",
         "Eight-week terrestrial net growth sequence; no extrapolation beyond 56 productive days without reviewed yield/composition inputs.",
         "Week-one dry fraction and medium-level composition are not separately measured for every weekly harvest. Water, medium, startup and electricity need reviewed inputs.",
         "No assured space yield, active B12 contribution or capsule equivalence."]),
    _profile("euglena_ccap_1224_5z", "Euglena research protein culture", "microbial_protein",
        "Euglena gracilis (single-celled microalga)", "CCAP 1224/5Z research strain", "L",
        "terrestrial_research_composition",
        "Research culture with protein composition evidence; carbon feed and operational coefficients are not supplied by this profile.",
        {"protein_fraction": .661, "biomass_basis": "dry"},
        {"title": "Optimization of heterotrophic Euglena culture for protein (2023)",
         "url": "https://www.mdpi.com/1660-3397/21/10/519",
         "detail": "Protein content reached 66.10% dry weight under a specific research treatment. This is not a default growth rate and is not evidence that this research strain/process equals a separately qualified food product."},
        ["Requires reviewed matched yield, feedstock/medium, startup and operational resource coefficients.",
         "Research strain/process identity and habitat food qualification remain unestablished."], simulatable=False),
    _profile("bionutrients_yeast", "BioNutrients engineered yeast", "targeted_nutrient_research",
        "Engineered yeast", "NASA nutrient-specific strains", "L", "research_only",
        "Targeted beta-carotene or zeaxanthin manufacturing concept, inspired by NASA BioNutrients.", {},
        {"title": "NASA BioNutrients", "url": "https://www.nasa.gov/general/what-is-bionutrients/",
         "detail": "48-hour incubations demonstrate specific engineered nutrient-production experiments; this profile has no public matched nutrient yield in mg per reactor/day."},
        ["Ordinary baker's yeast cannot substitute for the engineered strain.",
         "No qualified nutrient-yield and resource dataset: no food or capsule-equivalent output is calculated."], simulatable=False),
    _profile("electrocatalytic_acetate_microbes", "CO2-to-acetate microbial production", "electrocatalytic_research",
        "Acetate-fed algae, yeast or mushroom-producing fungus", "Organism/process-specific", "L",
        "research_only", "A true inorganic–biological route: electrocatalytic acetate supplies carbon and energy to organisms.", {},
        {"title": "Hybrid inorganic–biological artificial photosynthesis (2022)",
         "url": "https://www.nature.com/articles/s43016-022-00530-x",
         "detail": "Two-stage electrochemical CO2-to-acetate production supported tested organisms in darkness. Carbon selectivity is not edible protein yield or a habitat energy balance."},
        ["Electrolyser, catalyst, acetate quality, downstream yields and full electrical/processing costs are not modelled.",
         "No numeric food output until a matched full-process yield/resource dataset exists."], simulatable=False),
    _profile("acetate_assisted_seedlings", "Electrocatalytic acetate + crop seedlings", "assisted_plant_research",
        "Micro-Tom tomato / Kitaake rice / cowpea CB46", "Tested seedling cultivars", "m2", "research_only",
        "Plant-plus-catalyst research route: CO2-derived acetate carbon incorporation in tested crop tissues.", {},
        {"title": "Hybrid artificial photosynthesis: crop carbon incorporation (2022)",
         "url": "https://www.nature.com/articles/s43016-022-00530-x",
         "detail": "Seedlings grown in light incorporated labelled acetate carbon. External Ag/IrO2 and Cu/NiFe-oxide electrolysis stages make acetate; the metal catalysts are not added to plant trays. Complete fruit harvest, nutrient enrichment and dark-grown crop food yield are not established."},
        ["Seedling carbon incorporation is not evidence of higher fruit protein or capsule-equivalent nutrition.",
         "No catalyst dose, growing recipe or edible yield multiplier is provided."], simulatable=False),
    _profile("iron_biofortified_red_cabbage", "Iron-biofortified red cabbage microgreens", "plant_biofortification",
        "Brassica oleracea red cabbage microgreens", "Study-specific cultivar/treatment", "m2",
        "requires_reviewed_harvest_and_composition",
        "Targeted mineral enrichment candidate; supplied iron is a resource input, not a catalyst or newly created mineral.", {},
        {"title": "Zinc and iron agronomic biofortification of microgreens (2019)",
         "url": "https://www.mdpi.com/2073-4395/9/11/677",
         "detail": "Treatment-specific relative tissue enrichment is evidence of an effect, not a universal final iron concentration. No 278% multiplier is applied to an unrelated crop composition."},
        ["Requires compatible final harvested composition and yield, not a relative enrichment percentage alone.",
         "Plant mineral content is not a validated absorption estimate or treatment for deficiency."], simulatable=False),
    _profile("nanozyme_cucumber_research", "Antioxidant nanozymes + cucumber seedlings", "nano_assisted_plant_research",
        "Cucumis sativus experimental seedlings", "Study-specific Mn3O4 nanozymes", "m2", "research_only",
        "Catalytic antioxidant assistance for seedling stress resilience; not an operational food-production treatment.", {},
        {"title": "Mn3O4 nanozymes improve cucumber seedling performance under salinity (2020)",
         "url": "https://pubs.rsc.org/en/content/articlehtml/2020/en/d0en00214c",
         "detail": "Tested nanozymes altered antioxidant defenses, photosynthesis and seedling biomass under salinity. Mature fruit yield, harvested nutrient composition and food-qualified treatment are not established."},
        ["No edible nutrient yield, safe food process, space performance or transferable catalytic multiplier is established.",
         "Research-only record; no growing dose or hardware command is generated."], simulatable=False),
]

_WOLFFIA_WEEKLY_FRESH = [42.14, 30.57, 34.16, 33.72, 40.58, 26.68, 23.90, 24.79]
_PROFILES[1]["weekly_net_fresh_g_per_m2_day"] = list(_WOLFFIA_WEEKLY_FRESH)
_PROFILES[1]["harvest_interval_days"] = 7


def bioproduction_catalog() -> dict:
    return {"profiles": deepcopy(_PROFILES), "nutrient_units": dict(NUTRIENT_UNITS), "scope": SCOPE,
        "assumptions": ["Literature defaults are comparisons, not measured local performance.",
            "Total operational water includes aqueous medium; the simulator does not claim recovery.",
            "New reactor fills consume water and medium before any production.",
            "All outputs remain separate from the saved mission food inventory."]}


def _number(value, name, *, maximum=1e9, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0 or value > maximum:
        raise ValueError(f"{name} must be a finite nonnegative number no greater than {maximum:g}.")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive.")
    return float(value)


def _integer(value, name, low=0, high=3650):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}.")
    return value


def _resolve_module(raw, profiles, focus):
    allowed = {"id", "profile_id", "size", "size_unit", "startup_days", "biomass_g_per_unit_day", "biomass_basis",
        "dry_matter_fraction", "protein_fraction", "nutrients_mg_per_g_dry", "water_l_per_unit_day",
        "power_kwh_per_unit_day", "media_l_per_unit_day", "commissioning_water_l",
        "commissioning_power_kwh", "commissioning_media_l"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("Biological modules must be objects with supported coefficient fields.")
    if not isinstance(raw.get("id"), str) or not raw["id"].strip() or len(raw["id"]) > 100:
        raise ValueError("Every biological module needs a nonempty id of at most 100 characters.")
    if not isinstance(raw.get("profile_id"), str) or raw["profile_id"] not in profiles:
        raise ValueError("Unknown biological production profile.")
    profile = profiles[raw["profile_id"]]
    if raw.get("size_unit") != profile["capacity_unit"]:
        raise ValueError(f"{profile['name']} requires capacity in {profile['capacity_unit']}; incompatible units cannot be converted implicitly.")
    size = _number(raw.get("size"), "Module capacity", maximum=1e5, positive=True)
    startup = _integer(raw.get("startup_days"), "Reviewed startup days")
    defaults = profile["literature_defaults"]
    coefficients, provenance, reasons = {}, {}, []
    for key in ("biomass_g_per_unit_day", "biomass_basis", "dry_matter_fraction", "protein_fraction",
                "water_l_per_unit_day", "power_kwh_per_unit_day", "media_l_per_unit_day"):
        coefficients[key] = raw.get(key, defaults.get(key))
        provenance[key] = "reviewed_scenario_input" if key in raw else "literature_reference" if key in defaults else "unknown"
        value = coefficients[key]
        if key == "biomass_basis":
            if value is not None and value not in ("dry", "fresh"):
                raise ValueError("Biomass basis must be 'dry' or 'fresh'.")
        elif value is not None:
            coefficients[key] = _number(value, key, maximum=1 if key.endswith("fraction") else 1e6,
                                        positive=key == "dry_matter_fraction")
    # Preserve paired reference treatments: swapping in a percentage from
    # another run cannot silently retain a literature production rate.
    if defaults.get("biomass_g_per_unit_day") is not None and defaults.get("protein_fraction") is not None:
        changed = [key for key in ("biomass_g_per_unit_day", "protein_fraction")
                   if key in raw and (raw[key] is None or not isclose(raw[key], defaults[key], rel_tol=1e-9, abs_tol=EPS))]
        if changed and not all(key in raw for key in ("biomass_g_per_unit_day", "protein_fraction")):
            reasons.append("A changed literature yield/protein pair requires both coefficients to be reviewed together; cross-run maxima were not combined.")
        if changed:
            for key in ("biomass_g_per_unit_day", "protein_fraction"):
                provenance[key] = "reviewed_scenario_pair; no longer matched literature run"
    for key in ("biomass_g_per_unit_day", "biomass_basis", "water_l_per_unit_day", "power_kwh_per_unit_day", "media_l_per_unit_day"):
        if coefficients[key] is None:
            reasons.append(f"Missing reviewed {key}; no coefficient was invented.")
    if coefficients["biomass_basis"] == "fresh" and coefficients["dry_matter_fraction"] is None:
        reasons.append("Fresh yield requires a reviewed dry_matter_fraction before dry-basis nutrients can be calculated.")
    if coefficients["biomass_basis"] == "fresh" and provenance["protein_fraction"] == "literature_reference" and profile["id"] != "wolffia_globosa":
        # Literature composition may be a different harvest than this user
        # supplied fresh rate/fraction; expose the transfer instead of claiming
        # a matched reference yield-composition experiment.
        provenance["protein_fraction"] = "literature_composition_transfer_assumption; not a matched local batch"
    if coefficients["water_l_per_unit_day"] is not None and coefficients["media_l_per_unit_day"] is not None:
        if coefficients["water_l_per_unit_day"] + EPS < coefficients["media_l_per_unit_day"]:
            raise ValueError("Total daily water must include the aqueous medium volume; water cannot be smaller than media.")
    nutrients = raw.get("nutrients_mg_per_g_dry", {})
    if not isinstance(nutrients, dict) or set(nutrients) - (set(NUTRIENT_UNITS) - {"protein"}):
        raise ValueError("Dry-biomass nutrient composition must use supported mg/g identifiers.")
    nutrients = {name: _number(value, f"{name} mg/g dry biomass", maximum=1000) for name, value in nutrients.items()}
    if focus == "protein" and coefficients["protein_fraction"] is None:
        reasons.append("Protein composition is unknown; no protein contribution can be projected.")
    elif focus != "protein" and focus not in nutrients:
        reasons.append(f"Final {focus} composition in mg/g dry biomass is unknown; relative enrichment is not a final concentration.")
    commissioning = {}
    for resource, field in (("water_l", "commissioning_water_l"), ("power_kwh", "commissioning_power_kwh"), ("media_l", "commissioning_media_l")):
        value = raw.get(field)
        if value is None and resource != "power_kwh" and profile["capacity_unit"] == "L":
            value = size
            provenance[field] = "geometric_initial_aqueous_fill_assumption"
        else:
            provenance[field] = "reviewed_scenario_input" if field in raw else "unknown"
        commissioning[resource] = _number(value, field) if value is not None else None
        if value is None:
            reasons.append(f"Missing reviewed {field}; commissioning is not treated as free.")
    if commissioning["water_l"] is not None and commissioning["media_l"] is not None and commissioning["water_l"] + EPS < commissioning["media_l"]:
        raise ValueError("Commissioning water must include its aqueous medium volume.")
    if not profile["simulatable"]:
        reasons.insert(0, "Research-only profile: no matched edible-yield/composition/resource dataset; arbitrary supplied coefficients cannot qualify it for food simulation.")
    # The weekly terrestrial fresh-mass series describes growth, so nutrient
    # conversion overrides (dry-matter or protein fraction) must not discard it.
    use_weekly_reference = profile["id"] == "wolffia_globosa" and all(
        coefficients[key] == defaults.get(key) for key in ("biomass_g_per_unit_day", "biomass_basis"))
    return {"id": raw["id"], "profile_id": profile["id"], "name": profile["name"], "size": size,
        "size_unit": profile["capacity_unit"], "startup_days": startup, "coefficients": coefficients,
        "nutrients_mg_per_g_dry": nutrients, "commissioning": commissioning,
        "provenance": {**provenance, "startup_days": "reviewed_scenario_input", "size": "reviewed_scenario_input",
                       "nutrients_mg_per_g_dry": "reviewed_scenario_input" if nutrients else "unknown"},
        "exclusion_reasons": reasons, "simulatable": not reasons,
        "weekly_net_fresh_g_per_m2_day": list(_WOLFFIA_WEEKLY_FRESH) if use_weekly_reference else None,
        "harvest_interval_days": 7 if profile["id"] == "wolffia_globosa" else 1,
        "references": deepcopy(profile["references"]), "limitations": list(profile["limitations"])}


def _clean(value):
    if not isfinite(value):
        raise ValueError("Coefficient combination exceeded finite numerical range.")
    return max(0.0, value)


def simulate_bioproduction(config: HabitatConfig, plan: PlanResult | None, request: dict,
                          scenario: Scenario | None = None, *, earliest_start_day: int = 1) -> dict:
    """Compare extra production against resources unallocated in the saved plan.

    Allocation order is the submitted module order; a fully funded module runs,
    while a short-funded module is held with no output/resource draw. Holding is
    an accounting rule, not a model of biological survival or restart kinetics.
    """
    config.validate()
    scenario = scenario or Scenario("bioproduction", "Reviewed mission inputs", event_day=config.days + 1)
    scenario.validate(config)
    allowed = {"start_day", "horizon_days", "focus_nutrient", "modules", "reviewed_inputs", "events",
               "daily_water_budget_l", "daily_power_budget_kwh", "daily_media_budget_l",
               "initial_water_l", "initial_power_kwh", "initial_media_l"}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError("Biological production request contains unsupported fields.")
    if request.get("reviewed_inputs") is not True:
        raise ValueError("Review and acknowledge scenario coefficients before projecting biological production.")
    earliest = _integer(earliest_start_day, "Earliest prospective day", low=1, high=config.days)
    start = _integer(request.get("start_day"), "Start day", low=earliest, high=config.days)
    horizon = _integer(request.get("horizon_days"), "Horizon days", low=1, high=config.days - start + 1)
    end = start + horizon - 1
    focus = request.get("focus_nutrient", "protein")
    if not isinstance(focus, str) or focus not in NUTRIENT_UNITS:
        raise ValueError("Unsupported biological production nutrient focus.")
    raw_modules = request.get("modules")
    if not isinstance(raw_modules, list) or not 1 <= len(raw_modules) <= 20:
        raise ValueError("Provide between one and twenty biological modules.")
    profiles = {profile["id"]: profile for profile in _PROFILES}
    modules = [_resolve_module(raw, profiles, focus) for raw in raw_modules]
    ids = [module["id"] for module in modules]
    if len(ids) != len(set(ids)):
        raise ValueError("Biological module identifiers must be unique.")
    caps = {}
    for resource, field in (("water_l", "daily_water_budget_l"), ("power_kwh", "daily_power_budget_kwh"), ("media_l", "daily_media_budget_l")):
        caps[resource] = _number(request[field], field) if field in request else None
    if caps["media_l"] is None:
        raise ValueError("A reviewed daily media budget is required; feedstock capacity is not invented.")
    rows = {row["day"]: row for row in plan.daily} if plan else {}
    free_stores = _unallocated_stores(config, rows, start)
    stores, store_provenance = {}, {}
    for resource, field, saved_key in (("water_l", "initial_water_l", "water_l"),
                                      ("power_kwh", "initial_power_kwh", "energy_kwh"),
                                      ("media_l", "initial_media_l", None)):
        known = free_stores[saved_key] if saved_key else {"configured": False, "remaining": None}
        value = _number(request[field], field) if field in request else None
        if known["configured"]:
            if known["remaining"] is None:
                raise ValueError("A configured finite mission store lacks a closing saved forecast; no extra biological allocation can be established.")
            if value is not None and value > known["remaining"] + EPS:
                raise ValueError(f"{field} exceeds the saved mission's unallocated closing store; existing resource commitments cannot be reused.")
            value = known["remaining"] if value is None else value
            store_provenance[resource] = "Within saved mission unallocated closing store"
        else:
            store_provenance[resource] = "Reviewed additional-module store" if value is not None else "Unspecified finite store; only daily delivery capacity is checked"
        stores[resource] = value
    raw_events = request.get("events", [])
    if not isinstance(raw_events, list) or len(raw_events) > 100:
        raise ValueError("Resource events must be a list with at most 100 entries.")
    events = []
    for event in raw_events:
        if not isinstance(event, dict) or set(event) - {"day", "water_factor", "power_factor", "media_factor", "production_factor"}:
            raise ValueError("Biological production events contain unsupported fields.")
        normalized = {"day": _integer(event.get("day"), "Resource event day", low=start, high=end)}
        for field in ("water_factor", "power_factor", "media_factor", "production_factor"):
            normalized[field] = _number(event.get(field, 1), field, maximum=1)
        events.append(normalized)
    if len({event["day"] for event in events}) != len(events):
        raise ValueError("Combine biological resource factors into one event per mission day.")
    events.sort(key=lambda row: row["day"])
    state = {module["id"]: {"commissioned": False, "funded_startup_days": 0,
                          "production_age_days": 0, "unharvested_biomass_g": 0.0} for module in modules}
    totals = {"biomass_dry_g": 0.0, "protein_g": 0.0, "water_l": 0.0, "power_kwh": 0.0, "media_l": 0.0,
              "focus_nutrient_output": 0.0}
    nutrient_totals = {nutrient: 0.0 for nutrient in NUTRIENT_UNITS}
    nutrient_known = {nutrient: False for nutrient in NUTRIENT_UNITS}
    daily, all_reasons = [], []
    for day in range(start, end + 1):
        saved_row = rows.get(day, {})
        headroom = _headroom(config, plan, saved_row, day, scenario)
        factors = {"water_factor": 1.0, "power_factor": 1.0, "media_factor": 1.0, "production_factor": 1.0}
        for event in events:
            if event["day"] <= day:
                for field in factors:
                    factors[field] *= event[field]
        limits = {"water_l": headroom["water_l"], "power_kwh": headroom["power_kwh"], "media_l": caps["media_l"]}
        for resource, factor in (("water_l", "water_factor"), ("power_kwh", "power_factor"), ("media_l", "media_factor")):
            if caps[resource] is not None:
                limits[resource] = min(limits[resource], caps[resource])
            limits[resource] *= factors[factor]
            if stores[resource] is not None:
                limits[resource] = min(limits[resource], stores[resource])
        remaining = dict(limits)
        reserved_area = sum(module["size"] for module in modules
                            if module["size_unit"] == "m2" and state[module["id"]]["commissioned"])
        available_area = max(0.0, headroom["area_m2"] - reserved_area)
        output = []
        for module in modules:
            module_state = state[module["id"]]
            row = {"id": module["id"], "name": module["name"], "status": "excluded", "exclusion_reasons": list(module["exclusion_reasons"]),
                   "biomass_dry_g": 0.0, "biomass_fresh_g": None, "protein_g": None,
                   "nutrients": dict.fromkeys(NUTRIENT_UNITS), "water_l": 0.0, "power_kwh": 0.0, "media_l": 0.0,
                   "commissioning": {"water_l": 0.0, "power_kwh": 0.0, "media_l": 0.0},
                   "funded_startup_days": module_state["funded_startup_days"]}
            if module["simulatable"]:
                coef = module["coefficients"]
                area_reserved = module["size_unit"] == "m2" and module_state["commissioned"]
                need = {resource: module["size"] * coef[field] for resource, field in
                        (("water_l", "water_l_per_unit_day"), ("power_kwh", "power_kwh_per_unit_day"), ("media_l", "media_l_per_unit_day"))}
                fill = module["commissioning"] if not module_state["commissioned"] else dict.fromkeys(need, 0.0)
                required = {resource: _clean(need[resource] + fill[resource]) for resource in need}
                reasons = [f"{resource}: needs {required[resource]:.6g}, only {remaining[resource]:.6g} unallocated today."
                           for resource in required if required[resource] > remaining[resource] + EPS]
                if area_reserved and reserved_area > headroom["area_m2"] + EPS:
                    reasons.append("The commissioned tray no longer fits the saved mission's available growing area.")
                elif module["size_unit"] == "m2" and not area_reserved and module["size"] > available_area + EPS:
                    reasons.append(f"area_m2: needs {module['size']:.6g}, only {available_area:.6g} unallocated today.")
                if module["weekly_net_fresh_g_per_m2_day"] and module_state["production_age_days"] >= 56:
                    reasons.append("Eight-week reference exhausted; a reviewed longer-duration yield/composition pair is required.")
                row["required_resources"] = required
                if reasons:
                    row["status"], row["exclusion_reasons"] = "resource_hold", reasons
                    all_reasons.extend(f"Day {day}, {module['name']}: {reason}" for reason in reasons)
                else:
                    for resource in required:
                        row[resource] = required[resource]
                        remaining[resource] = max(0.0, remaining[resource] - required[resource])
                        if stores[resource] is not None:
                            stores[resource] = max(0.0, stores[resource] - required[resource])
                    if module["size_unit"] == "m2" and not area_reserved:
                        available_area = max(0.0, available_area - module["size"])
                    row["commissioning"] = dict(fill)
                    module_state["commissioned"] = True
                    startup = module_state["funded_startup_days"] < module["startup_days"]
                    row["status"] = "startup" if startup else "projected_production"
                    if startup:
                        module_state["funded_startup_days"] += 1
                    produced = 0.0
                    if not startup:
                        rate = coef["biomass_g_per_unit_day"]
                        if module["weekly_net_fresh_g_per_m2_day"]:
                            rate = module["weekly_net_fresh_g_per_m2_day"][module_state["production_age_days"] // 7]
                        module_state["production_age_days"] += 1
                        module_state["unharvested_biomass_g"] += _clean(module["size"] * rate * factors["production_factor"])
                        if module_state["production_age_days"] % module["harvest_interval_days"] == 0:
                            produced = module_state["unharvested_biomass_g"]
                            module_state["unharvested_biomass_g"] = 0.0
                        else:
                            row["status"] = "growing_until_harvest"
                    if coef["biomass_basis"] == "fresh":
                        row["biomass_fresh_g"] = produced
                        produced *= coef["dry_matter_fraction"]
                    row["biomass_dry_g"] = produced
                    row["nutrients"]["protein"] = produced * coef["protein_fraction"] if coef["protein_fraction"] is not None else None
                    row["protein_g"] = row["nutrients"]["protein"]
                    for nutrient, amount in module["nutrients_mg_per_g_dry"].items():
                        row["nutrients"][nutrient] = produced * amount
                    row["funded_startup_days"] = module_state["funded_startup_days"]
            row["production_age_days"] = module_state["production_age_days"]
            row["unharvested_biomass_g"] = module_state["unharvested_biomass_g"]
            output.append(row)
        nutrients = {nutrient: sum(row["nutrients"][nutrient] or 0.0 for row in output)
                     if any(row["nutrients"][nutrient] is not None for row in output) else None for nutrient in NUTRIENT_UNITS}
        context = active_crew_context(config, day, saved_row, scenario)
        protein_target = context["aggregate_daily_targets"].get("protein")
        row = {"day": day, "crew_context": context, "crew_protein_target_g": protein_target,
               "protein_g": nutrients["protein"], "biomass_dry_g": sum(item["biomass_dry_g"] for item in output),
               "nutrients": nutrients, "focus_nutrient_output": nutrients[focus], "resource_budgets": limits,
               "resources_remaining_today": remaining, "finite_stores_remaining": dict(stores),
               "protein_target_share": nutrients["protein"] / protein_target if nutrients["protein"] is not None and protein_target else None,
               "modules": output, "area_remaining_m2": available_area}
        for resource in ("water_l", "power_kwh", "media_l"):
            row[resource] = sum(item[resource] for item in output)
        for key in totals:
            totals[key] += row[key] or 0.0
        for nutrient, amount in nutrients.items():
            if amount is not None:
                nutrient_totals[nutrient] += amount
                nutrient_known[nutrient] = True
        row["cumulative"] = dict(totals)
        daily.append(row)
    # Zero accounting output for a held module is not a measured nutrient zero.
    totals["nutrients"] = {nutrient: nutrient_totals[nutrient] if nutrient_known[nutrient] else None for nutrient in NUTRIENT_UNITS}
    totals["protein_g"] = totals["nutrients"]["protein"]
    totals["focus_nutrient_output"] = totals["nutrients"][focus]
    totals["protein_g_per_kwh"] = totals["protein_g"] / totals["power_kwh"] if totals["protein_g"] is not None and totals["power_kwh"] > EPS else None
    targets = [row["crew_protein_target_g"] for row in daily]
    totals["crew_protein_target_g"] = sum(targets) if all(target is not None for target in targets) else None
    totals["protein_target_share"] = totals["protein_g"] / totals["crew_protein_target_g"] if totals["protein_g"] is not None and totals["crew_protein_target_g"] else None
    totals["production_days"] = sum(any(module["status"] == "projected_production" for module in row["modules"]) for row in daily)
    totals["resource_hold_days"] = sum(any(module["status"] == "resource_hold" for module in row["modules"]) for row in daily)
    references = {reference["url"]: reference for module in modules for reference in module["references"]}
    return {"scope": SCOPE, "start_day": start, "end_day": end, "focus_nutrient": focus,
        "nutrient_units": dict(NUTRIENT_UNITS), "modules": modules, "daily": daily, "totals": totals,
        "inputs": deepcopy(request), "events": events, "finite_store_provenance": store_provenance,
        "references": list(references.values()), "resource_hold_reasons": all_reasons,
        "warnings": ["No output is added to saved food inventory or credited to crew nutrient supply.",
            "Linear literature transfer, reviewed startup and resource coefficients are assumptions, not a trained growth model.",
            "Total water includes medium water; gross media supply is tracked separately without double-counting water.",
            "Initial fill and commissioning are charged before output. Held operation produces nothing; survival and restart after a hold are not validated.",
            "Module order determines allocation priority. Reactor physical footprint is not inferred from liquid volume.",
            "Projected composition is not food qualification, absorption, active B12 evidence, or capsule equivalence."]}
