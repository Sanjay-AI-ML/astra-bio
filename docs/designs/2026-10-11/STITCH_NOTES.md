# Google Stitch generation notes

Generated design descriptions and suggestions follow. These are design-tool explanations, not scientific validation or live product status. Example values, labels and unimplemented copy must be replaced when the chosen design is wired to real app state.

The mockup has been refined into a compact, production-grade **Application Overview** designed specifically for a 1440 × 1050 desktop viewport, preserving the SEDS-inspired black and violet aesthetic while strictly adhering to your project constraints:

### Key Changes & Design Decisions:
1. **Removed All Invented Telemetry & Unimplemented Science:**
   - Stripped away LEO altitude, MET clocks, O₂/CO₂ recycling formulas, flight surgeon notes, folate alerts, cosmic radiation tickers, and speculative calibration badges.
   - Reframed Water and Energy strictly as **configured budgets** (`Water: 50 L/day`, `Energy: 8 kWh/day`) rather than measured live streams.

2. **Clean Header & Top Navigation:**
   - Header badges configured strictly to `DEMO DATA` and `PROTOTYPE · OUTPUTS DISABLED`.
   - Clean workspace switcher and notification utility without speculative orbital links.

3. **240px Sidebar & 6 Nav Items:**
   - Standardized 6 primary navigation tabs: **Overview**, **Crew & nutrition**, **Crops & food**, **Simulator**, **Plant screening**, and **Live devices**, with **Workspace settings** at the footer.

4. **Information Architecture (1440 × 1050 Dense App Layout):**
   - **Header Summary:** Clean title accompanied by the four verified mission figures (`4 crew`, `90 days`, `12.5 m²`, `Water 50 L/day`, `Energy 8 kWh/day`).
   - **Ecosystem Subsystem Diagram + Actions (Row 1):** Compact coupling cards displaying Nutritional Demand (Energy, Protein, Vitamin C), Active Crop Batches (Lettuce & Radish), and Allocation Engine (Fixed / Adaptive budgets), paired side-by-side with the prioritized action list (`Review dietary targets`, `Review crop schedule`, `Hardware readings unavailable`, and a subtle `View input assumptions` link).
   - **Scenario Control & Simulation Preview (Row 2):** Inline controls featuring `Water remaining: 60%`, `Event day: 30`, and `Run scenario`, alongside an SVG timeline curve tagged with `Illustrative preview`.
   - **Harvest Timetable (Row 3):** Clean data table listing Dwarf Butterhead Lettuce and Cherry Belle Radish with actual modeled progression, day windows, estimated yields, and the requested note `Model estimates · example schedule`.

---

Suggested next screen: Add modal for 'Review dietary targets'

---

Suggested next screen: Design the 'Crew & nutrition' detail screen

---

Suggested next screen: Design the 'Simulator' deep-dive screen

---

I have generated **exactly two** distinct dark-mode desktop alternatives for the ASTRA-BIO Application Overview, completely reimagining the layout, typography, and visual philosophy while strictly maintaining the verified product data, configured budgets, and honest prototype framing.

---

### **Variant B — Flight deck** (B — Flight deck)
**Design Direction:** *Operator-first mission operations console*
- **Aesthetic & Color:** High-contrast graphite (`#111416`), slate structural borders (`#2c333a`), and restrained technical amber (`#e6b667`) for accents, controls, and alert states.
- **Typography & Geometry:** Monospace and technical sans typography, squared 4px corners, clean mechanical alignment, and zero celestial or decorative space clutter.
- **Layout Structure:**
  - **Top Aligned Budget Strip:** Direct operator overview highlighting configured limits (`Water 50 L/day`, `Power 8 kWh/day`, `4 crew`, `90 days`, `12.5 m²`, and `Hardware readings unavailable (sandbox)`).
  - **Prominent What-If Workbench:** Centers the operator's workflow around the scenario control panel (`Water remaining: 60%`, `Event day: Day 30`, `Run scenario`) and a high-contrast `Illustrative preview` timeline response chart.
  - **Crisp Monospace Harvest Timetable:** Data-dense, aligned technical tabular layout for Chamber Alpha & Beta crops (`Model estimates · example schedule`).

---

### **Variant C — Habitat** (C — Habitat)
**Design Direction:** *Biology-first ecological habitat dashboard*
- **Aesthetic & Color:** Deep forest base (`#0c1b18`), soft ivory and sage typography (`#f4f4ee`), and fresh botanical emerald/lime accents (`#34d399` / `#a3e635`).
- **Typography & Tone:** Editorial, calm, scientific aesthetic with generous whitespace and flat hairline section dividers rather than repetitive boxed cards.
- **Layout Structure:**
  - **Horizontal Ecological Journey:** Clean progression ribbon mapping the closed-loop system: `1. Crew` → `2. Food` → `3. Crops` → `4. Resources` with configured baseline metrics.
  - **Botanical Imagery & Subsystem Panel:** Elegantly embeds real controlled-environment agriculture photography (Macro photograph of indoor controlled-environment agriculture hydroponic microgreens and dwarf lettuce grow tray with subtle LED illumination in a dark clean research facility, soft muted lighting, realistic botanical detail, high resolution, calm biology aesthetic) alongside active canopy batch tracking and prioritized actions (`Review dietary targets`, `Review crop schedule`, `View input assumptions`).
  - **Balanced Scenario & Harvest Split:** Organically pairs the adaptive resource response curve with the harvest timetable in an airy, non-repetitive layout.

---

Both screens preserve the standard 240px sidebar, the exact 6 core nav items, honest status badges (`DEMO DATA` and `PROTOTYPE · OUTPUTS DISABLED`), and contain zero unsupported science or invented telemetry.

---

Suggested next screen: Select Variant B and build out the 'Simulator' screen in the graphite/amber console style

---

Suggested next screen: Select Variant C and design the 'Crops & food' chamber monitoring view in the habitat style

---

Suggested next screen: A/B test a hybrid version blending B's workbench density with C's journey flow
