# Sample nutrition mission

This is a sample simulation requested by the user, not a physical habitat experiment. It uses the existing Pyomo/HiGHS planner through the local API.

- Four crew, 90 days, 20 m² growing area.
- Sample net water budget 55 L/day and crop electricity budget 40 kWh/day.
- Initial sample stocks: 140 kg dry oats, 45 kg dry/raw lentils, 20 kg peanut butter and 5 kg synthetic fortified bridge food.
- USDA reference composition for matched food/crop forms. EDEN ISS/NASA terrestrial harvest references for arugula, radish, kohlrabi and lettuce; resource transfer to our tray remains assumed.
- Sample daily per-person targets: 2200 kcal, 90 g protein and 100 mg vitamin C. These are not clinical prescriptions.
- On Day 30 the sample protein target increases 40%, to 126 g/person/day. Other inputs remain the same.
- Three-day soft reserve target, 0.8 kg fresh food/person/day and 1.2 kg total modeled food/person/day.

The synthetic bridge composition is explicitly 1000 kcal/kg, zero protein and 5000 mg vitamin C/kg. It is a coefficient placeholder, not a researched product or supplement dose. Dry lentils/oats are ingredient forms, with cooking/hydration/preparation resources outside the planner.

`inputs.json` holds the reusable input configuration and scenario. `run.json` holds the actual fixed/adaptive solve and local history ID. `advisor-day-*.json` holds nutrient rankings and resource checks for a hypothetical extra 0.25 m² growing batch on Days 1 and 31. `summary.json` holds outcomes and limits.

The completed example produced 49 fixed-plan days below tracked targets versus 12 adaptive-plan days. Modeled harvest was approximately 16.41 kg fixed and 84.16 kg adaptive. This is a result of the sample coefficients, not evidence of measured biological savings. The adaptive plan still has protein shortfalls and spends down its reserve.

Day-one protein comparison recommends the arugula reference profile `arugula_600` where an added batch fits. Its first harvest is Day 30. After the adaptive replan, the saved future schedule commits its available growing power, so an extra batch may be blocked; continuing/replacing the future crop mix is different from adding a batch to the existing schedule.

To reproduce while the API is running, execute from the application root:

```powershell
.venv\Scripts\python.exe scripts/run-sample-mission.py
```

This creates a new local run/configuration snapshot and rewrites these sample reports. Earlier runs are retained. It does not publish synthetic sensor packets or change MongoDB camera data or ESP32 firmware.
