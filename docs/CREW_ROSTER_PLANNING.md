# Crew roster, nutrient needs and harvest deadlines

Open **Crew & nutrition** to edit the named people and their individual energy,
protein and vitamin C planning targets. Names and stable profile IDs remain
shared across tabs; playback does not reload demonstration names. Edited
targets need review before being applied. Sample blood tests are fictional and
do not produce prescriptions. Iron is outside this three-nutrient planner.

Use **Use this crew & replan from Day N+1** after selecting the last completed
day. The exact roster becomes a dated mission event. Previous days, closing
food stocks, finite water/electricity stores and growing crop ages carry
forward. Pending crew changes are replaced; unrelated future disruptions stay
effective. If no run exists, applying the crew creates a fresh Day-1 mission
with no inherited dated changes. Existing saved runs remain in history.

Overview now displays the people effective on its selected day, their targets
and the aggregate daily needs. Historical days keep their historical rosters.
Numeric arrivals with no names remain unassigned rather than inventing
identities. Independent target adjustments scale recorded individual target
proportions to the effective aggregate; shared allocations are not personal
menus. The editable nutrition draft remains separate until applied.

**What to grow next** automatically evaluates the saved adaptive plan from the
next day. Its **Harvest needed by Day** field limits the growing window. The
same deadline is available in the full Crop advisor. Advice considers:

- Effective crew demand on planting and harvest dates, including later events.
- Stored-food balance, expiry and predicted nutrient gaps.
- Reference crop composition, edible yield and full growth duration.
- Remaining growing area, daily water/electricity and configured finite stores.
- Existing plantings, fresh-food meal capacity and scenario crop losses.

The view separates selected future plantings from an additional batch that may
fit the remaining headroom. Late harvests receive no deadline credit. Crops
cannot close earlier gaps; the interface shows when stored food or recovery
options need review. Crop nutrients use USDA/reference composition multiplied
by modeled edible mass, not laboratory measurements of our harvest.

Gemini is unnecessary for these quantities: optimization and arithmetic
determine the plan. The existing optional Plant overview Gemini action can
curate local text evidence, with its server-side key remaining private.

Verification and scope: `docs/CREW_AND_LEAVES_VERIFICATION.json`.
