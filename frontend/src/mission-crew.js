const nutrients = ['energy', 'protein', 'vitamin_c'];
const clone = value => structuredClone(value);

// Resolve only identities recorded for this mission; a numeric arrival cannot
// tell us a person's name. Nutrition edits stay a separate draft until applied.
export function missionCrewContext(run, fallbackConfig, day) {
  const config = run?.metadata?.config || fallbackConfig || {};
  const scenario = run?.metadata?.scenario || {};
  const row = run?.metadata?.adaptive?.daily?.find(item => item.day === day);
  let roster = clone(config.crew_profiles || []), count = config.crew || 0;
  let perCrew = {...config.targets_per_crew};
  let effectiveFrom = 1;
  const canceled = (config.planning_events || []).some(event => event.cancel_scenario_crew === true && event.day <= scenario.event_day);
  const events = (config.planning_events || []).map((event, index) => ({event, day: event.day, index}));
  if (scenario.event_day) events.push({day: scenario.event_day, index: -1, event: null});
  events.sort((a, b) => a.day - b.day || a.index - b.index);
  for (const item of events) {
    if (item.day > day) break;
    const event = item.event;
    if (!event) {if (!canceled) count += scenario.extra_crew || 0;perCrew=Object.fromEntries(Object.entries(perCrew).map(([key,value])=>[key,value*(scenario.target_factors?.[key]??1)]));}
    else if (event.crew_profiles?.length) {roster = clone(event.crew_profiles); count = event.crew; effectiveFrom = item.day;}
    else if (event.crew != null) {if (count !== event.crew) roster = []; count = event.crew;}
    if(event?.targets_per_crew)perCrew={...event.targets_per_crew};
  }
  count = row?.crew ?? count;
  if (roster.length > count) roster = [];
  const totals = Object.fromEntries(nutrients.map(key => [key, row?.[key + '_target'] ?? Number(perCrew[key] || 0) * count]));
  const namedCount = roster.length, unnamedCount = Math.max(0, count - namedCount);
  for (const key of nutrients) {
    const originalTotal = roster.reduce((sum, profile) => sum + Number(profile.targets?.[key] || 0), 0);
    const denominator = originalTotal + unnamedCount * (namedCount ? originalTotal / namedCount : Number(config.targets_per_crew?.[key] || 0));
    for (const profile of roster) profile.targets[key] = denominator ? Number(profile.targets[key] || 0) * totals[key] / denominator : 0;
  }
  return {members: roster, crew_count: count, named_count: namedCount, unnamed_count: unnamedCount, aggregate_daily_targets: totals, effective_from_day: effectiveFrom};
}

export function initialNutritionRoster(data) {
  const run = data.last_run;
  const context = missionCrewContext(run, data.config, run?.metadata?.continuation?.next_day || 1);
  return clone(context.members.length ? context.members : data.crew_sample?.profiles || data.profiles || []);
}
