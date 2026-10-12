"""Fine-tuning split integrity without training or installing heavyweight tools."""
from hashlib import sha256
import random

import numpy as np
from PIL import Image
import pytest

from astra_bio.plant_training import group_and_split, image_fingerprints
from astra_bio.vision_evaluation import audit_manifest


def photos(count=20, label="Tomato_healthy", *, prefix="tomato", avoid=()):
    """Independent synthetic metadata, sufficiently separated in hash space."""
    generator = random.Random(prefix)
    used = list(avoid)
    rows = []
    for index in range(count):
        while True:
            value = generator.getrandbits(64)
            if all((value ^ previous).bit_count() > 8 for previous in used):
                used.append(value)
                break
        path = f"train/{prefix}/leaf-{index}.jpg"
        rows.append({"path": path, "label": label, "original_split": "train",
                     "sha256": sha256(path.encode()).hexdigest(), "phash": f"{value:016x}"})
    return rows


def test_official_test_wins_exact_duplicates_even_if_train_appears_first():
    rows = photos()
    copied = {**rows[0], "path": "test/tomato/official.jpg", "original_split": "test"}
    result, report = group_and_split([*rows, copied])
    kept = next(row for row in result if row["sha256"] == copied["sha256"])
    assert kept["path"] == copied["path"] and kept["split"] == "test"
    assert rows[0]["path"] in report["duplicate_removals"]
    assert not any(row["path"] == rows[0]["path"] for row in result)
    assert audit_manifest(result, perceptual_distance=8)["valid"]


def test_near_duplicate_connected_component_keeps_test_out_of_both_fitting_splits():
    rows = photos(20, avoid=(0, 255, 65535))
    # A-B and B-C are within eight bits, while A-C are sixteen bits apart.
    copies = [{"path": f"{split}/chain/{name}.jpg", "label": "Tomato_healthy",
               "original_split": split, "sha256": sha256(name.encode()).hexdigest(),
               "phash": f"{value:016x}"}
              for split, name, value in (("train", "a", 0), ("train", "b", 255), ("test", "c", 65535))]
    result, report = group_and_split([*rows, *copies])
    chain = [row for row in result if "/chain/" in row["path"]]
    assert len(chain) == 1
    assert chain[0]["path"] == "test/chain/c.jpg" and chain[0]["split"] == "test"
    assert {"train/chain/a.jpg", "train/chain/b.jpg"} <= set(report["duplicate_removals"])
    assert audit_manifest(result, perceptual_distance=8)["valid"]


def test_conflicting_label_group_is_quarantined_including_official_test():
    rows = photos()
    original = {**rows[0]}
    conflicting = {**rows[0], "path": "test/conflicting.jpg", "label": "Tomato_Late_blight", "original_split": "test"}
    result, report = group_and_split([*rows, conflicting])
    assert set(report["conflicting_label_quarantine"]) == {original["path"], conflicting["path"]}
    assert all(row["sha256"] != original["sha256"] for row in result)
    assert len(result) == 19


def test_class_stratification_is_seeded_order_independent_and_does_not_mutate_inputs():
    tomato = photos(20)
    potato = photos(15, "Potato___healthy", prefix="potato", avoid=[int(row["phash"], 16) for row in tomato])
    source = [*tomato, *potato]
    original = [dict(row) for row in source]
    expected, _ = group_and_split(source, seed=42)
    shuffled = list(source)
    random.Random(991).shuffle(shuffled)
    actual, _ = group_and_split(shuffled, seed=42)
    assert actual == expected
    assert source == original
    assert sum(row["split"] == "validation" and row["label"] == "Tomato_healthy" for row in actual) == 4
    assert sum(row["split"] == "validation" and row["label"] == "Potato___healthy" for row in actual) == 3
    assert sum(row["split"] == "train" for row in actual) == 28
    train_groups = {row["group_id"] for row in actual if row["split"] == "train"}
    validation_groups = {row["group_id"] for row in actual if row["split"] == "validation"}
    assert not train_groups & validation_groups
    assert audit_manifest(actual, perceptual_distance=8)["valid"]


def test_too_few_distinct_groups_cannot_be_hidden_by_repeated_images():
    rows = photos(14)
    duplicate = {**rows[0], "path": "train/another-copy.jpg"}
    with pytest.raises(ValueError, match="Too few independent image groups.*14"):
        group_and_split([*rows, duplicate])
    result, _ = group_and_split(photos(15))
    assert sum(row["split"] == "train" for row in result) == 12
    assert sum(row["split"] == "validation" for row in result) == 3


def test_decoded_exact_hash_detects_same_pixels_despite_different_file_encoding(tmp_path):
    pixels = np.zeros((96, 96, 3), dtype=np.uint8)
    pixels[:, :48] = [32, 129, 61]
    pixels[48:] = [160, 90, 45]
    image = Image.fromarray(pixels)
    png, bmp = tmp_path / "leaf.png", tmp_path / "leaf.bmp"
    image.save(png)
    image.save(bmp)
    assert sha256(png.read_bytes()).digest() != sha256(bmp.read_bytes()).digest()
    assert image_fingerprints(png) == image_fingerprints(bmp)
    exact, perceptual = image_fingerprints(png)
    assert len(exact) == 64 and len(perceptual) == 16


def test_fingerprints_reject_small_or_undecodable_images(tmp_path):
    small, invalid = tmp_path / "small.png", tmp_path / "broken.jpg"
    Image.new("RGB", (32, 128), "green").save(small)
    invalid.write_bytes(b"not image data")
    with pytest.raises(ValueError, match="geometry"):
        image_fingerprints(small)
    with pytest.raises(OSError):
        image_fingerprints(invalid)
