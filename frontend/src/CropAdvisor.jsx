import React, {useEffect, useRef, useState} from 'react';
import {ArrowRight, Check, Sprout} from 'lucide-react';
import {loadBioProductionScenario} from './bio-production-scenario.js';
import './crop-advisor.css';

const nutrients = ['protein', 'vitamin_c', 'energy'];
const labels = {balanced: 'Balanced nutrition', protein: 'Protein', vitamin_c: 'Vitamin C', energy: 'Energy'};
const units = {protein: 'g', vitamin_c: 'mg', energy: 'kcal'};
const number = value => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString(undefined, {maximumFractionDigits: 2}) : 'Unavailable';
const measure = (value, unit) => number(value) + (typeof value === 'number' && Number.isFinite(value) ? ' ' + unit : '');
const safeSource = url => typeof url === 'string' && /^https?:\/\//i.test(url);

function Source({provenance = {}}) {
  const composition = provenance.composition || {};
  const name = composition.status === 'usda_reference_proxy'
    ? 'USDA reference' : 'Configured composition';
  return <div className="crop-advisor-sources">
    <span>{safeSource(composition.source_url)
      ? <a href={composition.source_url} target="_blank" rel="noreferrer">{name}{composition.fdc_id ? ' · FDC ' + composition.fdc_id : ''}</a>
      : name}{composition.food_form ? ' · ' + composition.food_form : ''}</span>
    {composition.detail && <span>{composition.detail}</span>}
    {provenance.growth?.detail && <span>Growth: {provenance.growth.detail}</span>}
    {provenance.resources?.detail && <span>Resources: {provenance.resources.detail}</span>}
  </div>;
}

