"""Dataset metrics, validation-only calibration and leakage protections."""
import json

import numpy as np
import pytest

from astra_bio.vision_evaluation import (
    audit_manifest, evaluate_logits, fit_temperature, read_manifest_csv,
    softmax_probabilities,
)


LABELS = ["Pepper__bell___Bacterial_spot", "Pepper__bell___healthy", "Potato___Early_blight",
    "Potato___Late_blight", "Potato___healthy", "Tomato_Bacterial_spot", "Tomato_Early_blight",
    "Tomato_Late_blight", "Tomato_Leaf_Mold", "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites_Two_spotted_spider_mite", "Tomato__Target_Spot",
    "Tomato__Tomato_YellowLeaf__Curl_Virus", "Tomato__Tomato_mosaic_virus", "Tomato_healthy"]


def peaked(*indices):
    values = np.full((len(indices), len(LABELS)), -5.0)
    for row, index in enumerate(indices):
        values[row, index] = 5.0
    return values


def record(path, split, *, group=None, digest=None, label="Tomato_healthy", phash=None):
    result = {"path": path, "label": label, "split": split,
              "group_id": group or path, "sha256": digest or path.encode().hex().ljust(64, "0")[:64]}
    if phash is not None:
        result.update(phash=phash, phash_algorithm="phash-dct-64")
    return result


def test_global_softmax_is_stable_and_temperature_keeps_class_ranking():
    logits = np.array([[1000, 999, -1000], [0, -1, 1]])
    probabilities = softmax_probabilities(logits)
    assert probabilities.sum(axis=1) == pytest.approx([1, 1])
    assert probabilities[0, 0] == pytest.approx(1 / (1 + np.exp(-1)))
    assert np.isfinite(probabilities).all()
    softened = softmax_probabilities(logits, temperature=3)
    assert probabilities.argmax(axis=1).tolist() == softened.argmax(axis=1).tolist()
    assert softened.max(axis=1)[1] < probabilities.max(axis=1)[1]


def test_metrics_match_hand_computed_confusion_and_expose_missing_classes():
    logits = np.log([[.8, .1, .1], [.1, .8, .1], [.1, .8, .1]])
    result = evaluate_logits(logits, [0, 0, 1], ["a", "b", "unseen"])
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["balanced_accuracy"] == pytest.approx(.75)
    assert result["macro_f1"] == pytest.approx(2 / 3)
    assert result["macro_f1_all_classes"] == pytest.approx(4 / 9)
    assert result["confusion_matrix"] == [[1, 1, 0], [0, 1, 0], [0, 0, 0]]
    assert result["per_class"][0] == {"label": "a", "support": 2, "predicted_count": 1,
                                      "precision": 1.0, "recall": .5, "f1": 2 / 3}
    assert result["per_class"][2]["recall"] is None
    assert result["per_class"][2]["support"] == 0
    assert result["class_coverage"]["unrepresented_labels"] == ["unseen"]
    assert result["negative_log_likelihood"] == pytest.approx(-(2 * np.log(.8) + np.log(.1)) / 3)
    assert result["brier_score"] == pytest.approx((.06 + 1.46 + .06) / 3)
    assert result["expected_calibration_error"] == pytest.approx(.8 - 2 / 3)
    assert result["abstention"]["coverage"] == 1
    assert result["abstention"]["selective_accuracy"] == pytest.approx(2 / 3)
    json.dumps(result, allow_nan=False)


def test_temperature_fits_validation_only_and_never_receives_test_targets():
    logits = np.array([[8., -8.]] * 3 + [[-8., 8.]])
    fitted = fit_temperature(logits, [0, 0, 0, 0], split_name="validation")
    assert fitted["temperature"] > 1
    assert fitted["after_nll"] < fitted["before_nll"]
    assert .05 <= fitted["temperature"] <= 20
    assert fitted["fit_split"] == "validation"
    assert fitted["independent_evaluation"] is False
    # Applying frozen validation T to test changes probabilities, not fitting.
    result = evaluate_logits([[2., -2.]], [0], ["a", "b"], temperature=fitted["temperature"], split_name="external_test")
    assert result["split"] == "external_test"
    assert result["temperature"] == fitted["temperature"]
    for split in ("train", "test", "external_test", "holdout", ""):
        with pytest.raises(ValueError, match="validation"):
            fit_temperature(logits, [0, 0, 0, 0], split_name=split)


def test_unknown_images_are_separate_and_ood_acceptance_is_not_counted_as_accuracy():
    result = evaluate_logits(peaked(14, 14, 14), [14, 4, -1], LABELS,
                             crop_species=["tomato", "potato", "tomato"])
    assert result["known_samples"] == 2 and result["unknown_samples"] == 1
    assert result["accuracy"] == .5
    assert sum(map(sum, result["confusion_matrix"])) == 2
    abstention = result["abstention"]
    assert abstention["statuses"] == ["tentative", "rejected", "tentative"]
    assert abstention["coverage"] == .5
    assert abstention["selective_accuracy"] == 1
    assert abstention["unknown_accepted_count"] == 1
    assert abstention["unknown_false_acceptance_rate"] == 1
    assert abstention["overall_coverage"] == pytest.approx(2 / 3)
    assert abstention["minimum_species_mass"] == .5


