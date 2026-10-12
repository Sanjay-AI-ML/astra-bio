"""Measured terrestrial harvest references with deliberately limited predictions.

The references calibrate a batch-harvest endpoint, not a mechanistic growth curve
or response to water, power, temperature, CO2, microgravity or nutrient stress.
No downloaded document can execute instructions through this module.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from math import ceil, isfinite, sqrt
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "research" / "crops"


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number.") from error
    if not isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}.")
    return number


def _optional_number(value: str) -> float | None:
    return None if not value.strip() else _number(value, "Reference coefficient")


@dataclass(frozen=True)
class ReferenceCrop:
    id: str
    name: str
    crop_species: str
    cultivar: str
    environment_id: str
    grow_days: float
    yield_kg_per_m2: float
    reported_cycles: int
    yield_standard_error_kg_per_m2: float | None
    observed_min_kg_per_m2: float
    observed_max_kg_per_m2: float
    uncertainty_type: str
    grow_days_definition: str
    ppfd_umol_m2_s: float
    photoperiod_hours: float
    equivalent_full_light_hours: float
    day_temperature_c: float
    night_temperature_c: float
    relative_humidity_pct: float
    co2_ppm: float
    plants_per_m2: float | None
    cultivation_system: str
    light_source: str
    source_id: str
    source_url: str
    source_doi: str
    source_table: str
    ppfd_basis: str = "reported crop light setting"
    environment_notes: str = ""
    gross_applied_irrigation_l_per_m2_cycle: float | None = None
    net_makeup_water_l_per_m2_day: float | None = None
    whole_system_kwh_per_m2_day: float | None = None
    evidence_setting: str = "terrestrial controlled environment; not spaceflight validation"
    ppfd_basis: str = "reported canopy setting"
    environment_notes: str = ""

    @property
    def planning_grow_days(self) -> int:
        """Round the measured mean cycle upward for a daily planning grid."""
        return ceil(self.grow_days)

    @property
    def observed_yield_range(self) -> tuple[float, float]:
        return self.observed_min_kg_per_m2, self.observed_max_kg_per_m2

    def as_dict(self) -> dict:
        return {**asdict(self), "planning_grow_days": self.planning_grow_days}

    to_dict = as_dict


def load_reference_crops(path: str | Path | None = None) -> dict[str, ReferenceCrop]:
    """Load cultivar/environment-specific measured batch-harvest summaries."""
    references: dict[str, ReferenceCrop] = {}
    with Path(path or DATA_DIR / "reference_crops.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            values = dict(row)
            for key in (
                "grow_days", "yield_kg_per_m2", "observed_min_kg_per_m2", "observed_max_kg_per_m2",
                "ppfd_umol_m2_s", "photoperiod_hours", "equivalent_full_light_hours",
                "day_temperature_c", "night_temperature_c", "relative_humidity_pct", "co2_ppm",
            ):
                values[key] = _number(row[key], key)
            for key in ("plants_per_m2", "yield_standard_error_kg_per_m2", "gross_applied_irrigation_l_per_m2_cycle",
                        "net_makeup_water_l_per_m2_day", "whole_system_kwh_per_m2_day"):
                values[key] = _optional_number(row.get(key, ""))
            values["reported_cycles"] = int(row["reported_cycles"])
            crop = ReferenceCrop(**values)
            if not crop.id or crop.id in references:
                raise ValueError("Reference crop identifiers must be nonempty and unique.")
            if crop.grow_days <= 0 or crop.reported_cycles <= 0:
                raise ValueError("Reference cycle length/count must be positive.")
            if not crop.observed_min_kg_per_m2 <= crop.yield_kg_per_m2 <= crop.observed_max_kg_per_m2:
                raise ValueError("Reference mean must fall inside its observed range.")
            references[crop.id] = crop
    return references


def estimate_led_energy(
    ppfd_umol_m2_s: float, equivalent_full_light_hours: float,
    *, efficacy_umol_per_j: float = 2.5, photon_delivery_fraction: float = 1.0,
) -> float:
    """Engineering estimate of LED kWh/m²/day; excludes HVAC, pumps and controls.

    PPFD / (fixture efficacy * photon-delivery fraction) gives electrical W/m².
    Efficacy and delivery are explicit assumptions, not measured EDEN hardware
    efficiencies. For NASA's fluorescent reference this models replacement LEDs.
    """
    ppfd = _number(ppfd_umol_m2_s, "PPFD")
    hours = _number(equivalent_full_light_hours, "Equivalent light hours")
    efficacy = _number(efficacy_umol_per_j, "LED photon efficacy", positive=True)
    delivery = _number(photon_delivery_fraction, "Photon delivery fraction", positive=True)
    if hours > 24 or delivery > 1:
        raise ValueError("Light hours must be at most 24 and photon delivery fraction at most one.")
    return ppfd * hours / (efficacy * delivery * 1000.0)


@dataclass(frozen=True)
class GrowthPrediction:
    crop_id: str
    age_days: float
    area_m2: float
    reference_grow_days: float
    planning_grow_days: int
    reference_yield_kg_per_m2: float
    expected_harvest_kg: float
    observed_harvest_range_kg: tuple[float, float]
    harvest_ready: bool
    available_harvest_kg: float
    illustrative_biomass_kg: float | None
    maturity_fraction: float
    estimated_led_kwh_per_m2_day: float
    estimated_led_kwh_for_reference_cycle: float
    net_makeup_water_l: None
    whole_system_energy_kwh: None
    curve_basis: str
    stress_basis: str
    source_url: str
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)

    to_dict = as_dict


def predict_growth(
    crop_id: str, age_days: float, area_m2: float,
    water_factor: float = 1.0, power_factor: float = 1.0,
    *, conservative: bool = False, curve: str = "endpoint_only",
    assume_linear_resource_stress: bool = False, efficacy_umol_per_j: float = 2.5,
    photon_delivery_fraction: float = 1.0,
    references: Mapping[str, ReferenceCrop] | None = None,
) -> GrowthPrediction:
    """Predict one reference batch, never repeated harvests or extrapolated yield.

    Default: a measured harvest endpoint and a daily scheduling readiness gate.
    ``linear_assumption`` optionally draws an unfitted illustrative biomass curve.
    Non-unit resource factors require explicit opt-in to a hypothetical linear
    reduction. Resource budgets should normally constrain planting in the planner.
    """
    crops = load_reference_crops() if references is None else references
    if crop_id not in crops:
        raise ValueError(f"No measured reference for crop identifier {crop_id!r}.")
    crop = crops[crop_id]
    age = _number(age_days, "Age in days")
    area = _number(area_m2, "Cultivation area")
    water = _number(water_factor, "Water factor")
    power = _number(power_factor, "Power factor")
    if water > 1 or power > 1:
        raise ValueError("Resource factors must be between zero and one; yield gains are not calibrated.")
    if (water != 1 or power != 1) and not assume_linear_resource_stress:
        raise ValueError("Resource-to-yield response is not fitted. Explicitly opt in to a hypothetical stress assumption.")
    if curve not in ("endpoint_only", "linear_assumption"):
        raise ValueError("Curve must be endpoint_only or linear_assumption.")
    stress_factor = min(water, power) if assume_linear_resource_stress else 1.0
    yield_value = crop.observed_min_kg_per_m2 if conservative else crop.yield_kg_per_m2
    endpoint = yield_value * area * stress_factor
    observed = tuple(value * area for value in crop.observed_yield_range)
    maturity = min(age / crop.grow_days, 1.0)
    ready = age >= crop.planning_grow_days
    warnings = [
        "Measured terrestrial harvest reference; performance in space or a new tray is unvalidated.",
        "Observed min/max describes those experiments, not a confidence or prediction interval.",
        "Net makeup water and whole-system electrical energy are not available for this reference.",
        "LED energy uses assumed fixture efficacy and photon delivery; it is not measured system energy.",
    ]
    if age > crop.grow_days:
        warnings.append("Past the reference mean harvest age, yield is held at one batch endpoint; further growth is unknown.")
    if curve == "linear_assumption":
        warnings.append("Intermediate biomass is a linear illustration, not fitted to measured growth observations.")
    if stress_factor != 1:
        warnings.append("Water/power yield reduction is hypothetical; the original observed range remains unscaled evidence.")
    led = estimate_led_energy(crop.ppfd_umol_m2_s, crop.equivalent_full_light_hours,
                              efficacy_umol_per_j=efficacy_umol_per_j,
                              photon_delivery_fraction=photon_delivery_fraction)
    return GrowthPrediction(
        crop_id, age, area, crop.grow_days, crop.planning_grow_days, crop.yield_kg_per_m2,
        endpoint, observed, ready, endpoint if ready else 0.0,
        endpoint * maturity if curve == "linear_assumption" else None,
        maturity, led, led * crop.grow_days * area, None, None,
        "measured endpoint only" if curve == "endpoint_only" else "unfitted linear illustration",
        "no fitted resource response" if stress_factor == 1 else "assumed min(water_factor, power_factor) linear loss",
        crop.source_url, tuple(warnings),
    )


def load_observations(path: str | Path | None = None) -> list[dict[str, str]]:
    """Load recorded crop-cycle measurements and labelled published summaries."""
    with Path(path or DATA_DIR / "harvest_observations.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def calibrate_harvests(
    observations: Iterable[Mapping[str, object]], *,
    holdout_ids: Iterable[str] = (),
) -> dict:
    """Fit a constant batch endpoint per crop/cultivar/environment, then score holdouts.

    Required columns: observation_id, crop_id, cultivar, environment_id,
    grow_days, area_m2, fresh_harvest_kg, observation_type, source_url.
    A published summary is one summary, not its reported N fabricated replicates.
    Holdouts must be distinct actual ``crop_cycle`` rows with a training cycle
    from that same profile. Re-publication or duplication cannot supply a holdout.
    """
    records = []
    seen: set[str] = set()
    groups: dict[str, tuple[str, str]] = {}
    selected = set(holdout_ids)
    for row in observations:
        identifier = str(row.get("observation_id", ""))
        crop_id = str(row.get("crop_id", ""))
        cultivar = str(row.get("cultivar", ""))
        environment = str(row.get("environment_id", ""))
        if not all((identifier, crop_id, cultivar, environment, row.get("source_url"))):
            raise ValueError("Every observation needs identity, cultivar, environment and source provenance.")
        if identifier in seen:
            raise ValueError("Duplicate observation identifiers would leak data into validation.")
        seen.add(identifier)
        group = cultivar, environment
        if crop_id in groups and groups[crop_id] != group:
            raise ValueError("Do not pool cultivars or growing environments under one crop profile.")
        groups[crop_id] = group
        kind = str(row.get("observation_type", ""))
        if kind not in ("crop_cycle", "published_summary"):
            raise ValueError("Observation type must distinguish crop_cycle from published_summary.")
        records.append({
            "observation_id": identifier, "crop_id": crop_id, "cultivar": cultivar,
            "environment_id": environment, "grow_days": _number(row.get("grow_days"), "Grow days", positive=True),
            "yield_kg_per_m2": _number(row.get("fresh_harvest_kg"), "Fresh edible harvest") /
                                _number(row.get("area_m2"), "Measured cultivation area", positive=True),
            "observation_type": kind, "source_url": str(row["source_url"]),
            "independent_group_id": str(row.get("independent_group_id") or identifier),
        })
    if not records or not selected <= seen:
        raise ValueError("Provide observations and valid explicit holdout identifiers.")
    fits = {}
    validation_rows = []
    for crop_id in sorted(groups):
        group_rows = [row for row in records if row["crop_id"] == crop_id]
        train = [row for row in group_rows if row["observation_id"] not in selected]
        holdouts = [row for row in group_rows if row["observation_id"] in selected]
        if not train:
            raise ValueError(f"Crop {crop_id} has no training observation.")
        endpoint = mean(row["yield_kg_per_m2"] for row in train)
        fits[crop_id] = {
            "crop_id": crop_id, "cultivar": groups[crop_id][0], "environment_id": groups[crop_id][1],
            "yield_kg_per_m2": endpoint, "grow_days": mean(row["grow_days"] for row in train),
            "training_record_count": len(train), "training_cycle_count": sum(row["observation_type"] == "crop_cycle" for row in train),
            "training_summary_count": sum(row["observation_type"] == "published_summary" for row in train),
            "training_observation_ids": [row["observation_id"] for row in train],
            "source_urls": sorted({row["source_url"] for row in train}),
        }
        for row in holdouts:
            if row["observation_type"] != "crop_cycle" or any(item["observation_type"] != "crop_cycle" for item in train):
                raise ValueError("Published summaries cannot provide independent held-out cycle validation.")
            if row["independent_group_id"] in {item["independent_group_id"] for item in train}:
                raise ValueError("Training and holdout observations share a cycle/group; validation would leak.")
            if any(abs(item["grow_days"] - row["grow_days"]) > 1e-9 for item in train):
                raise ValueError("Endpoint holdouts must have the same harvest age; age response is not fitted.")
            error = endpoint - row["yield_kg_per_m2"]
            validation_rows.append({
                "observation_id": row["observation_id"], "crop_id": crop_id,
                "observed_kg_per_m2": row["yield_kg_per_m2"], "predicted_kg_per_m2": endpoint,
                "error_kg_per_m2": error, "absolute_error_kg_per_m2": abs(error),
                "absolute_percentage_error": 100 * abs(error) / row["yield_kg_per_m2"] if row["yield_kg_per_m2"] else None,
                "source_url": row["source_url"],
            })
    validation = None
    if validation_rows:
        percentage = [row["absolute_percentage_error"] for row in validation_rows if row["absolute_percentage_error"] is not None]
        validation = {
            "kind": "explicit held-out crop-cycle endpoint diagnostic",
            "holdout_record_count": len(validation_rows),
            "mae_kg_per_m2": mean(row["absolute_error_kg_per_m2"] for row in validation_rows),
            "rmse_kg_per_m2": sqrt(mean(row["error_kg_per_m2"] ** 2 for row in validation_rows)),
            "mape_pct": mean(percentage) if percentage else None,
            "records": validation_rows,
            "limitation": "Small within-facility diagnostic; not general accuracy, independent-facility or spaceflight validation.",
        }
    return {
        "model": "constant fresh-edible batch-harvest endpoint per cultivar/environment",
        "fit_parameters": fits, "validation": validation,
        "fitted_growth_curve": False, "fitted_resource_stress": False,
        "summary_records_are_not_individual_cycles": True,
    }


# Explicit names for callers that describe the workflow as observation calibration.
calibrate_observations = calibrate_harvests