function CropDetail({crop, area}) {
  return <section className="crop-advisor-detail" aria-label={'Crop details for ' + crop.name}>
    <div className="crop-advisor-detail-heading"><h3>{crop.name}</h3>
      <span className={'crop-advisor-state' + (crop.actionable ? '' : ' blocked')}>{crop.actionable ? 'Fits modeled limits' : 'Blocked under these assumptions'}</span>
    </div>
    {!!crop.blocked_reasons?.length && <ul className="crop-advisor-blockers">{crop.blocked_reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
    <div className="crop-advisor-output">
      <div><span>Estimated edible harvest</span><strong>{measure(crop.estimated_harvest_kg, 'kg')}</strong><small>For {number(area)} m² · Day {crop.harvest_day ?? 'unavailable'}</small></div>
      {nutrients.map(nutrient => <div key={nutrient}><span>{labels[nutrient]} in that harvest</span><strong>{measure(crop.nutrients_at_harvest?.[nutrient], units[nutrient])}</strong><small>{crop.provenance?.composition?.status === 'usda_reference_proxy' ? 'USDA reference composition' : 'Configured composition'} × modeled mass</small></div>)}
    </div>
    <div className="crop-advisor-detail-columns">
      <div><h4>Nutrition per 100 g</h4><dl>{nutrients.map(nutrient => <div key={nutrient}><dt>{labels[nutrient]}</dt><dd>{measure(crop.nutrients_per_100g?.[nutrient], units[nutrient])}</dd></div>)}</dl>
        <p>Food density helps compare servings. Harvest size, growing time and available resources determine what this batch can supply.</p>
        <h4>Nutrient output per m² per growing day</h4><dl>{nutrients.map(nutrient => <div key={nutrient}><dt>{labels[nutrient]}</dt><dd>{measure(crop.nutrient_output_per_m2_day?.[nutrient], units[nutrient] + '/m²/day')}</dd></div>)}</dl>
      </div>
      <div><h4>Added batch resource needs</h4><dl>
        <div><dt>Growth duration</dt><dd>{measure(crop.grow_days, 'days')}</dd></div>
        <div><dt>Water each growing day</dt><dd>{measure(crop.resources?.required_daily_water_l, 'L/day')}</dd></div>
        <div><dt>Electricity each growing day</dt><dd>{measure(crop.resources?.required_daily_power_kwh, 'kWh/day')}</dd></div>
        <div><dt>Water over crop cycle</dt><dd>{measure(crop.resources?.cycle_water_l, 'L')}</dd></div>
        <div><dt>Electricity over crop cycle</dt><dd>{measure(crop.resources?.cycle_power_kwh, 'kWh')}</dd></div>
        <div><dt>Lowest remaining area in cycle</dt><dd>{measure(crop.resources?.min_available_area_m2_in_cycle, 'm²')}</dd></div>
        <div><dt>Lowest remaining water in cycle</dt><dd>{measure(crop.resources?.min_available_water_l_in_cycle, 'L/day')}</dd></div>
        <div><dt>Lowest remaining electricity in cycle</dt><dd>{measure(crop.resources?.min_available_power_kwh_in_cycle, 'kWh/day')}</dd></div>
      </dl></div>
    </div>
    {Object.values(crop.gaps_before_harvest || {}).some(value => value > 1e-6) && <p className="crop-advisor-before-harvest">Before this crop's harvest, the saved plan has cumulative shortages of {nutrients.filter(nutrient => crop.gaps_before_harvest?.[nutrient] > 1e-6).map(nutrient => measure(crop.gaps_before_harvest[nutrient], units[nutrient]) + ' ' + labels[nutrient].toLowerCase()).join('; ')}. Those days need another food source.</p>}
    {crop.harvest_day_fresh_limit_kg != null && <p className="crop-advisor-consumption-limit">Configured total fresh-food limit on harvest day: {measure(crop.harvest_day_fresh_limit_kg, 'kg')} for the crew. All crops harvested that day share this limit.</p>}
    {crop.credited_nutrient_gap_reduction && <div className="crop-advisor-timed-help"><h4>Useful help on Day {crop.harvest_day}</h4><p>Credit is limited to the gap and unused meal capacity on the actual harvest day. The full harvest is not guaranteed intake.</p><dl>{nutrients.map(nutrient=><div key={nutrient}><dt>{labels[nutrient]} gap reduced</dt><dd>{measure(crop.credited_nutrient_gap_reduction[nutrient],units[nutrient])}</dd></div>)}</dl><p>Estimated extra harvest the crew can consume that day: {measure(crop.consumable_harvest_kg,'kg')}.</p></div>}
    <Source provenance={crop.provenance}/>
    {!!crop.warnings?.length && <details className="crop-advisor-notes"><summary>Crop assumptions</summary>{crop.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</details>}
  </section>;
}

function CrewResponse({plan}) {
  if (!plan) return null;
  const alerts = plan.health_alerts || [], support = plan.immediate_support || [], options = plan.production_options || [];
  const sampleOnly = plan.scope?.sample_only;
  const readyOptions = options.filter(option => option.first_harvest_day != null);
  const pendingOptions = options.filter(option => option.first_harvest_day == null);
  const unmatched = plan.scope?.unmatched_crew_names || [];
  return <section className="crop-advisor-response" aria-labelledby="crew-response-title">
    <div className="crop-advisor-response-heading"><div><span className="eyebrow">SUPPORT NOW · PRODUCE FOR LATER</span><h3 id="crew-response-title">Crew health and food response</h3></div>{sampleOnly && <span className="source-pill">Sample crew records</span>}</div>
    {!!alerts.length && <div className="crop-advisor-health-alerts" aria-label="Crew health alerts">{alerts.map((alert, index)=><article key={(alert.profile_id || 'crew')+'-'+alert.kind+'-'+index} className={'crop-advisor-health-alert '+(alert.severity || '')}><div><strong>{alert.name || 'Crew member'}</strong><span>{alert.sample_only ? 'Sample record' : 'Recorded observation'}{alert.day != null ? ' · Day '+alert.day : ''}</span></div><p>{alert.message}</p></article>)}</div>}
    {!!unmatched.length && <div className="notice warning"><strong>Connect the crew roster to this mission</strong><p>{unmatched.join(', ')} have records in Crew & nutrition but are not matched to the accepted mission roster. Review and apply that roster to enable their health and food response here.</p><a href="#crew">Review crew & nutrition →</a></div>}
    {!alerts.length && <p className="crop-advisor-record-scope">{unmatched.length || plan.scope?.matched_crew_count === 0 ? 'Individual health checks are waiting for a matched mission roster.' : 'No flagged comparison in the matched records. This does not confirm that everyone is healthy.'}</p>}
    {!!support.length && <><h4 className="crop-advisor-support-title">Available support before harvest</h4><div className="crop-advisor-support" aria-label="Immediate support">{support.map((item,index)=><article key={item.kind+'-'+index}><h4>{item.title}</h4>{item.stock_kg != null && <strong className="crop-advisor-stock">{measure(item.stock_kg,'kg')} in modeled stock</strong>}<p>{item.message}</p>{item.kind === 'stored_food' && item.nutrients && <small>{nutrients.filter(n=>item.nutrients[n]!=null).map(n=>measure(item.nutrients[n],units[n])+' '+labels[n].toLowerCase()).join(' · ')} in that stock; shared mission inventory.</small>}</article>)}</div></>}
    {!!plan.crew_intake?.length && <details className="crop-advisor-notes"><summary>Recorded crew intake today</summary><p>Complete logs use the accepted mission targets. Partial or missing logs cannot establish a daily shortage.</p><div className="table-wrap"><table aria-label="Current crew intake"><thead><tr><th>Member</th><th>Nutrient</th><th>Logged intake</th><th>Accepted target</th><th>Daily gap</th></tr></thead><tbody>{plan.crew_intake.map(row=><tr key={row.profile_id+'-'+row.nutrient}><td>{row.person}</td><td>{labels[row.nutrient]}</td><td>{measure(row.intake,row.unit)}</td><td>{measure(row.target,row.unit)}</td><td>{row.usable_for_response ? measure(row.gap,row.unit) : 'Incomplete / unknown'}</td></tr>)}</tbody></table></div></details>}
    {!!plan.scope?.pending_target_profile_ids?.length && <p className="notice warning">Crew target edits are pending. Apply them to the mission plan to update production suggestions.</p>}
    {!!options.length && <div className="crop-advisor-production-options"><h4>Biological production to consider</h4><p>Growing is a future food option. It cannot replace support needed today.</p>{!!readyOptions.length && <div className="table-wrap"><table aria-label="Biological production recommendations"><thead><tr><th>Organism / module</th><th>First harvest</th><th>Protein at first harvest</th><th>Modeled protein total</th><th>Constraints</th></tr></thead><tbody>{readyOptions.map((option,index)=><tr key={(option.id || option.profile_id || 'option')+'-'+index}><td><strong>{option.name}</strong><small>{String(option.status || 'review').replaceAll('_',' ')}</small></td><td>Day {option.first_harvest_day}</td><td>{measure(option.first_harvest_protein_g,'g')}</td><td>{measure(option.protein_g,'g')}</td><td>{option.reasons?.length ? option.reasons.join(' ') : 'Projected output; food qualification and actual intake remain unestablished.'}</td></tr>)}</tbody></table></div>}{!!pendingOptions.length && <div className="crop-advisor-production-setup"><h4>{readyOptions.length ? 'Other modules need setup' : 'Set up a production comparison'}</h4><p>{pendingOptions.map(option=>option.name).join(' · ')}</p><p>Harvest dates and nutrient output need a saved scenario with module capacity, startup time, water, power and medium supply. The projection then checks the remaining mission resources.</p><a className="text-button" href="#production">Review biological production →</a><details><summary>What is missing?</summary>{pendingOptions.map((option,index)=><p key={index}><strong>{option.name}: </strong>{option.reasons?.join(' ') || 'Review the production inputs.'}</p>)}</details></div>}</div>}
    <details className="crop-advisor-notes"><summary>Health record coverage and limits</summary>{!!plan.scope?.missing_metrics?.length && <p>Missing measurements: {plan.scope.missing_metrics.map(metric=>typeof metric==='string'?metric:metric.name || metric.metric || 'Unspecified measurement').join(', ')}.</p>}{(plan.scope?.limitations || []).map((text,index)=><p key={index}>{text}</p>)}<p>Heart rate and blood pressure alone cannot determine a nutrient deficiency. Supplement decisions need a clinician’s assessment and an approved supply.</p></details>
  </section>;
}

export default function CropAdvisor({config, setConfig, run, missionDay = 1, setMissionDay, setRun, request, notify = () => {}, showContinuation = true, crewState, biologicalScenario}) {
  const [automatic, setAutomatic] = useState(true);
  const [priority, setPriority] = useState('balanced');
  const [area, setArea] = useState(() => Math.min(1, Number((run?.metadata?.config || config)?.area_m2) || 1));
  const [targetChange, setTargetChange] = useState(0);
  const [report, setReport] = useState(null);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const version = useRef(0);
  const planningConfig = run?.metadata?.config || config;
  const horizon = Number(planningConfig?.days) || 1;
  const [deadline,setDeadline] = useState(horizon);
  const day = Math.max(1, Math.min(horizon, Number(missionDay) || 1));
  const harvestDeadline = Math.max(day,Math.min(horizon,deadline));
  const lastCompleted = Number(run?.metadata?.continuation?.through_day) || 0;
  const pastBoundary = day < lastCompleted;
  const reviewedBiologicalScenario = biologicalScenario === undefined ? loadBioProductionScenario(run) : biologicalScenario;
  const contextKey = JSON.stringify([config, run?.history_id, run?.metadata, day, crewState, reviewedBiologicalScenario, automatic, ...(automatic ? [] : [priority, area, harvestDeadline])]);
  useEffect(()=>setDeadline(horizon),[horizon,run?.history_id]);
  const activeContext = useRef(contextKey);
  activeContext.current = contextKey;
  useEffect(()=>{const advice=run?.metadata?.planning_advice;if(advice){setArea(advice.area_m2);setPriority(advice.priority);}},[run?.history_id,run?.metadata?.created_at_utc]);
  useEffect(() => {
    version.current++;
    setReport(null); setSelectedId(''); setError(''); setBusy('');
    if (automatic && planningConfig) void calculate();
  }, [contextKey]);
  useEffect(() => () => {version.current++;}, []);

  function invalidate() {
    version.current++;
    setReport(null); setSelectedId(''); setError(''); setBusy('');
  }
  const current = (token, context) => version.current === token && activeContext.current === context;

  async function calculate(event) {
    event?.preventDefault();
    if (!automatic && (!(area > 0) || !Number.isFinite(area))) {setError('Enter a positive planting area.'); return;}
    const token = ++version.current, context = contextKey;
    setBusy('recommend'); setError(''); setReport(null);
    try {
      const response = await request('/crop-advisor', {metadata: run?.metadata, config: planningConfig, day, automatic,
        ...(crewState ? {crew_state: crewState} : {}), ...(reviewedBiologicalScenario ? {biological_scenario: reviewedBiologicalScenario} : {}),
        ...(!automatic ? {priority, area_m2: area, deadline_day: harvestDeadline} : {})});
      if (!current(token, context)) return;
      if (!Array.isArray(response.recommendations)) throw new Error('Crop recommendations are unavailable. Review the planning inputs.');
      setReport(response);
      setSelectedId(response.top_choice_crop_id || response.recommendations[0]?.crop_id || '');
    } catch (failure) {
      if (current(token, context)) {setError(failure.message || 'Crop recommendations could not be calculated.'); notify(failure.message || 'Crop recommendations could not be calculated.', true);}
    } finally {if (current(token, context)) setBusy('');}
  }

  async function continuePlan() {
    if (!run?.metadata || day >= horizon || pastBoundary || !setRun) return;
    if (priority !== 'balanced' && (!Number.isFinite(targetChange) || targetChange < -90 || targetChange > 100)) {
      setError('Enter a target change between −90% and 100%.'); return;
    }
    const token = ++version.current, context = contextKey;
    setBusy('continue'); setError('');
    try {
      const result = await request('/plans/continue', {metadata: run.metadata, through_day: day,
        target_factors: priority === 'balanced' || targetChange === 0 ? {} : {[priority]: 1 + targetChange / 100}});
      if (!current(token, context)) return;
      if (!result.metadata?.adaptive?.daily?.length) throw new Error('Continuation did not return a usable mission plan. The saved plan is still available.');
      setRun(result);
      setTargetChange(0);
      setReport(null);
      notify(result.history_warning || 'Plan continued from Day ' + day + '. Earlier mission days are preserved.', !!result.history_warning);
    } catch (failure) {
      if (current(token, context)) {setError(failure.message || 'The mission plan could not be continued.'); notify(failure.message || 'The mission plan could not be continued.', true);}
    } finally {if (current(token, context)) setBusy('');}
  }

  async function loadCropNutrition() {
    if (!setConfig) return;
    const token = ++version.current, context = contextKey;
    setBusy('sources'); setError('');
    try {
      const result = await request('/config/crop-nutrition', {config});
      if (!current(token, context)) return;
      if (!result.config) throw new Error('Crop nutrition references did not return a usable configuration.');
      setReport(null); setSelectedId('');
      setConfig(result.config);
      notify('USDA crop nutrition applied to ' + (result.matched_crop_ids?.length || 0) + ' crop profiles. ' + (result.unmatched_crop_ids?.length || 0) + ' unmatched profiles retain their configured assumptions. Run a new simulation to update the forecast.');
    } catch (failure) {
      if (current(token, context)) {setError(failure.message || 'Crop nutrition references could not be applied.'); notify(failure.message || 'Crop nutrition references could not be applied.', true);}
    } finally {if (current(token, context)) setBusy('');}
  }

  const selected = report?.recommendations.find(crop => crop.crop_id === selectedId);
  const top = report?.recommendations.find(crop => crop.crop_id === report.top_choice_crop_id);
  const gapRows = report?.forecast?.nutrients || [];
  const bridgeFoods = report?.bridge_foods || [];
  return <section className="crop-advisor" aria-labelledby="crop-advisor-title">
    <div className="crop-advisor-heading"><div><span className="eyebrow"><Sprout size={15}/> CREW → NUTRITION → PRODUCTION</span><h2 id="crop-advisor-title">Crew-driven food recommendations</h2><p>Recommendations update from the crew’s reviewed needs, health records, remaining resources and time to harvest.</p></div><span className="source-pill">{automatic ? 'Updates automatically' : 'Custom comparison'}</span></div>
    <div className="crop-advisor-context" aria-label="Recommendation context"><span><strong>Day {day}</strong> of {horizon}</span><span><strong>{horizon - day}</strong> days after today</span><span>{run?.metadata ? 'Saved simulation and remaining resources' : 'Current configuration · no saved simulation'}</span></div>
    <details className="crop-advisor-advanced"><summary>Advanced comparison</summary><label className="crop-advisor-mode"><input type="checkbox" checked={!automatic} onChange={event=>{invalidate();setAutomatic(!event.target.checked);setTargetChange(0);}}/> Use custom nutrient priority, area and deadline</label>
    {!automatic && <form className="crop-advisor-form" onSubmit={calculate}>
      <div className="crop-advisor-controls">
        <label className="field"><span>Nutrient priority</span><select value={priority} onChange={event => {invalidate(); setPriority(event.target.value);}}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label className="field"><span>Assumed planting area (m²)</span><input type="number" min="0.01" max="10000" step="0.01" value={area} onChange={event => {invalidate(); setArea(event.target.value === '' ? '' : Number(event.target.value));}}/></label>
        <label className="field"><span>Simulated mission day</span><input type="number" min="1" max={horizon} step="1" value={day} disabled={!setMissionDay} onChange={event => {const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= horizon) {invalidate(); setMissionDay?.(value);}}}/></label>
        <label className="field"><span>Harvest deadline (mission day)</span><input type="number" min={day} max={horizon} step="1" value={harvestDeadline} onChange={event=>{const value=Number(event.target.value);if(Number.isInteger(value)&&value>=day&&value<=horizon){invalidate();setDeadline(value);}}}/></label>
      </div>
      <div className="crop-advisor-action"><button className="btn primary" type="submit" disabled={!!busy}>{busy === 'recommend' ? 'Comparing crops…' : 'Compare custom inputs'}<ArrowRight size={16}/></button><span>Health alerts continue to use the crew records.</span></div>
    </form>}
    </details>
    {setConfig && <details className="crop-advisor-data"><summary>Crop nutrition data</summary><p>Recommendations use the loaded crop coefficients. Apply USDA edible-food references to matched crops for reference-based comparisons. Unmatched crops retain their labeled assumptions; crop growth, resources and stored-food inputs stay as configured. This resets the current comparison and requires a new simulation.</p><button className="btn" type="button" disabled={!!busy} onClick={loadCropNutrition}>{busy === 'sources' ? 'Applying crop references…' : 'Use USDA crop nutrition'}</button></details>}
    {busy && <p role="status" className="muted">{busy === 'continue' ? 'Keeping simulated history and replanning the future…' : busy === 'sources' ? 'Matching configured crop profiles to USDA food forms…' : 'Reviewing crew needs, food options and time to harvest…'}</p>}
    {error && <div role="alert" className="notice warning"><p>{error}</p>{automatic && <button type="button" className="text-button" disabled={!!busy} onClick={()=>calculate()}>Retry recommendations</button>}</div>}
    {report && <div className="crop-advisor-results" aria-live="polite">
      <CrewResponse plan={report.response_plan}/>
      {report.crew_context&&<p className="crop-advisor-basis">Planning for {report.crew_context.members?.map(profile=>profile.name).join(', ')||'the recorded crew count'}{report.crew_context.unnamed_count>0?' · '+report.crew_context.unnamed_count+' unnamed positions':''}. Harvest deadline: Day {report.deadline_day} · {report.remaining_days} days in this growing window. Crew needs can change on later dated events.</p>}
      {!!report.planned_crop_actions?.length && <section className="crop-advisor-selected-plan" aria-labelledby="selected-crop-plan-title"><span className="eyebrow">ALREADY SELECTED BY THE REVISED SOLVER</span><h3 id="selected-crop-plan-title">Crops for the remaining mission</h3><p>These batches belong to the saved resource-constrained plan. Their dates reflect crew demand, existing food and the time left to harvest. Nutrient output below is potential harvest composition; meals may use less.</p><div className="table-wrap"><table aria-label="Selected crops for the remaining mission"><thead><tr><th>Crop</th><th>Plant → harvest</th><th>Area</th><th>Estimated edible harvest</th><th>Protein in harvest</th><th>Vitamin C in harvest</th></tr></thead><tbody>{report.planned_crop_actions.slice(0,12).map((action,index)=><tr key={action.crop_id+'-'+action.day+'-'+index}><td>{action.name}</td><td>Day {action.day} → {action.harvest_day}</td><td>{measure(action.area_m2,'m²')}</td><td>{measure(action.predicted_harvest_kg,'kg')}</td><td>{measure(action.nutrients_at_harvest?.protein,'g')}</td><td>{measure(action.nutrients_at_harvest?.vitamin_c,'mg')}</td></tr>)}</tbody></table></div>{report.planned_crop_actions.length>12 && <p className="muted">First 12 future batches shown; the complete schedule is below.</p>}</section>}
      <div className="crop-advisor-recommendation"><span className="eyebrow">{top ? 'ADDITIONAL CROP TO CONSIDER' : 'ADDITIONAL CROP COMPARISON'}</span><h3>{top ? top.name : report.selection_reason?.type==='no_timely_gap_help' ? 'Extra batches cannot help these gaps in time' : report.selection_reason?.type==='no_crops' ? 'No crops configured' : 'No additional batch fits the modeled limits'}</h3><p>{report.selection_reason?.text || (top ? 'Highest-ranked feasible batch for ' + labels[priority].toLowerCase() + ' at Day ' + report.day + '. Review harvest timing and food needed before it is ready.' : 'Review each crop’s timing and resource constraints below. Continue planning to evaluate a different crop mix under your reviewed targets.')}</p></div>
      <p className="crop-advisor-basis">{report.weight_basis || 'Rankings compare modeled nutrient output per growing area and day.'} One proposed batch is evaluated at a time; combinations need the mission solver.</p>
      {report.automatic && report.area_basis && <p className="crop-advisor-basis">{report.area_basis}</p>}
      {report.recommendations.length > 0 ? <div className="crop-advisor-comparison table-wrap"><table aria-label="Crop recommendation comparison"><thead><tr><th>Rank / crop</th><th>Protein per 100 g</th><th>Vitamin C per 100 g</th><th>Energy per 100 g</th><th>Harvest timing</th><th>Estimated harvest</th><th>Limits</th><th/></tr></thead><tbody>{report.recommendations.map(crop => <tr key={crop.crop_id} className={selectedId === crop.crop_id ? 'selected' : ''}>
        <td><span className="crop-advisor-crop-name"><span>{crop.rank ?? '—'}</span><strong>{crop.name}</strong></span></td>
        {nutrients.map(nutrient => <td key={nutrient}>{measure(crop.nutrients_per_100g?.[nutrient], units[nutrient])}</td>)}
        <td>Day {crop.harvest_day ?? 'unavailable'}<small>{measure(crop.grow_days, 'growing days')}</small></td><td>{measure(crop.estimated_harvest_kg, 'kg')}</td>
        <td>{crop.actionable ? <span className="crop-advisor-fits"><Check size={14}/> Fits</span> : <span className="crop-advisor-blocked">Blocked</span>}</td>
        <td><button className="text-button" type="button" aria-label={'Review ' + crop.name} aria-pressed={selectedId === crop.crop_id} onClick={() => setSelectedId(crop.crop_id)}>Review</button></td>
      </tr>)}</tbody></table></div> : <p>No crops are configured. Add crop profiles to compare their nutrient output.</p>}
      {selected && <CropDetail crop={selected} area={selected.resources?.required_area_m2 ?? report.area_m2}/>}
      <section className="crop-advisor-gaps" aria-labelledby="crop-advisor-gaps-title"><h3 id="crop-advisor-gaps-title">Can the crew wait for harvest?</h3>
        {report.forecast?.available ? <><p>These are intake gaps in the saved simulated plan. A crop planted now supplies no food before its harvest.</p><div className="table-wrap"><table aria-label="Predicted nutrient gaps"><thead><tr><th>Nutrient</th><th>Supply on Day {report.day}</th><th>Crew target that day</th><th>First future gap</th><th>Future gap days</th></tr></thead><tbody>{gapRows.map(row => <tr key={row.nutrient}><td>{labels[row.nutrient] || row.nutrient}</td><td>{measure(row.current_supply, row.unit || units[row.nutrient])}</td><td>{measure(row.current_target, row.unit || units[row.nutrient])}</td><td>{row.earliest_gap_day != null ? 'Day ' + row.earliest_gap_day : 'None in saved plan'}</td><td>{number(row.gap_days)}</td></tr>)}</tbody></table></div></> : <p>Run a mission simulation to inspect predicted nutrient gaps and remaining stored food.</p>}
        {bridgeFoods.length > 0 && <><h4>Stored food to consider before harvest</h4><p>Remaining stock can bridge a delay. This comparison does not allocate a meal or prove that all dietary targets can be met.</p><div className="table-wrap"><table aria-label="Food available before harvest"><thead><tr><th>Food / form</th><th>Remaining stock</th><th>Protein per 100 g now</th><th>Vitamin C per 100 g now</th><th>Energy per 100 g now</th><th>Status</th></tr></thead><tbody>{bridgeFoods.map(food => <tr key={food.food_id}><td>{food.name}<small>{food.provenance?.food_form || food.provenance?.composition?.food_form || 'Configured food form'}</small></td><td>{measure(food.stock_kg, 'kg')}<small>{food.stock_source}</small></td>{nutrients.map(nutrient => <td key={nutrient}>{measure(food.current_nutrients_per_100g?.[nutrient], units[nutrient])}{food.available && food.available_nutrients_in_stock?.[nutrient] != null && <small>{measure(food.available_nutrients_in_stock[nutrient], units[nutrient])} in remaining stock</small>}</td>)}<td>{food.expired ? 'Expired' : food.available ? food.is_reserve ? 'Reserve eligible' : 'Available' : 'Unavailable'}</td></tr>)}</tbody></table></div></>}
      </section>
      <details className="crop-advisor-notes"><summary>Data sources and calculation limits</summary>{report.scoring_basis && <p>{report.scoring_basis}</p>}{(report.limitations || []).map((limitation, i) => <p key={i}>{limitation}</p>)}<p>Photos and fruit counts do not supply measured crop mass or nutrient composition to this calculation. Only the three listed nutrients are tracked.</p></details>
    </div>}
    {showContinuation && <section className="crop-advisor-continue" aria-labelledby="crop-advisor-continue-title"><div><span className="eyebrow">KEEP THE MISSION MOVING</span><h3 id="crop-advisor-continue-title">Continue with updated needs</h3><p>{day >= horizon ? 'All days in this mission have been explored. Extend the mission horizon in the setup and run a new simulation to plan further.' : <>Keep simulated stock, growing batches and days 1–{day}. Recalculate future planting and meals from Day {day + 1} using the remaining resources.</>}</p><p className="crop-advisor-scope">The solver chooses the crop mix. The comparison above does not force a crop into the plan. History is simulated, not a confirmed harvest or image measurement.</p></div>
      <div className="crop-advisor-continue-action">{priority !== 'balanced' && <label className="field"><span>{labels[priority]} target change from next day (%)</span><input type="number" min="-90" max="100" step="1" value={targetChange} disabled={!!busy || day >= horizon} onChange={event => {invalidate(); setTargetChange(Number(event.target.value));}}/></label>}
        <button className="btn" type="button" disabled={!!busy || !run?.metadata || !setRun || day >= horizon || pastBoundary} onClick={continuePlan}>{busy === 'continue' ? 'Continuing plan…' : 'Continue from Day ' + day}<ArrowRight size={16}/></button>
        <small>{pastBoundary ? 'Choose Day ' + lastCompleted + ' or later to preserve completed simulation history.' : day >= horizon ? 'Mission horizon reached; there are no future days to replan.' : !run?.metadata ? 'Run a mission simulation first.' : priority === 'balanced' || targetChange === 0 ? 'Keeps current nutrient targets.' : labels[priority] + ' target becomes ' + number(100 + targetChange) + '% of its current value from the next day.'}</small>
      </div>
    </section>}
  </section>;
}