def test_ambiguous_predictions_are_uncertain_and_unidentified_crop_is_withheld():
    logits = peaked(14, 14, 14)
    logits[1, 7] = 4.99
    result = evaluate_logits(logits, [14, 14, -1], LABELS)
    assert result["abstention"]["statuses"] == ["tentative", "uncertain", "rejected"]
    assert result["abstention"]["coverage"] == .5
    assert result["abstention"]["unknown_false_acceptance_rate"] == 0
    unsupported = evaluate_logits(peaked(14), [-1], LABELS, crop_species="lettuce")
    assert unsupported["abstention"]["rejected_count"] == 1
    assert unsupported["accuracy"] is None
    assert unsupported["negative_log_likelihood"] is None
    json.dumps(unsupported, allow_nan=False)


def test_empty_eval_reports_unavailable_metrics_without_inventing_accuracy():
    result = evaluate_logits(np.empty((0, 15)), [], LABELS)
    assert result["samples"] == 0
    assert result["accuracy"] is None and result["macro_f1"] is None
    assert result["abstention"]["coverage"] is None
    assert result["abstention"]["selective_accuracy"] is None
    assert result["class_coverage"]["represented_classes"] == 0
    with pytest.raises(ValueError, match="known validation"):
        fit_temperature(peaked(14), [-1])


@pytest.mark.parametrize("logits,targets,names", [
    ([[np.nan, 0]], [0], ["a", "b"]),
    ([[0, 0]], [2], ["a", "b"]),
    ([[0, 0]], [-2], ["a", "b"]),
    ([[0, 0]], [.5], ["a", "b"]),
    ([[0, 0]], [], ["a", "b"]),
    ([[0, 0]], [0], ["a", "a"]),
    ([[0, 0]], [0], ["a"]),
])
def test_bad_outputs_and_mapping_are_rejected(logits, targets, names):
    with pytest.raises(ValueError):
        evaluate_logits(logits, targets, names)


def test_calibration_configuration_and_species_list_are_validated():
    for temperature in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            softmax_probabilities([[0, 1]], temperature=temperature)
    with pytest.raises(ValueError, match="bin"):
        evaluate_logits([[0, 1]], [0], ["a", "b"], n_bins=0)
    with pytest.raises(ValueError, match="one entry"):
        evaluate_logits(peaked(14), [14], LABELS, crop_species=[])
    with pytest.raises(ValueError, match="15-class"):
        evaluate_logits([[0, 1]], [0], ["a", "b"], crop_species="tomato")
    with pytest.raises(ValueError, match="bounds"):
        fit_temperature([[0, 1]], [0], bounds=(1, 1))


def test_manifest_catches_exact_duplicate_and_capture_group_leakage():
    common_digest = "a" * 64
    rows = [record("a.jpg", "train", digest=common_digest),
            record("b.jpg", "test", digest=common_digest),
            record("c.jpg", "validation", group="same-leaf"),
            record("d.jpg", "external_test", group="same-leaf")]
    result = audit_manifest(rows)
    codes = {error["code"] for error in result["errors"]}
    assert not result["valid"]
    assert "cross_split_exact_hash" in codes
    assert "cross_split_capture_group" in codes
    assert result["pretraining_overlap_checked"] is False


def test_manifest_near_duplicate_threshold_and_label_conflicts():
    rows = [record("a.jpg", "train", phash="0000000000000000"),
            record("b.jpg", "test", phash="00000000000000ff")]
    assert audit_manifest(rows, perceptual_distance=7)["valid"]
    result = audit_manifest(rows, perceptual_distance=8)
    assert not result["valid"]
    assert result["cross_split_near_duplicate_pairs"] == 1
    assert result["errors"][0]["code"] == "cross_split_perceptual_hash"
    rows = [record("a.jpg", "train", digest="b" * 64),
            record("b.jpg", "train", digest="b" * 64, label="Tomato_Late_blight")]
    assert "conflicting_duplicate_labels" in {error["code"] for error in audit_manifest(rows)["errors"]}


def test_manifest_rejects_missing_provenance_and_incompatible_hashes():
    rows = [record("a.jpg", "train", phash="ffff"), record("b.jpg", "test", phash="ffffffff")]
    assert "incompatible_phash" in {error["code"] for error in audit_manifest(rows)["errors"]}
    rows = [{"path": "a.jpg", "label": "healthy", "split": "validation", "sha256": "invalid"}]
    codes = {error["code"] for error in audit_manifest(rows)["errors"]}
    assert {"missing_fields", "invalid_sha256"} <= codes
    result = audit_manifest([record("a.jpg", "mystery")], max_issues=1)
    assert not result["valid"]
    assert result["errors"][0]["code"] == "unknown_split"
    assert not audit_manifest([])["valid"]


def test_manifest_normalizes_paths_and_rejects_null_capture_identity():
    rows = [record("IMAGES\\leaf.jpg", "train"), record("images/./leaf.jpg", "train")]
    codes = {error["code"] for error in audit_manifest(rows)["errors"]}
    assert "duplicate_path" in codes
    rows = [record("a.jpg", "train")]
    rows[0]["group_id"] = None
    assert "missing_fields" in {error["code"] for error in audit_manifest(rows)["errors"]}


def test_valid_csv_manifest_is_local_and_never_opens_its_image_paths(tmp_path):
    path = tmp_path / "manifest.csv"
    path.write_text("path,label,split,group_id,sha256\nnot-present.jpg,Tomato_healthy,train,leaf-a," + "a" * 64 + "\n", encoding="utf-8")
    rows = read_manifest_csv(path)
    result = audit_manifest(rows)
    assert result["valid"]
    assert result["split_counts"] == {"train": 1}
    assert result["label_counts"] == {"train": {"Tomato_healthy": 1}}
