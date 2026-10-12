# Research basis for reviewed changes during a mission

Research checked 12 October 2026. This document separates established research,
ASTRA-BIO implementation choices and the evidence still needed for validation.

## The planning method

A mission change should take effect on a named day. If Day 30 is completed, a
new crew member or reviewed nutritional target takes effect on Day 31. Days
1–30, food already consumed, remaining stock and active crop cohorts form the
initial state of a new optimisation. The planner changes the future schedule;
it must not recreate the mission from its original food stock or rewrite what
already happened. Further changes repeat that same state transition.

This follows the established idea of receding-horizon planning: optimise the
future from the latest available state, implement or review the next decisions,
and solve again when the state or needs change. ASTRA-BIO uses a daily linear or
mixed-integer planting and meal planner. It is not a validated nonlinear crop
controller, and it does not implement the reinforcement-learning controller
described by the source paper.

[Mallick et al., 2025, *Reinforcement learning-based model predictive control
for greenhouse climate control*](https://research.wur.nl/en/publications/reinforcement-learning-based-model-predictive-control-for-greenho/)
shows how model-based optimisation can enforce physical constraints while
updating decisions, and discusses inaccurate biological models and prediction
uncertainty. Its reported controller improvements are simulation results; they
are not measured ASTRA-BIO performance.

## What crop suggestions must account for

For each remaining day, aggregate the reviewed individual energy, protein and
vitamin C targets of the crew active that day. Compare the planned meals with
those daily totals. A new crop batch has a planting date and a first harvest
date; it cannot solve a shortage before harvest.

The crop advisor now separates two useful questions:

1. Which crops and dates are already selected by the saved resource-constrained
   planting and meal plan?
2. Can an additional batch fit without displacing those saved allocations, and
   would its consumable harvest actually help a nutrient gap on that day?

With a complete saved forecast and nutrient gaps, an additional batch receives
credit only for the remaining gap on its harvest day. Credit is capped by the
batch mass, available fresh-food meal capacity, total meal-mass limits and
known nutrient upper-bound room. Existing fresh-crop meals share that capacity.
Separate target-normalised shares keep grams, milligrams and kilocalories from
being added directly. Production per square metre and growing day remains a
comparison and tie-break value, not a promise of food available every day.

The current planner consumes or discards fresh produce on harvest day. It does
not assume unvalidated storage of the full harvest for later days. Shortfalls
before harvest require stored-food allocation, protected-reserve review,
recovery options or an explicit report that the available resources cannot
meet the targets.

Daily resource capacity and finite stock are different constraints. A tray can
fit today's water flow but still require more total water than the mission has
left. Additional-batch screening therefore checks daily capacity throughout
growth and the finite store left after all later saved allocations. It does
not spend water or energy already reserved for a later part of the plan.

[Liang et al., 2024, *Modeling of Space Crop-Based Dishes for Optimal Nutrient
Delivery to Astronauts and Beyond on Earth*](https://pubs.acs.org/doi/10.1021/acsfoodscitech.3c00396)
already optimises crop combinations using nutritional constraints and water
requirements. This supports the use of constraint-based nutritional crop
selection and establishes prior art; ASTRA-BIO must not claim to have invented
nutrition-based crop optimisation.

## Why the problem is credible

[NASA's food and nutrition risk record](https://www.nasa.gov/directorates/esdmd/hhp/food-and-nutrition-risk/)
identifies the difficulty of maintaining acceptable, safe and nutritious food
through long missions with limited resupply. Food quantity alone is an
incomplete measure; meal composition, storage and practical resource
constraints matter. This supports the planning problem, without proving that
this prototype provides complete astronaut nutrition.

The [Wageningen Autonomous Greenhouse Challenge](https://www.wur.nl/en/research/plant/autonomous-greenhouse-challenge)
has demonstrated autonomous cultivation using sensors, images and climate
models. [Its fourth challenge report](https://www.wur.nl/en/news/winner-4th-autonomous-greenhouse-challenge-announced)
describes a physically grown dwarf-tomato cycle in which algorithms managed
lighting, heating, carbon dioxide, water, plant density and harvest timing.
These demonstrations establish that crop control and harvest scheduling have
real experimental precedents. Their measurements are not transferable
validation of our tray or our nutrient reference profiles.

## Novelty: a defensible project claim

[NASA's September 2026 Mars to Table winners](https://www.nasa.gov/directorates/stmd/prizes-challenges-crowdsourcing-program/centennial-challenges/nasa-unveils-winning-designs-for-mars-space-food-systems-challenge/)
include integrated food-system concepts: Adaptive Nourishment Infrastructure
and Fresh, Ferment, Reserve. The challenge judged system designs, not a fully
proven Mars habitat. Integrated crops, nutrition, resources and reserves are
therefore an active and timely research direction with substantial prior art.

A defensible ASTRA-BIO project contribution is a working, explainable prototype
that preserves mission history, accepts reviewed changes in individual crew
needs, carries remaining food and finite resources forward, and explains which
harvests can help which future nutrient gaps. This is our product design
recommendation and integration claim. The research does not establish a
world-first algorithm, patent novelty, clinical efficacy or guaranteed savings.

## Blood markers and Vamshika's fictional low-iron example

Sample haemoglobin and ferritin values are labelled fictional. Ferritin is an
iron-status marker, not a dietary target or a direct estimate of the amount of
iron to eat; inflammation and other clinical context affect interpretation.
The [NIH Office of Dietary Supplements iron fact sheet](https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/)
discusses these distinctions. ASTRA-BIO does not turn a blood value into a
diagnosis or prescribe a therapeutic intake. A reviewed dietary planning target
is an input, and the current food optimiser covers energy, protein and vitamin
C. An iron-driven crop recommendation requires separately verified edible-form
iron composition, suitable crop-growth data and reviewed target bounds before
being implemented or presented as a supported capability.

## Validation still required

- Check repeated continuations from the same boundary preserve past daily rows,
  past food consumption, remaining inventory and active cohorts.
- Verify an added crew member changes targets only from their arrival day.
- Test harvest deadlines, depleted stock, failed or retired growing area,
  maximum portions, expiry and finite-resource exhaustion.
- Compare fixed and adaptive strategies from the same past history and stocks;
  report nutrient-gap days, reserve protection and water/energy use, including
  failures rather than only favourable examples.
- Calibrate yield and harvest date against measured local crop cycles, holding
  out entire plants or cycles. Published crop-reference values and a simulated
  mission remain different from biological validation.
- Report sensitivity to plausible yield and timing errors. Passing a few
  deterministic stress cases is not an estimated probability of success.
- Keep measured observations, reference composition, sample health profiles,
  reviewed assumptions and solver output visibly distinguishable.

The crop-advisor regression suite covers these marginal recommendation rules;
passing software tests verifies implementation behaviour, not clinical or
spaceflight validation.
