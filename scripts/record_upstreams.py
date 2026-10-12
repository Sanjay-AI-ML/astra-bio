"""Record the source provenance of this workspace's shallow reference clones."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT.parent / "open-source"
REPOS = [
    (ROOT, "Apache-2.0", "LICENSE", "React/FastAPI application; original starter license/origin retained; Streamlit removed"),
    (SOURCES / "pyomo-gallery", "BSD-3-Clause", "LICENSE.md", "Diet-constraint formulation adapted in planner"),
    (SOURCES / "highs", "MIT", "LICENSE.txt", "Solver source reference; highspy package runs the solver"),
    (SOURCES / "plotly", "MIT", "LICENSE.txt", "Earlier chart reference; current React charts use Recharts"),
    (SOURCES / "node-red", "Apache-2.0", "LICENSE", "Local telemetry runtime installed as pinned npm release"),
    (SOURCES / "node-red-nodes", "Apache-2.0", "LICENSE", "SQLite node source; pinned npm package in runtime"),
    (SOURCES / "esphome", "MIT (Python) AND GPL-3.0 (C++ runtime)", "LICENSE", "ESPHome 2026.9.1 sensor firmware validated and compiled for ESP32-S3 with Arduino; not flashed or bench-tested"),
    (SOURCES / "mosquitto", "EPL-2.0 OR BSD-3-Clause", "LICENSE.txt", "Official source retained; Mosquitto 2.1.2 workspace binary provides tested authenticated local/TLS MQTT; no Windows service"),
    (SOURCES / "grocy", "MIT", "LICENSE.md", "Optional inventory reference; not integrated"),
    (SOURCES / "mealie", "AGPL-3.0", "LICENSE", "Optional recipe reference; not integrated"),
    (SOURCES / "ollama", "MIT", "LICENSE", "Optional loopback fact-selection adapter implemented; daemon/model not installed or required"),
]


def git(path, *arguments):
    return subprocess.check_output(["git", "-C", str(path), *arguments], text=True).strip()


def main():
    records = []
    for path, license_name, license_file, purpose in REPOS:
        actual_license = path / license_file
        if not actual_license.exists():
            candidates = list(path.glob("LICENSE*")) + list(path.glob("COPYING*"))
            if not candidates:
                raise FileNotFoundError(f"No top-level license found in {path}")
            actual_license = candidates[0]
        records.append({
            "name": path.name, "source_url": git(path, "remote", "get-url", "origin"),
            "cloned_commit": git(path, "rev-parse", "HEAD"), "local_path": str(path),
            "license": license_name, "license_file": str(actual_license), "purpose": purpose,
            "shallow_clone": git(path, "rev-parse", "--is-shallow-repository") == "true",
        })
    (ROOT / "UPSTREAM_SOURCES.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    gallery_notice = (SOURCES / "pyomo-gallery" / "LICENSE.md").read_text(encoding="utf-8")
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text(
        "# Third-party notices\n\n"
        "The app preserves the Streamlit starter's Apache-2.0 LICENSE. "
        "ASTRA-BIO's planner adapts the Pyomo Gallery diet-constraint pattern and extends it "
        "with daily stocks, crop cohorts, resources, scenario replanning and reserve slack. "
        "The complete Gallery notice follows.\n\n"
        "Cloned frameworks keep their own licenses in their source directories. "
        "See UPSTREAM_SOURCES.json for exact commits and paths. Python and npm package "
        "licenses are preserved inside the installed distributions. Optional services "
        "have their own obligations when modified or distributed.\n\n"
        "The current frontend uses React, Recharts, Lucide and Vite; original package licenses remain in frontend/node_modules and package-lock.json pins releases. FastAPI, Uvicorn, NumPy, Pillow and ONNX Runtime licenses remain in locked Python distributions.\n\n"
        "The MQTT runtime uses official Eclipse Mosquitto 2.1.2 binaries; vendor notices and byte provenance remain under runtime/mqtt. Paho and cryptography are locked Python releases. ESPHome firmware retains its source/license obligations if distributed.\n\n"
        "EDEN ISS data/paper attribution: Zabel et al. 2020, DOI10.3389/fpls.2020.00656, CC-BY-4.0. NASA OSD metadata identify CC0 and NTRS record permits public use. USDA FDC government data are public domain. Source identities/units/hashes are in data/research.\n\n"
        "The pinned imaflower/plantvillage-mobilenetv3 model card declares MIT. Its card, artifact hashes and revision are retained in runtime/plant-model/PROVENANCE.json. The smoke photograph is PlantVillage, attributed Mohanty/Hughes/Salathe 2016, DOI10.3389/fpls.2016.01419, reported CC-BY-SA-3.0; original bytes were downloaded unchanged. It is a smoke sample, not independent accuracy evidence.\n\n"
        "## Pyomo Gallery\n\n" + gallery_notice,
        encoding="utf-8",
    )
    print(f"Recorded {len(records)} source repositories and complete Pyomo Gallery notice.")


if __name__ == "__main__":
    main()
