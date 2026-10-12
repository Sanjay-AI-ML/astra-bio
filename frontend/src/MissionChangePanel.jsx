import React, {useEffect, useId, useRef, useState} from 'react';
import {ArrowRight, Plus, UsersRound} from 'lucide-react';
import {randomCrewName} from './crew-names.js';
import './mission-change.css';

const tracked = ['energy', 'protein', 'vitamin_c'];
const labels = {energy: 'Energy', protein: 'Protein', vitamin_c: 'Vitamin C'};
const units = {energy: 'kcal/day', protein: 'g/day', vitamin_c: 'mg/day'};
const budgets = [
  {key: 'water_budget_l_per_day', label: 'Daily water allowance', unit: 'L/day', max: 10000},
  {key: 'power_budget_kwh_per_day', label: 'Daily electricity allowance', unit: 'kWh/day', max: 1000},
  {key: 'area_m2', label: 'Available growing area', unit: 'm²', max: 10000},
];
const numeric = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
const format = value => numeric(value) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 2}) : 'Unknown';

function nextConditions(config, run, day) {
  const row = run?.metadata?.adaptive?.daily?.find(item => item.day === day);
  const applied = (config?.planning_events || []).filter(event => event.day <= day);
  const active = Object.assign({}, ...applied);
  return {row, active};
}

export function missionChangeProfiles(run, config, sampleProfiles = [], day = 1) {
  const {row, active} = nextConditions(config, run, day);
  const count = Math.min(12, Math.max(1, row?.crew || active.crew || config?.crew || 4));
  const continuationEffective = run?.metadata?.continuation?.next_day;
  const saved = active.crew_profiles || (!continuationEffective || continuationEffective <= day
    ? run?.metadata?.continuation?.crew_profiles || config?.crew_profiles || run?.metadata?.crew_profiles : config?.crew_profiles);
  const source = saved?.length ? saved : sampleProfiles;
  const currentTargets = Object.fromEntries(tracked.map(key => [key, numeric(row?.[key + '_target']) ? Number(row[key + '_target']) / count : config?.targets_per_crew?.[key]]));
  const profiles = Array.from({length: count}, (_, index) => {
    const profile = source[index];
    return {
      profile_id: profile?.profile_id || 'crew-' + (index + 1),
      name: profile?.name || 'Sample Crew ' + (index + 1),
      targets: saved?.length ? {...currentTargets, ...profile?.targets} : {...currentTargets},
      ...(profile?.age != null ? {age: profile.age} : {}),
      ...(profile?.sex ? {sex: profile.sex} : {}),
      targets_reviewed: false,
    };
  });
  for (const key of tracked) {
    const total = profiles.reduce((sum, profile) => sum + (Number(profile.targets[key]) || 0), 0);
    if (numeric(row?.[key + '_target']) && Number(row[key + '_target']) > 0 && total > 0) {
      const factor = Number(row[key + '_target']) / total;
      for (const profile of profiles) profile.targets[key] *= factor;
    }
  }
  return profiles;
}

function TargetPreview({before, after, fromDay}) {
  return <section className="mission-change-targets" aria-label="Future crew nutrient target comparison">
    <div className="mission-change-subheading"><h3>What changes in daily demand?</h3><p>Sum of the listed crew targets · applies from Day {fromDay}</p></div>
    <div className="mission-change-target-plots">{tracked.map(key => {
      const maximum = Math.max(Number(before[key]) || 0, Number(after[key]) || 0, 1);
      return <div className="mission-change-target" key={key}>
        <div><strong>{labels[key]}</strong><span>{units[key]}</span></div>
        <div className="mission-change-bar-row"><span>Saved</span><div className="mission-change-track"><i style={{width: numeric(before[key]) ? Number(before[key]) / maximum * 100 + '%' : '0%'}}/></div><b>{format(before[key])}</b></div>
        <div className="mission-change-bar-row future"><span>Proposed</span><div className="mission-change-track"><i style={{width: numeric(after[key]) ? Number(after[key]) / maximum * 100 + '%' : '0%'}}/></div><b>{format(after[key])}</b></div>
      </div>;
    })}</div>
    <p className="mission-change-small">Each nutrient has its own scale and unit. The planner balances total crew needs; individual meal allocation is outside this view.</p>
  </section>;
}

