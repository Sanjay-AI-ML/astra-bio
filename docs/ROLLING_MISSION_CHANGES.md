# Continue a mission after crew or resource changes

Open **Mission overview → Change crew at Day N** while viewing or playing a
saved simulation. This pauses playback and opens the complete roster editor at
the selected day. The same editor remains available in **Crops & food** and
**What-if simulator**. A completed saved simulation is required.

1. Choose the last completed mission day, for example Day 30.
2. Keep the existing people and add or remove future crew. Added demonstration
   people are numbered. Edit each person's energy, protein and vitamin C targets.
3. If needed, enable a future daily water/electricity allowance or available
   growing-area override. These are absolute total allowances from Day 31, not
   extra supplies and not the percentage remaining in a tank.
4. Mark the planning targets reviewed and apply the change. A new saved run starts
   its recalculated future on Day 31. The earlier run remains in local history.

Crew count is an operator input, not a fixed four-to-six rule. The earlier
demonstration saved six-person roster events on Days 31 and 32; replaying that
saved schedule made those changes appear automatic. **Replace scheduled future
crew changes** is now selected by default in the roster editor. Applying a new
roster removes pending roster changes and cancels a pending scenario arrival,
while keeping unrelated water, power, crop and independent target changes.
Uncheck it only when the listed later crew arrivals should remain scheduled.
Completed crew events and all elapsed daily results remain unchanged.

To begin a separate mission, choose **What-if simulator → Start a new mission**.
It uses the configured starting crew, food and resource inputs from Day 1, with
no inherited planning events or scenario disruptions. Previous runs stay in
history. **Run comparison** continues to evaluate explicitly entered scenarios
and dated changes in the current configuration.

## What carries forward

The checkpoint includes the source plan's closing food inventory, already used
water and electricity, and active crop batches with their original planting and
harvest dates. Days 1–30 keep their daily rows, meals and closing inventories.
The optimizer can retire some active area if the remaining constraints require
it; retired area is reported in its warnings. It never makes a replacement crop
instantly mature. The original source cohort schedule remains in continuation
evidence for inspecting that transition.

The model aggregates individual reviewed targets:

`crew target for nutrient n on day d = sum(target of each active person)`

It uses that total to allocate shared food. This does not establish an individual
menu or prove that nutrients reached each person. Sample blood tests and photos
never determine those targets. Iron remains outside the three-nutrient planner.

A chronological ledger records absolute changes. Unless explicitly replaced,
an announced future Scenario event remains effective on its original date.
Replacing future crew changes suppresses its arrival count only; reviewed
protein targets do not erase an independent announced target increase or a
resource reduction. A later absolute review can supersede those values.

## Remaining resources

Daily flow capacity and cumulative usable stock are separate constraints. Mission
inputs have optional **total usable mission water** and **total mission electricity
allowance** fields. If configured:

`closing store = opening store + explicit supply - modeled consumption`

A continuation starts from the previous closing store. Editing a daily allowance
does not refill it. Without a configured total, the app reports that the finite
store is not configured and enforces the declared daily rates. Energy production,
water recycling and automatic replenishment are not simulated. Depleted crew
water service becomes an explicit capacity gap rather than negative stock or
fictional delivered water.

## Which crops to grow

The mission solver considers future daily targets, stored-food composition and
expiry, growth delays, edible yield, area, water, electricity, fresh-meal capacity
and configured reserve/upper limits together. It chooses dates and areas for a
crop mix. The crop advisor now shows those **already selected future batches**
separately from a comparison of **additional batches**.

For an additional batch, useful credit is the lesser of the consumable harvest
nutrients and the saved plan's gap on the actual harvest day. All existing fresh
meals share the same fresh-food limit. A shortage earlier than harvest receives
no credit. Different nutrient units are normalized against the crew target for
that day before comparing scores. Remaining finite capacity is what remains
after the entire saved future schedule, not today's water already needed later.

The current planner consumes or discards fresh produce on harvest day. It does
not assume that an entire fresh batch remains edible for weeks. Stored food can
bridge a delay; insufficient stocks and constraints remain visible as shortfalls.

## Reproducible evidence

Run `.venv\Scripts\python.exe scripts/run-rolling-crew-demo.py` from the app root
with the local API running. It creates a new fictional 90-day run with four crew,
USDA edible-food references, EDEN ISS/NASA crop endpoints, explicitly assumed
resources and synthetic bridge food. It then adds Sample Crew 5 and 6 from Day 31.
Data and outputs are saved under `data/samples/rolling-crew-change/`.

In the recorded example, total daily targets changed from 8,800 to 13,200 kcal,
504 to 704 g protein, and 400 to 600 mg vitamin C. These are fictional planning
inputs, not recommended intakes. Days 1–30 and Day-30 food stocks were unchanged;
3,801.02 L and 2,921.57 kWh remained at that checkpoint. The optimizer selected 24
future batches. Target-gap days in Days 31–90 changed from 60 for the prior
schedule to 55 for the replan: **this sample is still resource/food insufficient**.
The difference is simulated performance, not a measured biological benefit.

A second actual browser submission changed one reviewed sample protein target
from Day 32. It preserved Days 1–31 and the same Day-31 food inventory. Software
verification is in `ROLLING_VERIFICATION.json`; the complete new run is saved as
`data/samples/rolling-crew-change/browser-continued-run.json`.

Tests cover repeated events, chronological future arrivals, finite conservation,
drinking-water exhaustion, crop ages and losses, late harvests, meal caps,
reviewed-input validation and history restoration. Calibration against measured
local crop cycles is still needed. Research and a defensible integration claim
are documented in [ROLLING_RESEARCH.md](ROLLING_RESEARCH.md).
