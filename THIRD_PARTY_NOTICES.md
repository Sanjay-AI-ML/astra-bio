# Third-party notices

The app preserves the Streamlit starter's Apache-2.0 LICENSE. ASTRA-BIO's planner adapts the Pyomo Gallery diet-constraint pattern and extends it with daily stocks, crop cohorts, resources, scenario replanning and reserve slack. The complete Gallery notice follows.

Cloned frameworks keep their own licenses in their source directories. See UPSTREAM_SOURCES.json for exact commits and paths. Python and npm package licenses are preserved inside the installed distributions. Optional services have their own obligations when modified or distributed.

The current frontend uses React, Recharts, Lucide and Vite; original package licenses remain in frontend/node_modules and package-lock.json pins releases. FastAPI, Uvicorn, NumPy, Pillow and ONNX Runtime licenses remain in locked Python distributions.

The MQTT runtime uses official Eclipse Mosquitto 2.1.2 binaries; vendor notices and byte provenance remain under runtime/mqtt. Paho and cryptography are locked Python releases. ESPHome firmware retains its source/license obligations if distributed.

EDEN ISS data/paper attribution: Zabel et al. 2020, DOI10.3389/fpls.2020.00656, CC-BY-4.0. NASA OSD metadata identify CC0 and NTRS record permits public use. USDA FDC government data are public domain. Source identities/units/hashes are in data/research.

The pinned imaflower/plantvillage-mobilenetv3 model card declares MIT. Its card, artifact hashes and revision are retained in runtime/plant-model/PROVENANCE.json. The smoke photograph is PlantVillage, attributed Mohanty/Hughes/Salathe 2016, DOI10.3389/fpls.2016.01419, reported CC-BY-SA-3.0; original bytes were downloaded unchanged. It is a smoke sample, not independent accuracy evidence.

PlantDoc fine-tuning attribution: [PlantDoc-Dataset](https://github.com/pratikkayal/PlantDoc-Dataset), pinned commit `5467f6012d78d1c446145d5f582da6096f852ae8`, with the upstream repository's CC-BY-4.0 declaration. Selected original photographs remain unchanged in private local training files. Decoding, duplicate exclusion, label mapping, augmentation and classifier fine-tuning are ASTRA-BIO processing changes. Original source paths, source license and README, file identities, split membership and exclusions are retained in `runtime/ml-training/`; the completed report and artifact manifest are retained in `data/reports/`.

Measured lettuce-growth attribution: Saeed Karimzadeh and Md Shamim Ahamed, University of California, Davis, [Lettuce Dataset with RGB Canopy Images, Biomass, Nutrient Solution, and Environmental Variables for Machine Learning Model Development](https://zenodo.org/records/17041810), DOI `10.5281/zenodo.17041810`, CC-BY-4.0. Selected source XLSX/README files are unchanged. ASTRA-BIO extracts 540 plant/day fresh-mass observations and fits a source-specific age curve; changes and checksums are recorded in `data/research/growth/source_manifest.json`. The original figures are retained unchanged for attribution/context and are not training inputs. The separately referenced Wageningen light/temperature-treatment dataset was not downloaded successfully or fitted; its retrieval limitation remains explicit.

## Pyomo Gallery

LICENSE
=======

Copyright (c) 2015-2025 National Technology and Engineering Solutions of
Sandia, LLC . Under the terms of Contract DE-NA0003525 with National
Technology and Engineering Solutions of Sandia, LLC , the U.S.
Government retains certain rights in this software.

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

* Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

* Neither the name of the Sandia National Laboratories nor the names of
its contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