export default function MissionChangePanel({run, config, sampleProfiles = [], missionDay = 1, setMissionDay, setRun, request, notify = () => {}, planningBusy = false}) {
  const titleId = useId();
  const planningConfig = run?.metadata?.config || config || {};
  const horizon = Number(planningConfig.days) || 1;
  const runKey = JSON.stringify([run?.history_id, run?.metadata, sampleProfiles]);
  const [day, setDay] = useState(Math.max(1, Math.min(horizon, Number(missionDay) || 1)));
  const [profiles, setProfiles] = useState(() => missionChangeProfiles(run, planningConfig, sampleProfiles, day));
  const [reviewed, setReviewed] = useState(false), [reason, setReason] = useState('');
  const [replaceFutureCrew, setReplaceFutureCrew] = useState(true);
  const [enabled, setEnabled] = useState({}), [values, setValues] = useState({});
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipt, setReceipt] = useState(null);
  const revision = useRef(0), nextProfile = useRef(13);
  const currentContext = JSON.stringify([runKey, day, profiles, reviewed, reason, enabled, values, replaceFutureCrew]);
  const contextRef = useRef(currentContext); contextRef.current = currentContext;
  const lastCompleted = Number(run?.metadata?.continuation?.through_day) || 0;
  const nextDay = day + 1;
  const rows = run?.metadata?.adaptive?.daily || [];
  const atBoundary = rows.find(row => row.day === day);
  const {row: futureRow, active: futureEvent} = nextConditions(planningConfig, run, nextDay);
  const openingStocks = run?.metadata?.adaptive?.inventories?.[day];
  const storedFoods = planningConfig.foods || [];
  const hasFoodLedger = openingStocks && storedFoods.every(food => numeric(openingStocks[food.id]));
  const waterStoreConfigured = numeric(planningConfig.initial_water_l);
  const energyStoreConfigured = numeric(planningConfig.initial_energy_kwh);
  const carried = (run?.metadata?.adaptive?.planting || []).filter(batch => batch.day <= day && batch.harvest_day > day);
  const pendingCrewChanges = (planningConfig.planning_events || []).filter(change => change.day >= nextDay && (change.crew != null || change.crew_profiles?.length))
    .map(change => ({day: change.day, label: (change.crew ?? change.crew_profiles.length) + ' crew'}));
  const scenario = run?.metadata?.scenario;
  const scenarioCrewCanceled = (planningConfig.planning_events || []).some(change => change.cancel_scenario_crew === true && change.day <= scenario?.event_day);
  if (!scenarioCrewCanceled && scenario?.event_day >= nextDay && Number(scenario.extra_crew) > 0) pendingCrewChanges.push({day: scenario.event_day, label: '+' + scenario.extra_crew + ' crew'});
  pendingCrewChanges.sort((a, b) => a.day - b.day);
  const resourceDefaults = {
    water_budget_l_per_day: futureRow?.water_available_l ?? futureEvent.water_budget_l_per_day ?? planningConfig.water_budget_l_per_day,
    power_budget_kwh_per_day: futureRow?.power_available_kwh ?? futureEvent.power_budget_kwh_per_day ?? planningConfig.power_budget_kwh_per_day,
    area_m2: futureRow?.area_available_m2 ?? futureEvent.area_m2 ?? planningConfig.area_m2,
  };

  useEffect(() => {
    revision.current++; setBusy(false); setError(''); setReceipt(null); setReviewed(false); setEnabled({}); setReason(''); setReplaceFutureCrew(true);
    setProfiles(missionChangeProfiles(run, planningConfig, sampleProfiles, day));
    setValues({});
  }, [runKey]);
  useEffect(() => {
    const selected = Math.max(1, Math.min(horizon, Number(missionDay) || 1));
    if (selected !== day) {revision.current++; setDay(selected); setProfiles(missionChangeProfiles(run, planningConfig, sampleProfiles, selected)); setBusy(false); setError(''); setReviewed(false);}
  }, [missionDay, horizon]);
  useEffect(() => () => {revision.current++;}, []);

  function edit(action) {
    revision.current++; setBusy(false); setError(''); setReceipt(null); setReviewed(false); action();
  }
  function selectDay(value) {
    if (!Number.isInteger(value) || value < 1 || value > horizon) return;
    edit(() => {setDay(value); setProfiles(missionChangeProfiles(run, planningConfig, sampleProfiles, value)); setMissionDay?.(value);});
  }
  function updateProfile(id, key, value) {
    edit(() => setProfiles(previous => previous.map(profile => profile.profile_id === id
      ? key === 'name' ? {...profile, name: value} : {...profile, targets: {...profile.targets, [key]: value}}
      : profile)));
  }
  function addCrew() {
    if (profiles.length >= 12) return;
    const name = randomCrewName(profiles.map(profile => profile.name));
    const id = 'crew-added-' + nextProfile.current++;
    edit(() => setProfiles(previous => [...previous, {profile_id: id, name,
      targets: Object.fromEntries(tracked.map(key => [key, numeric(atBoundary?.[key + '_target']) && Number(atBoundary?.crew) > 0 ? Number(atBoundary[key + '_target']) / Number(atBoundary.crew) : planningConfig.targets_per_crew?.[key]])), targets_reviewed: false}]));
  }

  async function applyChange(event) {
    event.preventDefault();
    if (!run?.metadata || !setRun || day >= horizon || day < lastCompleted || busy || planningBusy) return;
    if (!reviewed) {setError('Review the future crew targets before applying this change.'); return;}
    if (!profiles.length || profiles.length > 12 || profiles.some(profile => !profile.name.trim() || tracked.some(key => !numeric(profile.targets[key]) || Number(profile.targets[key]) <= 0))) {
      setError('Give each crew member a name and positive energy, protein and vitamin C planning targets.'); return;
    }
    const resourceChanges = {};
    for (const field of budgets) if (enabled[field.key]) {
      const value = values[field.key] ?? resourceDefaults[field.key];
      if (!numeric(value) || Number(value) < 0 || Number(value) > field.max) {setError('Enter a valid ' + field.label.toLowerCase() + ' in ' + field.unit + '.'); return;}
      resourceChanges[field.key] = Number(value);
    }
    const missionChange = {crew_profiles: profiles.map(profile => ({...profile, name: profile.name.trim(),
      targets: Object.fromEntries(tracked.map(key => [key, Number(profile.targets[key])])), targets_reviewed: true})),
      replace_future_crew_changes: replaceFutureCrew, ...resourceChanges, ...(reason.trim() ? {reason: reason.trim()} : {})};
    const ticket = ++revision.current, context = currentContext;
    setBusy(true); setError('');
    try {
      const result = await request('/plans/continue', {run_id: run.history_id || null,
        ...(!run.history_id ? {metadata: run.metadata} : {}), through_day: day, mission_change: missionChange});
      if (ticket !== revision.current || context !== contextRef.current) return;
      if (!result.metadata?.adaptive?.daily?.length) throw new Error('Replanning did not return a usable future plan. Your saved mission is still available.');
      setReceipt(result); setRun(result); setMissionDay?.(nextDay);
      notify(result.history_warning || 'Updated ' + profiles.length + ' crew from Day ' + nextDay + '. Simulated history, remaining stock and growing crops are carried forward.', !!result.history_warning);
    } catch (failure) {
      if (ticket === revision.current && context === contextRef.current) {setError(failure.message || 'The future plan could not be recalculated.'); notify(failure.message || 'The future plan could not be recalculated.', true);}
    } finally {if (ticket === revision.current && context === contextRef.current) setBusy(false);}
  }

  const before = Object.fromEntries(tracked.map(key => [key, futureRow?.[key + '_target'] ?? null]));
  const after = Object.fromEntries(tracked.map(key => [key, profiles.every(profile => numeric(profile.targets[key])) ? profiles.reduce((total, profile) => total + Number(profile.targets[key]), 0) : null]));
  const accepted = receipt || (run?.metadata?.continuation?.mission_change ? run : null);
  const acceptedDetails = accepted?.metadata?.continuation;
  const acceptedFuture = (accepted?.metadata?.adaptive?.daily || []).filter(row => row.day >= (acceptedDetails?.next_day || nextDay));
  const firstGap = acceptedFuture.find(row => row.shortfall_normalized > 1e-6);
  const harvests = (accepted?.metadata?.adaptive?.planting || []).filter(batch => batch.harvest_day >= (acceptedDetails?.next_day || nextDay)).sort((a, b) => a.harvest_day - b.harvest_day);
  const disabled = busy || planningBusy;

  return <section className="mission-change" aria-labelledby={titleId}>
    <div className="mission-change-heading"><div><span className="eyebrow"><UsersRound size={16}/> CHANGES DURING THE MISSION</span><h2 id={titleId}>Update crew & continue the plan</h2><p>Add a crew member, edit reviewed dietary targets or update future resource allowances. The next plan starts with the food and crops remaining at your selected day.</p></div><span className="source-pill">Simulated state</span></div>
    <form onSubmit={applyChange}>
      <div className="mission-change-boundary"><label className="field"><span>Continue after completed Day</span><input type="number" min={Math.max(1, lastCompleted)} max={horizon} step="1" value={day} disabled={disabled} onChange={event => selectDay(Number(event.target.value))}/></label><div><strong>{nextDay <= horizon ? 'Day ' + nextDay + ' onward' : 'Mission horizon reached'}</strong><span>{Math.max(0, horizon - day)} remaining days · Days 1–{day} stay unchanged</span></div></div>
      <div className="mission-change-state" aria-label={'Saved state at end of Day ' + day}>
        <div><span>Remaining stored food</span><strong>{hasFoodLedger ? format(storedFoods.reduce((total, food) => total + Number(openingStocks[food.id]), 0)) + ' kg' : 'Unknown'}</strong><small>Saved closing stock; no new supplies added</small></div>
        <div><span>Growing batches carried forward</span><strong>{format(carried.length)}</strong><small>Planted earlier; harvest remains in the future</small></div>
        <div><span>Remaining water store</span><strong>{numeric(atBoundary?.water_remaining_l) ? format(atBoundary.water_remaining_l) + ' L' : waterStoreConfigured ? 'Unknown' : 'Not configured'}</strong><small>{waterStoreConfigured || numeric(atBoundary?.water_remaining_l) ? 'Finite modeled store at end of day' : 'Daily water allowance still applies'}</small></div>
        <div><span>Remaining electricity store</span><strong>{numeric(atBoundary?.energy_remaining_kwh) ? format(atBoundary.energy_remaining_kwh) + ' kWh' : energyStoreConfigured ? 'Unknown' : 'Not configured'}</strong><small>{energyStoreConfigured || numeric(atBoundary?.energy_remaining_kwh) ? 'Finite modeled store at end of day' : 'Daily electricity allowance still applies'}</small></div>
      </div>
      {!run?.metadata && <p className="notice">Run a mission simulation first to establish remaining food and growing crops.</p>}
      {day < lastCompleted && <p className="notice warning">Choose Day {lastCompleted} or later. A previous continuation already preserved history through that day.</p>}
      <div className="mission-change-roster-heading"><div><h3>Future crew roster</h3><p>{profiles.length} crew from Day {nextDay} · editable planning targets for each person</p></div><button className="btn" type="button" disabled={disabled || profiles.length >= 12} onClick={addCrew}><Plus size={15}/> Add crew member</button></div>
      <div className="table-wrap mission-change-roster"><table aria-label="Future crew roster and daily planning targets"><thead><tr><th>Crew member</th>{tracked.map(key => <th key={key}>{labels[key]}<small>{units[key]}</small></th>)}<th/></tr></thead><tbody>{profiles.map(profile => <tr key={profile.profile_id}><td><input className="mission-change-name" aria-label={'Name for ' + profile.profile_id} type="text" maxLength={80} value={profile.name} disabled={disabled} onChange={event => updateProfile(profile.profile_id, 'name', event.target.value)}/></td>{tracked.map(key => <td key={key}><input aria-label={labels[key] + ' target for ' + profile.name} type="number" min="0.01" step="any" value={profile.targets[key] ?? ''} disabled={disabled} onChange={event => updateProfile(profile.profile_id, key, event.target.value === '' ? '' : Number(event.target.value))}/></td>)}<td><button className="text-button" type="button" aria-label={'Remove ' + profile.name + ' from future crew'} disabled={disabled || profiles.length <= 1} onClick={() => edit(() => setProfiles(previous => previous.filter(item => item.profile_id !== profile.profile_id)))}>Remove</button></td></tr>)}</tbody></table></div>
      <p className="mission-change-small">Sample names and targets are fictional examples. Review the targets for planning. Blood-test examples, ferritin and photos do not set nutrient requirements. Iron is not tracked in this planner.</p>
      {pendingCrewChanges.length > 0 && <div className="mission-change-scheduled"><strong>Saved future crew changes</strong><ul>{pendingCrewChanges.map((change, index) => <li key={change.day + '-' + index}>Day {change.day}: {change.label}</li>)}</ul><label className="check-label"><input type="checkbox" checked={replaceFutureCrew} disabled={disabled} onChange={event => edit(() => setReplaceFutureCrew(event.target.checked))}/>Replace scheduled future crew changes</label><p className="mission-change-small">{replaceFutureCrew ? 'This roster stays in effect until you change it again. Existing future crew arrivals will be removed; resource changes and nutrient-only scenarios remain.' : 'Saved future crew changes remain scheduled and can change the roster again on the dates above.'}</p></div>}
      <TargetPreview before={before} after={after} fromDay={nextDay}/>
      <details className="mission-change-resources"><summary>Change future resource allowances</summary><p>Enter the total available allowance, including crew use. These values apply from Day {nextDay}; changing a daily allowance does not replenish a finite store or add food.</p><div className="mission-change-resource-inputs">{budgets.map(field => <div key={field.key}><label className="check-label"><input type="checkbox" checked={!!enabled[field.key]} disabled={disabled} onChange={event => edit(() => setEnabled(previous => ({...previous, [field.key]: event.target.checked})))}/>Change {field.label.toLowerCase()}</label><label className="field"><span>{field.label} ({field.unit})</span><input type="number" min="0" max={field.max} step="any" disabled={disabled || !enabled[field.key]} value={values[field.key] ?? resourceDefaults[field.key] ?? ''} onChange={event => edit(() => setValues(previous => ({...previous, [field.key]: event.target.value === '' ? '' : Number(event.target.value)})))}/></label></div>)}</div></details>
      <label className="field mission-change-reason"><span>Reason for the change (optional)</span><input type="text" maxLength={240} placeholder="For example: a fifth crew member arrives tomorrow" value={reason} disabled={disabled} onChange={event => edit(() => setReason(event.target.value))}/></label>
      <label className="check-label mission-change-review"><input type="checkbox" checked={reviewed} disabled={disabled} onChange={event => {revision.current++; setReviewed(event.target.checked); setError('');}}/>Reviewed planning targets for this change</label>
      <div className="mission-change-submit"><button className="btn primary" type="submit" disabled={disabled || !run?.metadata || !setRun || day >= horizon || day < lastCompleted}>{busy ? 'Replanning the remaining mission…' : 'Apply change & replan from Day ' + nextDay}<ArrowRight size={16}/></button><span>The solver chooses future planting and meals. A new crop supplies food only after its modeled harvest.</span></div>
      {busy && <p className="muted" role="status">Carrying saved food and growing batches into the next day, then testing future planting and meal allocations against the revised targets and limits…</p>}
      {error && <p className="notice warning" role="alert">{error}</p>}
    </form>
    {acceptedDetails && <section className="mission-change-result" aria-label="Accepted mission change"><h3>Future plan updated from Day {acceptedDetails.next_day}</h3><p>History through Day {acceptedDetails.through_day} is preserved. Food starts from saved closing stock and active crop batches are carried forward.</p><dl><div><dt>First future tracked nutrient gap</dt><dd>{firstGap ? 'Day ' + firstGap.day : 'None in this modeled plan'}</dd></div><div><dt>Future days with tracked nutrient gaps</dt><dd>{acceptedFuture.filter(row => row.shortfall_normalized > 1e-6).length}</dd></div><div><dt>Next modeled harvest</dt><dd>{harvests.length ? 'Day ' + harvests[0].harvest_day + ' · ' + harvests[0].crop : 'No future harvest scheduled'}</dd></div></dl><p className="mission-change-small">Crop recommendations in Crops & food use this updated plan, remaining mission days and future nutritional gaps. If resources cannot meet the targets, shortages remain visible.</p></section>}
  </section>;
}
