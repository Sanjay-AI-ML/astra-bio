"""Adapters connecting measured endpoints and composition to reviewed scenarios."""
from dataclasses import replace

from .crop_growth import estimate_led_energy, load_reference_crops
from .model import CropSpec
from .nutrition import composition_for_species


def research_preset(config, ids, *, water_l_per_m2_day, efficacy=2.5, photon_delivery=.8, overhead_kwh_per_m2_day=.15, conservative=False):
    references = load_reference_crops()
    if not ids or any(key not in references for key in ids):
        raise ValueError("Select at least one supported measured batch-harvest reference.")
    crops = []
    provenance = dict(config.input_provenance)
    for key in ids:
        reference = references[key]
        composition = composition_for_species(key)
        if composition is None:
            raise ValueError(f"No food-composition mapping for {reference.crop_species}.")
        if any(value is None for value in composition.nutrients_per_kg.values()):
            raise ValueError("Missing nutrient composition cannot be silently replaced with zero.")
        endpoint = reference.observed_min_kg_per_m2 if conservative else reference.yield_kg_per_m2
        led = estimate_led_energy(reference.ppfd_umol_m2_s, reference.equivalent_full_light_hours,
            efficacy_umol_per_j=efficacy, photon_delivery_fraction=photon_delivery)
        crops.append(CropSpec(key, f"{reference.name} · terrestrial reference", reference.planning_grow_days,
            endpoint, float(water_l_per_m2_day), led + overhead_kwh_per_m2_day, dict(composition.nutrients_per_kg)))
        provenance[f"crop:{key}:harvest"] = f"{reference.source_url}; {reference.source_table}; {reference.cultivar}; {reference.environment_id}; observed {'minimum' if conservative else 'mean'} fresh edible harvest; cycle rounded up from {reference.grow_days} days."
        provenance[f"crop:{key}:resources"] = f"Net makeup water {water_l_per_m2_day} L/m²/day assumed, not measured. LED {led:.6g} kWh/m²/day derived with efficacy {efficacy} µmol/J, delivery {photon_delivery}; PPFD basis: {reference.ppfd_basis}. Nursery stages are not resolved; final lighting/area assumed across the whole cycle. Overhead {overhead_kwh_per_m2_day} kWh/m²/day assumed. No fitted stress response."
        provenance[f"crop:{key}:composition"] = f"{composition.source_url}; generic edible species proxy, not cultivar/spaceflight assay."
    provenance["inventory_and_targets"] = "Stored inventories, crew targets and habitat budgets remain user-supplied scenario inputs."
    candidate = replace(config, crops=crops, input_provenance=provenance)
    candidate.validate()
    return candidate


def input_status(config):
    if not config.input_provenance:
        return "Synthetic demonstration food, crop and crew coefficients; not validated mission or clinical data."
    return "Mixed research and assumed inputs. Terrestrial harvest measurements and USDA references are identified by input; inventories, reviewed targets and unmeasured resources remain scenario inputs."
