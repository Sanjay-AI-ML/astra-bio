import React, {useEffect, useRef, useState} from 'react';
import './recovery.css';

const number = value => typeof value === 'number' && Number.isFinite(value)
  ? new Intl.NumberFormat(undefined, {maximumFractionDigits: 3}).format(value) : 'Unavailable';
const units = {food: 'kg', water: 'L/day', power: 'kWh/day'};
const titles = {food: 'Stored food', water: 'Daily water', power: 'Daily electricity'};
const amount = candidate => candidate.resources.minimum_proven ? candidate.resources.primary_minimum : candidate.resources.feasible_resource_amount;
const defaults = {food_limit_kg: 1000, water_limit_l_per_day: 100, power_limit_kwh_per_day: 20,
  include_reserve: false, lower_yield_factor: .8, harvest_delay_days: 3};

function saveReport(report) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'astra-bio-recovery.json'; anchor.click(); URL.revokeObjectURL(url);
}

function addition(candidate) {
  if (candidate.id === 'replan') return 'No additional resources';
  if (!candidate.summary.available) return candidate.status === 'infeasible' ? 'No feasible result within limit' : 'Calculation unavailable';
  if (candidate.resources.not_needed) return 'No addition needed';
  return number(amount(candidate)) + ' ' + units[candidate.id] +
    (candidate.resources.minimum_proven ? ' · minimum proven' : ' · feasible, minimum unproven');
}

