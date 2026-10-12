# Disruption recovery planning

Implemented on 12 October 2026. This extends the existing Pyomo/HiGHS planner with actionable resource comparisons and fixed-policy stress tests. It adds decision support; it does not train a new AI model, prove biological performance or control hardware.

## Use the workflow

1. Open **What-if simulator**, choose a disruption and explicitly run the comparison.
2. Find **Compare recovery options** below the comparison results. It uses that saved run's submitted configuration and scenario, not unsubmitted edits in the scenario form.
3. Enter the lower harvest yield and additional delay to test. Defaults are 80% of the entered yield and three extra days. These are hypothetical stress assumptions.
4. Expand **Resource limits and reserve protection** to set the maximum additional food, daily water and daily electricity to test. Choose whether the stored-food reserve target is also mandatory.
5. Click **Calculate recovery options**. Review the ranked options, selected plan, proposed food quantities/allowances and stress-case table. The minimum-resource disclosure retains all three results, including zero-addition and infeasible cases.
6. Export the report JSON if needed. It contains the submitted inputs, input hash, source run ID, limits, plans, stress outcomes and boundaries. No inventory, existing comparison or equipment command is changed by analysis.

## What is calculated

The existing adaptive plan is compared with three separate interventions:

- **Stored food:** minimize the total additional kilograms across configured stored-food forms. The optimizer chooses their composition. This stock becomes available on the event day.
- **Water:** minimize one uniform additional litres/day allowance from the event day to mission end. Both entered crew-water demand and crop-water demand must fit the allowance.
- **Electricity:** minimize one uniform additional kWh/day allowance over the same period. The energy scope remains the entered crop coefficients, not an uninstrumented complete habitat.

Each rescue solve fixes nutrient shortfalls to zero while retaining area, harvest timing, food balances, expiry, nutrient upper limits, portion limits and tray increments. Reserve shortfalls are fixed to zero only when reserve protection is selected. Resource minima are minimized first; a second solve chooses a practical allocation without materially increasing that minimum. An optimal primary solve provides a proven model minimum. A time-limited feasible outcome reports only a feasible amount, with `primary_minimum: null` and `minimum_proven: false`. An infeasible result means this resource alone did not work within the chosen limit. It does not rule out a larger limit or a combination of resources.

If the existing plan already meets the required constraints, zero is a proven lower bound for additional resources and no duplicate rescue solve is needed. Nutrient adequacy means only the targets included in this configuration; it is not a complete diet assessment.

All options use the same inventory and active crop cohorts immediately before the event. Historical daily values, food allocations and inventory records are retained. For a persisted run, the API loads the server's saved record by ID and ignores client-supplied draft configuration. If saving previously failed, a fresh comparison is calculated from the submitted configuration; all options within that analysis still share one common history.

## How stress tests work

The submitted case, lower-yield case, delayed-harvest case and joint case replay each option's **fixed planting and requested meal schedule**. No reoptimization is hidden inside these tests. A yield multiplier applies to remaining harvests, while the delay extends active crop cohorts and can push a harvest beyond the mission. Delayed batch overlap is checked against growing area as well as water/power allowances. Extra resources remain available from the same event day.

When the yield multiplier is 1 or the delay is zero, redundant cases are omitted. Results show nutrient gap days, resource gap days, reserve gap days and the first nutrient gap. Passing three of four cases is a deterministic test count, not a 75% reliability estimate. Resource-stress replay retains the prototype's declared synthetic worst-resource-ratio yield proxy.

Ranking prioritizes remaining-mission feasibility, then worst tested unit-normalized nutrient shortage, then the number of cases meeting the required constraints. It does not invent a conversion between kg, L and kWh or claim financial optimality. A highest-ranked option can still have shortages; the interface states when no tested option meets all requirements.

## Important scope

Additional food inherits each existing form's age, expiry and nutrient-retention assumptions. Freshly manufactured resupply with a separate age/expiry is not modeled. Fresh crop harvest still cannot be stored beyond its harvest day. This can make some recovery interventions infeasible even with large nominal quantities.

These stress assumptions have no measured probabilities. They do not replace local crop trials, a calibrated environmental response model, physical sensor readings, or spaceflight validation. Oxygen, CO₂, food preparation, complete micronutrients and a biological recycling loop remain outside the planner.

Verified harvest logging and qualified sensor-to-planning feedback are subsequent integrations. This update does not turn fruit counts into food mass, infer water budgets from a low-water switch, or infer total habitat energy from one DC bus.

## Code and API

- `astra_bio/recovery.py`: analysis options, common-state recovery, ranking and fixed-policy tests.
- `astra_bio/planner.py`: optional resource variables, lexicographic minimum solve, event-day relief and delayed-cohort capacity checks.
- `frontend/src/RecoveryPanel.jsx`: explicit workflow, limits, recommendations, selected-plan evidence and JSON export.
- `POST /api/recovery`: accepts a saved `run_id` and `options`, or `config`, `scenario` and `options` when no saved run exists. Uses the existing solver lock, rejects invalid limits and supports up to 120 days, 12 crops and 20 stored food forms.

Checks cover exact small-case food/water/electricity minima, chronological supply delivery, unchanged history, infeasible limits, reserve requirements, fixed-policy stress failures, tray overlap, input validation, saved-state integrity and UI request/result handling. These are software checks with constructed cases, not physical benefits.
