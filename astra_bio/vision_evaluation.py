"""Reproducible, local evaluation for plant-screening logits and dataset splits.

These utilities do not train a model, download data or claim field validation.
Unknown/out-of-distribution examples use target ``-1`` and are reported apart
from closed-set accuracy. Temperature fitting is restricted to validation data;
test and external-test logits must only be evaluated with a frozen temperature.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import math
from pathlib import Path
import posixpath
import re
from typing import Iterable, Mapping, Sequence

import numpy as np


def _validated_logits(logits, temperature: float = 1.0) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 2 or not np.isfinite(values).all():
        raise ValueError("Logits must be a finite N-by-C array with at least two classes.")
    if not math.isfinite(float(temperature)) or float(temperature) <= 0:
        raise ValueError("Temperature must be a finite positive scalar.")
    with np.errstate(over="ignore", invalid="ignore"):
        scaled = values / float(temperature)
    if not np.isfinite(scaled).all():
        raise ValueError("Logits exceed the finite range at this temperature.")
    return scaled


def _validated_targets(targets, n_samples: int, n_classes: int) -> np.ndarray:
    raw = np.asarray(targets)
    if raw.ndim != 1 or len(raw) != n_samples:
        raise ValueError("Targets must contain one integer class index per image.")
    try:
        numeric = raw.astype(np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Targets must be class indices; use -1 for unknown/OOD images.") from exc
    if (not np.isfinite(numeric).all() or np.any(numeric != np.floor(numeric))
            or np.any(numeric < -1) or np.any(numeric >= n_classes)):
        raise ValueError("Targets must be in 0..C-1, or -1 for unknown/OOD images.")
    return numeric.astype(np.int64)


def softmax_probabilities(logits, *, temperature: float = 1.0) -> np.ndarray:
    """Stable global softmax; never renormalize within the selected crop species."""
    values = _validated_logits(logits, temperature)
    if not len(values):
        return np.empty_like(values)
    with np.errstate(over="ignore", invalid="ignore"):
        shifted = values - values.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _nll(logits: np.ndarray, targets: np.ndarray, temperature: float) -> float:
    values = _validated_logits(logits, temperature)
    with np.errstate(over="ignore", invalid="ignore"):
        shifted = values - values.max(axis=1, keepdims=True)
    losses = np.log(np.exp(shifted).sum(axis=1)) - shifted[np.arange(len(targets)), targets]
    result = float(np.mean(losses))
    if not math.isfinite(result):
        raise ValueError("Logits exceed the finite range for negative log likelihood.")
    return result


def fit_temperature(logits, targets, *, split_name: str = "validation",
                    bounds: tuple[float, float] = (0.05, 20.0)) -> dict:
    """Fit one scalar on validation NLL only, using a deterministic bounded search.

    Unknown examples are excluded and counted. Reusing validation for checkpoint
    selection and calibration is permissible but must be disclosed; neither is
    independent final evaluation. Caller-supplied split names cannot establish
    provenance, so the manifest audit remains mandatory.
    """
    if str(split_name).strip().lower() != "validation":
        raise ValueError("Temperature may be fitted only on the validation split, never on test data.")
    values = _validated_logits(logits)
    labels = _validated_targets(targets, len(values), values.shape[1])
    low, high = (float(value) for value in bounds)
    if not all(math.isfinite(value) and value > 0 for value in (low, high)) or low >= high:
        raise ValueError("Temperature bounds must be finite, positive and increasing.")
    known = labels >= 0
    if not known.any():
        raise ValueError("Temperature fitting requires at least one known validation label.")
    fitting_logits, fitting_targets = values[known], labels[known]
    objective = lambda log_t: _nll(fitting_logits, fitting_targets, math.exp(float(log_t)))
    grid = np.linspace(math.log(low), math.log(high), 65)
    losses = np.array([objective(log_t) for log_t in grid])
    best = int(losses.argmin())
    left, right = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    ratio = (math.sqrt(5) - 1) / 2
    x_left, x_right = right - ratio * (right - left), left + ratio * (right - left)
    f_left, f_right = objective(x_left), objective(x_right)
    for _ in range(72):
        if f_left <= f_right:
            right, x_right, f_right = x_right, x_left, f_left
            x_left = right - ratio * (right - left)
            f_left = objective(x_left)
        else:
            left, x_left, f_left = x_left, x_right, f_right
            x_right = left + ratio * (right - left)
            f_right = objective(x_right)
    candidates = [(float(grid[best]), float(losses[best])),
                  (float(x_left), float(f_left)), (float(x_right), float(f_right))]
    # Include T=1 when feasible so calibration cannot worsen validation NLL.
    if low <= 1 <= high:
        candidates.append((0.0, objective(0.0)))
    selected_log_t, after = min(candidates, key=lambda item: item[1])
    return {"temperature": float(math.exp(selected_log_t)), "fit_split": "validation",
            "known_samples": int(known.sum()), "excluded_unknown_samples": int((~known).sum()),
            "before_nll": _nll(fitting_logits, fitting_targets, 1.0), "after_nll": after,
            "bounds": [low, high], "objective": "validation negative log likelihood",
            "independent_evaluation": False}


def _label_species(label: str) -> str | None:
    if label.startswith("Tomato"):
        return "tomato"
    if label.startswith("Potato"):
        return "potato"
    if label.startswith("Pepper"):
        return "bell pepper"
    return None


def _abstention_metrics(logits: np.ndarray, targets: np.ndarray, class_names: Sequence[str],
                        temperature: float, crop_species) -> dict:
    """Apply deployed .70/.15/.50 rules; no threshold is optimized on the test set."""
    from .plant_vision import classify_logits

    probabilities = softmax_probabilities(logits, temperature=temperature)
    inferred_species = crop_species is None
    model_species = [_label_species(label) for label in class_names]
    species_aware = len(class_names) == 15 and all(model_species)
    if crop_species is None:
        species = [model_species[target] if target >= 0 else None for target in targets]
    elif isinstance(crop_species, str):
        species = [crop_species] * len(targets)
    else:
        species = list(crop_species)
        if len(species) != len(targets):
            raise ValueError("Crop species must have one entry per image, or one species string.")
    statuses, predicted = [], probabilities.argmax(axis=1) if len(logits) else np.array([], dtype=int)
    for index, row in enumerate(logits):
        if species_aware:
            selected_species = species[index]
            if not isinstance(selected_species, str) or not selected_species.strip():
                statuses.append("rejected")
                continue
            result = classify_logits(row / temperature, list(class_names), selected_species)
            statuses.append(result["status"])
        else:
            if crop_species is not None:
                raise ValueError("Species-aware abstention requires the deployed 15-class mapping.")
            ranking = np.sort(probabilities[index])
            statuses.append("tentative" if ranking[-1] >= .7 and ranking[-1] - ranking[-2] >= .15 else "uncertain")
    known = targets >= 0
    accepted = np.array([status == "tentative" for status in statuses], dtype=bool)
    accepted_known = accepted & known
    accepted_unknown = accepted & ~known
    counts = Counter(statuses)
    known_count, unknown_count = int(known.sum()), int((~known).sum())
    correct_accepted = int(np.sum(predicted[accepted_known] == targets[accepted_known]))
    return {"coverage": float(accepted_known.sum() / known_count) if known_count else None,
            "overall_coverage": float(accepted.mean()) if len(accepted) else None,
            "selective_accuracy": correct_accepted / int(accepted_known.sum()) if accepted_known.any() else None,
            "accepted_count": int(accepted.sum()), "accepted_known_count": int(accepted_known.sum()),
            "rejected_count": int(counts["rejected"]), "uncertain_count": int(counts["uncertain"]),
            "unknown_accepted_count": int(accepted_unknown.sum()),
            "unknown_false_acceptance_rate": int(accepted_unknown.sum()) / unknown_count if unknown_count else None,
            "statuses": statuses, "minimum_score": .7, "minimum_margin": .15,
            "minimum_species_mass": .5 if species_aware else None,
            "species_aware": species_aware,
            "species_source": "inferred from known target label; unknown species withheld" if inferred_species and species_aware
                else "caller supplied crop identity" if crop_species is not None else "generic global confidence rules",
            "threshold_validation": "Fixed screening rules; not tuned or agronomically validated on this evaluation."}


def evaluate_logits(logits, targets, class_names: Sequence[str], *, temperature: float = 1.0,
                    crop_species=None, n_bins: int = 15, split_name: str = "test") -> dict:
    """JSON-safe closed-set, calibration and separate abstention/OOD measurements.

    ``macro_f1`` and balanced accuracy average classes represented by true labels;
    absent supported classes have null per-class recall/F1 and explicit support 0.
    ``macro_f1_all_classes`` additionally reports the zero-filled full-head mean.
    Brier is the mean sum of squared error across all C classes (range 0..2).
    ECE uses equal-width confidence bins and the top global class, without fitting.
    """
    values = _validated_logits(logits)
    names = list(class_names)
    if (len(names) != values.shape[1] or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Class names must be unique, nonempty and match every output column.")
    if not isinstance(n_bins, int) or isinstance(n_bins, bool) or n_bins < 1:
        raise ValueError("Calibration bin count must be a positive integer.")
    targets = _validated_targets(targets, len(values), len(names))
    probabilities = softmax_probabilities(values, temperature=temperature)
    known = targets >= 0
    known_targets, known_probabilities = targets[known], probabilities[known]
    predictions = known_probabilities.argmax(axis=1) if known.any() else np.array([], dtype=int)
    matrix = np.zeros((len(names), len(names)), dtype=np.int64)
    np.add.at(matrix, (known_targets, predictions), 1)
    support, predicted_count, true_positive = matrix.sum(axis=1), matrix.sum(axis=0), matrix.diagonal()
    precision = np.divide(true_positive, predicted_count, out=np.zeros(len(names), dtype=float), where=predicted_count > 0)
    recall = np.divide(true_positive, support, out=np.zeros(len(names), dtype=float), where=support > 0)
    f1 = np.divide(2 * true_positive, support + predicted_count, out=np.zeros(len(names), dtype=float), where=(support + predicted_count) > 0)
    represented = support > 0
    correct = predictions == known_targets
    calibration_bins = []
    ece = 0.0
    confidence = known_probabilities.max(axis=1) if known.any() else np.array([])
    # min(n_bins-1, ...) places confidence==1 in the last bin.
    assignments = np.minimum((confidence * n_bins).astype(int), n_bins - 1)
    for index in range(n_bins):
        mask = assignments == index
        count = int(mask.sum())
        bin_accuracy = float(correct[mask].mean()) if count else None
        bin_confidence = float(confidence[mask].mean()) if count else None
        if count:
            ece += count / int(known.sum()) * abs(bin_accuracy - bin_confidence)
        calibration_bins.append({"lower": index / n_bins, "upper": (index + 1) / n_bins,
                                 "count": count, "accuracy": bin_accuracy, "mean_confidence": bin_confidence})
    one_hot = np.zeros_like(known_probabilities)
    one_hot[np.arange(len(known_targets)), known_targets] = 1
    result = {"split": str(split_name), "temperature": float(temperature), "samples": len(values),
              "known_samples": int(known.sum()), "unknown_samples": int((~known).sum()),
              "accuracy": float(correct.mean()) if known.any() else None,
              "balanced_accuracy": float(recall[represented].mean()) if represented.any() else None,
              "macro_f1": float(f1[represented].mean()) if represented.any() else None,
              "macro_f1_all_classes": float(f1.mean()) if known.any() else None,
              "class_coverage": {"represented_classes": int(represented.sum()), "total_classes": len(names),
                                 "represented_labels": [names[i] for i in np.flatnonzero(represented)],
                                 "unrepresented_labels": [names[i] for i in np.flatnonzero(~represented)]},
              "per_class": [{"label": name, "support": int(support[i]), "predicted_count": int(predicted_count[i]),
                             "precision": float(precision[i]) if predicted_count[i] else None,
                             "recall": float(recall[i]) if support[i] else None,
                             "f1": float(f1[i]) if support[i] else None} for i, name in enumerate(names)],
              "confusion_matrix": matrix.tolist(), "confusion_matrix_order": names,
              "negative_log_likelihood": _nll(values[known], targets[known], temperature) if known.any() else None,
              "brier_score": float(np.square(known_probabilities - one_hot).sum(axis=1).mean()) if known.any() else None,
              "expected_calibration_error": float(ece) if known.any() else None,
              "calibration_bins": calibration_bins,
              "metric_scope": "Closed-set metrics exclude target -1; macro_f1/balanced_accuracy cover true-supported classes only.",
              "abstention": _abstention_metrics(values, targets, names, temperature, crop_species),
              "interpretation": "Dataset measurements only; field, tray, spaceflight and clinical validation are separate."}
    return result


def read_manifest_csv(path: str | Path) -> list[dict[str, str]]:
    """Read a local manifest; paths are not opened and no network access occurs."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_manifest(records: Iterable[Mapping], *,
                   allowed_splits: Sequence[str] = ("train", "validation", "test", "external_test"),
                   perceptual_distance: int = 0, max_issues: int = 100) -> dict:
    """Audit declared paths, exact hashes, capture groups and near duplicates.

    Required fields: path, label, split, group_id, sha256. Optional ``phash`` is
    hexadecimal, from the same declared algorithm for all images. Different
    bit widths/algorithms are rejected. Any cross-split group/hash/near-hash
    collision is an error. Perceptual similarity is a conservative leakage flag,
    not proof of visual identity, and should be reviewed before splitting groups.
    This validates supplied metadata, not upstream pretraining membership.
    """
    rows = [dict(row) for row in records]
    splits = tuple(allowed_splits)
    if not splits or len(set(splits)) != len(splits):
        raise ValueError("Allowed split names must be unique and nonempty.")
    if not isinstance(perceptual_distance, int) or isinstance(perceptual_distance, bool) or perceptual_distance < 0:
        raise ValueError("Perceptual hash distance must be a nonnegative integer.")
    if not isinstance(max_issues, int) or max_issues < 1:
        raise ValueError("max_issues must be a positive integer.")
    errors, warnings = [], []
    issue_count = 0
    def error(code: str, message: str, indices: Sequence[int] = ()):
        nonlocal issue_count
        issue_count += 1
        if len(errors) < max_issues:
            errors.append({"code": code, "message": message, "rows": list(indices)})
    if not rows:
        error("empty_manifest", "No dataset samples were supplied.")
    by_path, by_sha, by_group = defaultdict(list), defaultdict(list), defaultdict(list)
    hash_values, algorithms = [], set()
    split_counts, label_counts = Counter(), defaultdict(Counter)
    for index, row in enumerate(rows):
        missing = [key for key in ("path", "label", "split", "group_id", "sha256")
                   if row.get(key) is None or not str(row.get(key, "")).strip()]
        if missing:
            error("missing_fields", f"Row {index} is missing {', '.join(missing)}.", [index])
        split = str(row.get("split", "")).strip()
        if split not in splits:
            error("unknown_split", f"Row {index} uses an unrecognized split: {split!r}.", [index])
        split_counts[split] += 1
        label_counts[split][str(row.get("label", ""))] += 1
        raw_path = str(row.get("path", "")).strip().replace("\\", "/").casefold()
        path = posixpath.normpath(raw_path) if raw_path else ""
        if path:
            by_path[path].append(index)
        digest = str(row.get("sha256", "")).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            error("invalid_sha256", f"Row {index} has an invalid SHA256 hash.", [index])
        else:
            by_sha[digest].append(index)
        group = str(row.get("group_id", "")).strip()
        if group:
            by_group[group].append(index)
        phash = str(row.get("phash", "")).strip().lower()
        if phash:
            if not re.fullmatch(r"[0-9a-f]+", phash):
                error("invalid_phash", f"Row {index} has an invalid hexadecimal perceptual hash.", [index])
            else:
                hash_values.append((index, int(phash, 16), len(phash) * 4))
                if row.get("phash_algorithm"):
                    algorithms.add(str(row["phash_algorithm"]).strip().lower())
    for code, buckets in (("path", by_path), ("exact_hash", by_sha), ("capture_group", by_group)):
        for indices in buckets.values():
            if len(indices) < 2:
                continue
            if code == "path":
                error("duplicate_path", "A dataset image path occurs more than once.", indices)
            if len({str(rows[index].get("split", "")).strip() for index in indices}) > 1:
                error(f"cross_split_{code}", f"Images share a {code.replace('_', ' ')} across dataset splits.", indices)
            if code in {"path", "exact_hash"} and len({str(rows[index].get("label", "")) for index in indices}) > 1:
                error("conflicting_duplicate_labels", f"The same image has conflicting labels ({code}).", indices)
    widths = {entry[2] for entry in hash_values}
    if len(widths) > 1 or len(algorithms) > 1:
        error("incompatible_phash", "Perceptual hashes use incompatible widths or algorithms.")
    if widths and perceptual_distance > next(iter(widths)):
        raise ValueError("Perceptual distance cannot exceed hash bit width.")
    if hash_values and not algorithms:
        warnings.append("Perceptual hash algorithm was not declared; comparisons assume one consistent algorithm.")
    near_pairs, cross_split_near_pairs = 0, 0
    if len(widths) <= 1 and len(algorithms) <= 1:
        for position, (index, value, _) in enumerate(hash_values):
            for other_index, other_value, _ in hash_values[:position]:
                distance = (value ^ other_value).bit_count()
                if distance > perceptual_distance:
                    continue
                near_pairs += 1
                if str(rows[index].get("split", "")).strip() != str(rows[other_index].get("split", "")).strip():
                    cross_split_near_pairs += 1
                    error("cross_split_perceptual_hash", f"Near-duplicate images span splits (hash distance {distance}).", [other_index, index])
    return {"valid": issue_count == 0, "samples": len(rows), "errors": errors,
            "error_count": issue_count, "errors_truncated": issue_count > len(errors), "warnings": warnings,
            "split_counts": dict(split_counts), "label_counts": {split: dict(counts) for split, counts in label_counts.items()},
            "capture_groups": len(by_group), "unique_exact_hashes": len(by_sha),
            "perceptual_hashes": len(hash_values), "perceptual_distance": perceptual_distance,
            "near_duplicate_pairs": near_pairs, "cross_split_near_duplicate_pairs": cross_split_near_pairs,
            "pretraining_overlap_checked": False,
            "limitation": "Manifest integrity does not establish independence from pretrained upstream data."}