export default function RecoveryPanel({run, request, planningBusy = false, exportReport = saveReport}) {
  const [options, setOptions] = useState(defaults), [report, setReport] = useState(null);
  const [selectedId, setSelectedId] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const revision = useRef(0);
  const runKey = JSON.stringify([run.history_id, run.metadata.created_at_utc, run.metadata.config, run.metadata.scenario, run.metadata.continuation]);
  useEffect(() => {revision.current++; setReport(null); setError(''); setBusy(false); setSelectedId('');}, [runKey]);
  useEffect(() => () => {revision.current++;}, []);

  function change(key, value) {
    revision.current++;
    setOptions(previous => ({...previous, [key]: value})); setReport(null); setError(''); setBusy(false);
  }
  async function analyze(event) {
    event.preventDefault();
    const token = ++revision.current;
    setBusy(true); setError(''); setReport(null);
    try {
      const response = await request('/recovery', {run_id: run.history_id || null,
        ...(!run.history_id ? {metadata:run.metadata} : {}), config: run.metadata.config, scenario: run.metadata.scenario, options});
      if (revision.current !== token) return;
      if (response.status !== 'calculated' || !Array.isArray(response.candidates)) {
        throw new Error(response.warnings?.join(' ') || 'Recovery analysis could not produce a plan. Review the submitted inputs.');
      }
      setReport(response); setSelectedId(response.recommended_candidate_id || response.candidates.find(c => c.summary.available)?.id || '');
    } catch (error) {
      if (revision.current === token) setError(error.message || 'Recovery analysis failed.');
    } finally {if (revision.current === token) setBusy(false);}
  }
  const selected = report?.candidates.find(candidate => candidate.id === selectedId);
  const ranked = report?.candidates.filter(candidate => !candidate.resources.not_needed) || [];
  const anyFeasible = report?.candidates.some(candidate => candidate.summary.meets_targets);
  const foodNames = Object.fromEntries(run.metadata.config.foods.map(food => [food.id, food.name]));
  const day = run.metadata.continuation?.next_day || run.metadata.scenario.event_day;
  return <section className="recovery-panel" aria-labelledby="recovery-title">
    <div className="section-heading"><div><span className="eyebrow">DISRUPTION RECOVERY</span><h2 id="recovery-title">Compare recovery options</h2></div><span className="pill">Day {day} onward</span></div>
    <p className="muted">Use this saved comparison to find the smallest extra food, water or electricity allowance that meets the entered targets. Each resource is tested separately. Past mission decisions stay intact.</p>
    <form onSubmit={analyze}>
      <div className="recovery-inputs">
        <label className="field"><span>Harvest yield in stress tests (%)</span><input type="number" value={Math.round(options.lower_yield_factor * 100)} min="0" max="100" step="1" disabled={busy} onChange={e => change('lower_yield_factor', Number(e.target.value) / 100)}/></label>
        <label className="field"><span>Additional harvest delay (days)</span><input type="number" value={options.harvest_delay_days} min="0" max="30" step="1" disabled={busy} onChange={e => change('harvest_delay_days', Number(e.target.value))}/></label>
      </div>
      <p className="muted">These are assumptions to test, not measured crop responses or probability estimates.</p>
      <details className="recovery-limits"><summary>Resource limits and reserve protection</summary><div className="recovery-inputs">
        {[['food_limit_kg', 'Maximum additional stored food (kg)', 10000], ['water_limit_l_per_day', 'Maximum additional water (L/day)', 1000], ['power_limit_kwh_per_day', 'Maximum additional electricity (kWh/day)', 100]].map(([key, label, max]) =>
          <label className="field" key={key}><span>{label}</span><input type="number" min="0" max={max} step="0.1" value={options[key]} disabled={busy} onChange={e => change(key, Number(e.target.value))}/></label>)}
      </div><label className="check-label"><input type="checkbox" checked={options.include_reserve} disabled={busy} onChange={e => change('include_reserve', e.target.checked)}/>Also require the entered stored-food reserve target</label>
        <p className="muted">Limits describe hypothetical interventions. They do not confirm that supplies are available. Extra food uses the existing food forms’ age, expiry and composition assumptions.</p>
      </details>
      <div className="actions"><button className="btn primary" type="submit" disabled={busy || planningBusy}>{busy ? 'Calculating recovery options…' : 'Calculate recovery options'}</button><span className="muted">No inventory or equipment changes</span></div>
      {busy && <p role="status" className="muted">Solving the resource options and testing their fixed plans. Larger missions can take a minute.</p>}
      {error && <p role="alert" className="notice warning">{error}</p>}
    </form>
    {report && <div className="recovery-results" aria-live="polite">
      <p className={'notice' + (anyFeasible ? '' : ' warning')}>{anyFeasible ? 'At least one option meets the entered targets under the submitted assumptions.' : 'No tested option meets all entered targets. Review the limits, food composition or combined interventions.'} Only tracked nutrients are assessed.</p>
      <p className="muted">Ranked by remaining-mission feasibility and the worst tested nutrient shortage. Kilograms, litres and electricity are not compared as costs.</p>
      <p className="muted">Required: tracked nutrient targets and resource/portion limits{report.include_reserve ? ', including the entered reserve target.' : '. The reserve remains a soft target.'}</p>
      <div className="table-wrap"><table aria-label="Recovery option comparison"><thead><tr><th>Priority</th><th>Recovery option</th><th>Required addition</th><th>Nutrient gap days</th><th>Test cases met</th><th>Details</th></tr></thead>
        <tbody>{ranked.map(candidate => <tr key={candidate.id}><td>{candidate.rank || '—'}</td><td>{candidate.title}</td><td>{addition(candidate)}</td><td>{candidate.summary.available ? candidate.summary.target_gap_days : 'Unavailable'}</td><td>{candidate.summary.available ? candidate.cases_passed + ' / ' + candidate.cases_tested : 'Unavailable'}</td><td><button type="button" className="text-button" disabled={!candidate.summary.available} aria-label={'Review ' + candidate.title.toLowerCase()} aria-pressed={selectedId === candidate.id} onClick={() => setSelectedId(candidate.id)}>Review</button></td></tr>)}</tbody>
      </table></div>
      <details className="recovery-minimums"><summary>Minimum additional resource results</summary><dl>{report.candidates.filter(c => c.id !== 'replan').map(candidate => <div key={candidate.id}><dt>{titles[candidate.id]}</dt><dd>{addition(candidate)}</dd></div>)}</dl></details>
      {selected && <section className="recovery-review" aria-label="Selected recovery plan">
        <h3>{selected.title}</h3>
        <dl className="recovery-metrics"><div><dt>Remaining nutrient gap days</dt><dd>{number(selected.summary.target_gap_days)}</dd></div><div><dt>Worst tested nutrient gap days</dt><dd>{number(selected.worst_case_target_gap_days)}</dd></div><div><dt>Lowest tracked coverage</dt><dd>{number(selected.summary.minimum_coverage_pct)}%</dd></div></dl>
        {selected.resources.mode === 'food' && <p className="muted">Food proposed for arrival on Day {selected.resources.arrival_day}: {Object.entries(selected.resources.food_kg).filter(([, kg]) => kg > 1e-6).map(([id, kg]) => number(kg) + ' kg ' + (foodNames[id] || id)).join('; ') || 'none required'}.</p>}
        {['water', 'power'].includes(selected.resources.mode) && <p className="muted">Uniform allowance for {report.remaining_days} remaining days: {number(amount(selected))} {units[selected.id]}, or {number(amount(selected) * report.remaining_days)} {selected.id === 'water' ? 'L' : 'kWh'} over the remaining mission.</p>}
        <div className="table-wrap"><table aria-label="Selected plan stress tests"><thead><tr><th>Test case</th><th>Entered constraints met</th><th>Nutrient gap days</th><th>Resource gap days</th><th>Reserve gap days</th><th>First nutrient gap</th></tr></thead><tbody>{selected.stress_tests.map(test => <tr key={test.id}><td>{test.name}</td><td>{test.summary.meets_targets ? 'Yes' : 'No'}</td><td>{test.summary.target_gap_days}</td><td>{test.summary.resource_gap_days}</td><td>{test.summary.reserve_gap_days}</td><td>{test.summary.first_target_gap_day ? 'Day ' + test.summary.first_target_gap_day : 'None'}</td></tr>)}</tbody></table></div>
        <p className="muted">Planting and requested meals are held fixed during each test. Yield loss, harvest delay and delayed-batch area overlap can expose shortages. Passing these cases is not a measured reliability percentage.</p>
        <details><summary>Proposed planting and harvest schedule</summary><div className="table-wrap"><table aria-label="Recovery planting schedule"><thead><tr><th>Crop</th><th>Planting day</th><th>Harvest day</th><th>Area (m²)</th><th>Estimated harvest (kg)</th></tr></thead><tbody>{selected.plan.planting.filter(batch => batch.harvest_day >= day).map((batch, i) => <tr key={i}><td>{batch.crop}</td><td>{batch.day}</td><td>{batch.harvest_day}</td><td>{number(batch.area_m2)}</td><td>{number(batch.predicted_harvest_kg)}</td></tr>)}</tbody></table></div>{!selected.plan.planting.length && <p className="muted">This option contains no crop plantings.</p>}</details>
      </section>}
      <details className="recovery-assumptions"><summary>Calculation boundaries and submitted evidence</summary>{report.limitations.map((item, i) => <p className="muted" key={i}>{item}</p>)}<pre>{JSON.stringify({created_at_utc: report.created_at_utc, source_run_id: report.source_run_id, input_sha256: report.input_sha256, input_status: report.input_status, inputs: report.inputs}, null, 2)}</pre></details>
      <button className="btn" type="button" onClick={() => exportReport(report)}>Export recovery report JSON</button>
    </div>}
  </section>;
}
