"""Explicitly acquire and normalize the attributed UC Davis lettuce dataset.

Only the small tabular/README members are required. HTTP byte ranges avoid
downloading 743 MB of canopy photographs. ZIP member CRCs and local SHA256s
are checked; the publisher's whole-archive MD5 is retained but is NOT claimed
verified unless the entire archive has been downloaded separately.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "data/research/growth"
RECORD_ID = "17041810"
RECORD_URL = f"https://zenodo.org/records/{RECORD_ID}"
METADATA_URL = f"https://zenodo.org/api/records/{RECORD_ID}"
ARCHIVE_URL = f"{METADATA_URL}/files/Lettuce_growth.zip/content"
ARCHIVE_BYTES = 742925862
ARCHIVE_MD5 = "c8c60806f714dc065592b14eae570d16"
MEMBERS = (
    "Lettuce_growth/1_README_Lettuce_Dataset.txt",
    "Lettuce_growth/4_Biomass.xlsx",
    "Lettuce_growth/5_Environment_Solution.xlsx",
)
SOURCE_SHA256 = {
    "Lettuce_growth/1_README_Lettuce_Dataset.txt": "6c23753c1b70dbde136d358031848cc37a1b0203447eecb8059ae4347fa35265",
    "Lettuce_growth/4_Biomass.xlsx": "9d68694bbb99178a28b7e4576d9f12532c6691346ec962f582f49a4a586f7546",
    "Lettuce_growth/5_Environment_Solution.xlsx": "263ec21d7097c1c5a384e351040ef1c96c789eb5cf00e05580ed9fbc9a65a3f3",
    "Lettuce_growth/2_Figure_1.png": "6c5e23d609b8a060789e52ccaa1a80241604772a9fde8825933f30e069e95f18",
    "Lettuce_growth/3_Figure_2.png": "e03a247637319fec484436a06acd3c3ec254db99cbd6685c5d5df231a8e81e04",
}


class RemoteArchive(io.RawIOBase):
    """Seekable, bounded range reader for this fixed public archive."""

    def __init__(self):
        self.position = 0
        self.bytes_transferred = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        candidate = (offset if whence == 0 else self.position + offset
                     if whence == 1 else ARCHIVE_BYTES + offset)
        if candidate < 0 or candidate > ARCHIVE_BYTES:
            raise ValueError("Invalid archive seek.")
        self.position = candidate
        return candidate

    def read(self, size=-1):
        if size < 0:
            size = ARCHIVE_BYTES - self.position
        size = min(size, ARCHIVE_BYTES - self.position)
        if size == 0:
            return b""
        if size > 8 * 1024 * 1024:
            raise ValueError("Refusing an unexpectedly large archive range.")
        start, end = self.position, self.position + size - 1
        request = urllib.request.Request(ARCHIVE_URL, headers={
            "User-Agent": "ASTRA-BIO-measured-growth-import/1.0",
            "Range": f"bytes={start}-{end}",
        })
        with urllib.request.urlopen(request, timeout=60) as response:
            expected = f"bytes {start}-{end}/{ARCHIVE_BYTES}"
            if response.status != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server did not return the requested bounded range.")
            data = response.read(size + 1)
        if len(data) != size:
            raise ValueError("Incomplete archive byte range.")
        self.position += size
        self.bytes_transferred += size
        return data


def acquire(directory: Path, *, include_figures=False) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(METADATA_URL, headers={
        "User-Agent": "ASTRA-BIO-measured-growth-import/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw_metadata = response.read(1024 * 1024 + 1)
    if len(raw_metadata) > 1024 * 1024:
        raise ValueError("Unexpectedly large source metadata.")
    metadata = json.loads(raw_metadata)
    archive = next((entry for entry in metadata["files"]
                    if entry["key"] == "Lettuce_growth.zip"), None)
    if archive is None or archive["size"] != ARCHIVE_BYTES or archive["checksum"] != f"md5:{ARCHIVE_MD5}":
        raise ValueError("Pinned source archive metadata changed.")
    if metadata["metadata"].get("license", {}).get("id") != "cc-by-4.0":
        raise ValueError("Pinned dataset license is not the expected CC-BY-4.0.")
    (directory / "zenodo_metadata.json").write_bytes(raw_metadata)
    reader = RemoteArchive()
    members = list(MEMBERS)
    if include_figures:
        members.extend(("Lettuce_growth/2_Figure_1.png", "Lettuce_growth/3_Figure_2.png"))
    retained = []
    with zipfile.ZipFile(reader) as zipped:
        for name in members:
            info = zipped.getinfo(name)
            if info.file_size > 4 * 1024 * 1024:
                raise ValueError("Unexpectedly large requested source member.")
            # zipfile verifies the ZIP entry CRC while reading.
            data = zipped.read(info)
            if name in SOURCE_SHA256 and hashlib.sha256(data).hexdigest() != SOURCE_SHA256[name]:
                raise ValueError(f"Pinned source member SHA256 check failed: {name}")
            target = directory / Path(name).name
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(data)
            temporary.replace(target)
            retained.append({"archive_member": name, "local_file": target.name,
                             "bytes": len(data), "zip_crc32": f"{info.CRC:08x}",
                             "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "title": metadata["metadata"]["title"],
        "creators": metadata["metadata"].get("creators", []),
        "source_record": RECORD_URL,
        "source_doi": metadata["metadata"].get("doi"),
        "concept_doi": "10.5281/zenodo.16912088",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "archive": {"url": ARCHIVE_URL, "bytes": ARCHIVE_BYTES,
                    "publisher_md5": ARCHIVE_MD5,
                    "whole_archive_checksum_verified": False,
                    "acquisition": "Selected original ZIP members by HTTP byte ranges; entry CRC verified."},
        "metadata_sha256": hashlib.sha256(raw_metadata).hexdigest(),
        "files": retained,
        "bytes_transferred": reader.bytes_transferred,
        "changes": "Original selected files unchanged; tabular normalization described separately.",
        "independence": "One shared NFT lettuce cultivation cycle; plants and repeated days are not independent cultivation cycles.",
        "limitations": ["No spaceflight or ASTRA-BIO tray observations.",
                        "No randomized water/light/temperature stress intervention is documented in this dataset.",
                        "Fresh biomass basis must be preserved; never reinterpret it as edible yield."],
    }
    (directory / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def workbook_rows(path: Path):
    """Read original XLSX cell values without executing formulas or macros."""
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    relationship_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as workbook:
        for entry in workbook.infolist():
            if entry.file_size > 12 * 1024 * 1024:
                raise ValueError("Unexpectedly large source workbook member.")
        strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            document = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            strings = ["".join(node.itertext()) for node in document.findall("s:si", namespace)]
        relations = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relations}
        document = ET.fromstring(workbook.read("xl/workbook.xml"))
        for sheet in document.findall("s:sheets/s:sheet", namespace):
            target = targets[sheet.attrib[relationship_key]]
            member = "xl/" + target.lstrip("/") if not target.startswith("/") else target.lstrip("/")
            rows = []
            worksheet = ET.fromstring(workbook.read(member))
            for row in worksheet.findall("s:sheetData/s:row", namespace):
                cells = {}
                for cell in row.findall("s:c", namespace):
                    value = cell.find("s:v", namespace)
                    value = value.text if value is not None else None
                    if cell.attrib.get("t") == "s" and value is not None:
                        value = strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        inline = cell.find("s:is", namespace)
                        value = "".join(inline.itertext()) if inline is not None else None
                    cells[cell.attrib["r"]] = value
                rows.append((int(row.attrib["r"]), cells))
            yield sheet.attrib["name"], rows


def normalize(directory: Path) -> dict:
    path = directory / "4_Biomass.xlsx"
    manifest_path = directory / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_entry = next(entry for entry in manifest["files"] if entry["local_file"] == path.name)
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if (actual_hash != source_entry["sha256"]
            or actual_hash != SOURCE_SHA256["Lettuce_growth/4_Biomass.xlsx"]):
        raise ValueError("Original biomass workbook integrity check failed.")
    measurements, omitted, source_dates = [], [], set()
    cycle_id = "ucdavis_nft_zenodo17041810_cycle_1"
    for sheet, rows in workbook_rows(path):
        headers = rows[0][1]
        columns = {}
        for cell, value in headers.items():
            match = re.fullmatch(r"(B\d+)\s*\(g\)", (value or "").strip())
            if match:
                columns[re.sub(r"\d+$", "", cell)] = match.group(1)
        if len(columns) != 6 or headers.get("B1") != "DAT (day)":
            raise ValueError("Unexpected biomass source sheet schema.")
        for row_number, cells in rows[1:]:
            age_text = cells.get(f"B{row_number}")
            if age_text is None:
                continue
            age_match = re.fullmatch(r"\s*(\d+)(?:\s*\(harvest\))?\s*", age_text)
            if age_match is None:
                raise ValueError("Unexpected source DAT value.")
            age = int(age_match.group(1))
            serial_text = cells.get(f"A{row_number}")
            raw_date = ""
            if serial_text is not None:
                serial = float(serial_text)
                raw_date = (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()
                source_dates.add(raw_date)
            for column, plant_id in columns.items():
                address = f"{column}{row_number}"
                raw_mass = cells.get(address)
                if raw_mass is None:
                    omitted.append({"source_reference": f"{path.name}:{sheet}!{address}",
                                    "plant_id": plant_id, "days_after_transplant": age,
                                    "reason": "No original biomass value; not interpolated or set to zero."})
                    continue
                mass = float(raw_mass)
                if not math.isfinite(mass) or mass < 0:
                    raise ValueError("Invalid source fresh biomass measurement.")
                measurements.append({
                    "observation_id": f"zenodo17041810_{plant_id}_dat{age:02d}",
                    "plant_id": plant_id,
                    "independent_cycle_id": cycle_id,
                    "crop_species": "Lactuca sativa",
                    "cultivar": "unspecified_butterhead",
                    "environment_id": "ucdavis_nft_two_tier_reference_cycle",
                    "days_after_transplant": age,
                    "fresh_mass_g": format(mass, ".15g"),
                    "mass_basis": "unspecified_fresh",
                    "source_reference": f"{path.name}:{sheet}!{address}",
                    "source_url": RECORD_URL,
                    "source_excel_date_serial": serial_text or "",
                    "source_excel_date": raw_date,
                })
    keys = {(entry["plant_id"], entry["days_after_transplant"]) for entry in measurements}
    if len(keys) != len(measurements) or len(measurements) != 540:
        raise ValueError("Unexpected duplicate/count change in the pinned source biomass cells.")
    target = directory / "growth_observations.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(measurements[0]))
        writer.writeheader()
        writer.writerows(measurements)
    report = {
        "rows": len(measurements),
        "plant_ids": sorted({entry["plant_id"] for entry in measurements}),
        "independent_cycle_ids": [cycle_id],
        "observed_days_after_transplant": sorted({entry["days_after_transplant"] for entry in measurements}),
        "cultivar_handling": "Source specifies butterhead lettuce, not a named cultivar; unspecified_butterhead preserves this uncertainty.",
        "seedling_age_at_transplant_days": 14,
        "mass_basis_handling": "Source describes non-destructive fresh biomass weighing; plant part is unspecified, so mass_basis=unspecified_fresh. Not edible yield.",
        "missing_measurements": omitted,
        "calendar_conflict": {
            "source_readme_period": "2024-02-21 to 2024-03-23",
            "raw_workbook_date_range": [min(source_dates), max(source_dates)],
            "handling": "Preserve source Excel dates without silently correcting the year; fit only the explicit DAT column. One source cycle is retained without assuming a calendar year.",
        },
        "normalization": "Unpivot original individual biomass cells from B2/B3/B4 sheets; exclude Sum columns and blank day31harvest mass. No interpolation, imputation, synthetic mass, or resource-response target generation.",
        "output": {"file": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()},
    }
    manifest["normalization"] = report
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (directory / "normalization_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--download", action="store_true", help="Explicitly fetch fixed public source files.")
    parser.add_argument("--include-figures", action="store_true", help="Also retain the two original experiment figures.")
    args = parser.parse_args()
    if args.download:
        manifest = acquire(args.directory, include_figures=args.include_figures)
        print(json.dumps({"source": manifest["source_record"], "files": len(manifest["files"]),
                          "bytes_transferred": manifest["bytes_transferred"]}, indent=2))
    report = normalize(args.directory)
    print(json.dumps({"normalized_rows": report["rows"], "plants": len(report["plant_ids"]),
                      "independent_cycles": len(report["independent_cycle_ids"]),
                      "observed_age_range": [min(report["observed_days_after_transplant"]),
                                             max(report["observed_days_after_transplant"])]}, indent=2))


if __name__ == "__main__":
    main()
