import React, {useEffect, useRef, useState} from 'react';
import {ArrowRight, Activity, Sparkles, Utensils} from 'lucide-react';
import './astronaut-guidance.css';

const nutrientLabels = {energy: 'Energy', protein: 'Protein', vitamin_c: 'Vitamin C'};
const nutrientUnits = {energy: 'kcal', protein: 'g', vitamin_c: 'mg'};
const finite = value => typeof value === 'number' && Number.isFinite(value);
const number = value => finite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: 2}) : 'Unknown';
const measure = (value, unit) => finite(value) ? number(value) + ' ' + unit : 'Unknown';
const safeSource = url => typeof url === 'string' && /^https?:\/\//i.test(url);
const readable = value => typeof value === 'string' ? value.replaceAll('_', ' ') : '';
const availabilityLabels = {available: 'Enough for this reference portion', insufficient: 'Less than this reference portion', expired: 'Expired in the model', not_in_saved_inventory: 'No saved edible stock', unknown_inventory: 'Inventory unavailable'};

function NutrientChart({member}) {
  const rows = member.nutrients || [];
  return <section className="astronaut-nutrient-chart" aria-labelledby="astronaut-intake-title">
    <div className="astronaut-section-title"><h3 id="astronaut-intake-title">Daily nutrient picture</h3><span>Day-specific intake · separate units</span></div>
    <div className="astronaut-chart-legend"><span><i className="target"/>Daily target</span><span><i className="intake"/>Recorded intake</span></div>
    {rows.length ? <div className="astronaut-nutrient-rows">{rows.map(row => {
      const label = row.label || nutrientLabels[row.nutrient] || readable(row.nutrient);
      const unit = row.unit || nutrientUnits[row.nutrient] || '';
      const target = finite(row.target) && row.target > 0 ? row.target : null;
      const intake = finite(row.intake) && row.intake >= 0 ? row.intake : null;
      const complete = row.log_complete === true;
      const gap = complete && member.targets_reviewed === true && finite(row.gap) ? row.gap : null;
      const scale = Math.max(target || 0, intake || 0, 1);
      const status = !complete ? 'Intake log incomplete' : target === null ? 'Daily target not set' : member.targets_reviewed !== true ? 'Target needs review' : gap === null ? 'Comparison unavailable' : gap > 0 ? 'Remaining to target' : 'Target met in the log';
      return <article className={'astronaut-nutrient-row ' + (row.nutrient === member.focus_nutrient ? 'focused' : '')} key={row.nutrient}>
        <div className="astronaut-nutrient-heading"><strong>{label}</strong><span>{row.nutrient === member.focus_nutrient ? 'Current focus' : unit}</span></div>
        <div className="astronaut-bars" role="img" aria-label={label + ': daily target ' + measure(target, unit) + ', recorded intake ' + measure(intake, unit) + ', ' + status.toLowerCase()}>
          <div className="astronaut-bar-line"><span>Target</span><div className="astronaut-bar-track"><i className="target" style={{width: (target === null ? 0 : target / scale * 100) + '%'}}/></div><b>{measure(target, unit)}</b></div>
          <div className="astronaut-bar-line"><span>Intake</span><div className="astronaut-bar-track"><i className="intake" style={{width: (intake === null ? 0 : intake / scale * 100) + '%'}}/></div><b>{measure(intake, unit)}</b></div>
        </div>
        <div className={'astronaut-gap ' + (gap > 0 ? 'remaining' : '')}><span>{status}</span>{gap !== null && gap > 0 && <strong>{measure(gap, unit)}</strong>}</div>
      </article>;
    })}</div> : <p className="muted">Nutrient comparisons need a crew profile with daily targets and an intake log.</p>}
  </section>;
}

function FoodOptions({options}) {
  return <section className="astronaut-food-options" aria-labelledby="astronaut-food-title">
    <div className="astronaut-section-title"><h3 id="astronaut-food-title"><Utensils size={18}/>Food options to compare</h3><span>Reference portions, not an assigned meal</span></div>
    {!!options?.length ? <div className="table-wrap"><table aria-label="Individual food options"><thead><tr><th>Food / reference portion</th><th>Energy</th><th>Protein</th><th>Vitamin C</th><th>Availability</th></tr></thead><tbody>{options.map((food, index) => <tr key={(food.food_key || food.name) + '-' + index}>
      <td><strong>{food.name}</strong><small>{measure(food.reference_grams, 'g')}{food.food_form ? ' · ' + food.food_form : ''}</small>{food.reason && <small>{food.reason}</small>}{safeSource(food.source_url) && <a href={food.source_url} target="_blank" rel="noreferrer">Composition reference ↗</a>}</td>
      <td>{measure(food.nutrients?.energy, 'kcal')}</td><td>{measure(food.nutrients?.protein, 'g')}</td><td>{measure(food.nutrients?.vitamin_c, 'mg')}</td>
      <td>{finite(food.available_grams) ? <><strong>{measure(food.available_grams, 'g')}</strong><small>Shared modeled stock</small></> : <span>Stock unconfirmed</span>}{food.availability && <small>{availabilityLabels[food.availability] || readable(food.availability)}</small>}</td>
    </tr>)}</tbody></table></div> : <p className="muted">No food comparison is available from the current targets and reference data.</p>}
  </section>;
}

export default function AstronautGuidance({config, run, crewState, crewProfiles, missionDay = 1, setMissionDay, request, navigate}) {
  const planningConfig = run?.metadata?.config || config;
  const horizon = Math.max(1, Number(planningConfig?.days) || 1);
  const day = Math.max(1, Math.min(horizon, Number(missionDay) || 1));
  const state = crewState || {profiles: crewProfiles || []};
  const [focus, setFocus] = useState('auto');
  const [report, setReport] = useState(null);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [explanation, setExplanation] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');
  const version = useRef(0), aiVersion = useRef(0), selection = useRef(selectedId);
  selection.current = selectedId;
  const contextKey = JSON.stringify([planningConfig, run?.metadata, state, day, focus]);
  const activeContext = useRef(contextKey);
  activeContext.current = contextKey;

  const current = (token, context) => version.current === token && activeContext.current === context;
  async function calculate() {
    if (!planningConfig) return;
    const token = ++version.current, context = contextKey;
    aiVersion.current++;
    setBusy(true); setError(''); setReport(null); setExplanation(null); setAiError(''); setAiBusy(false);
    try {
      const response = await request('/astronaut-guidance', {metadata: run?.metadata, config: planningConfig, crew_state: state, day, focus_nutrient: focus});
      if (!current(token, context)) return;
      if (!Array.isArray(response?.members)) throw new Error('Individual guidance did not return usable crew records.');
      setReport(response);
      setSelectedId(response.members.some(member => member.profile_id === selection.current) ? selection.current : response.members[0]?.profile_id || '');
    } catch (failure) {
      if (current(token, context)) setError(failure.message || 'Individual guidance could not be calculated.');
    } finally {if (current(token, context)) setBusy(false);}
  }

  useEffect(() => {
    version.current++; aiVersion.current++;
    setReport(null); setError(''); setExplanation(null); setAiError(''); setAiBusy(false); setBusy(false);
    if (planningConfig) void calculate();
  }, [contextKey]);
  useEffect(() => () => {version.current++; aiVersion.current++;}, []);

  function chooseMember(value) {
    aiVersion.current++;
    setSelectedId(value); setExplanation(null); setAiError(''); setAiBusy(false);
  }
  async function explain() {
    if (!report?.evidence_id || !selectedId || !report.ai?.available) return;
    const token = ++aiVersion.current, context = contextKey, profileId = selectedId;
    setAiBusy(true); setExplanation(null); setAiError('');
    try {
      const response = await request('/astronaut-guidance/ai', {evidence_id: report.evidence_id, profile_id: profileId});
      if (aiVersion.current !== token || activeContext.current !== context || selection.current !== profileId) return;
      if (!Array.isArray(response?.summary)) throw new Error('The explanation was unavailable. Computed guidance remains available.');
      setExplanation(response);
    } catch (failure) {
      if (aiVersion.current === token && activeContext.current === context && selection.current === profileId) setAiError(failure.message || 'AI explanation unavailable. Computed guidance remains available.');
    } finally {if (aiVersion.current === token && activeContext.current === context && selection.current === profileId) setAiBusy(false);}
  }

  const member = report?.members.find(item => item.profile_id === selectedId);
  const logComplete = member?.log_status === 'complete' || member?.log_status === 'complete_log' || !!member?.nutrients?.length && member.nutrients.every(row => row.log_complete === true);
  return <section className="astronaut-guidance" aria-labelledby="astronaut-guidance-title">
    <header className="astronaut-guidance-header"><div><span className="eyebrow">PERSONAL NUTRITION · DATA REVIEW</span><h1 id="astronaut-guidance-title">Astronaut guidance</h1><p>A daily view of each person’s recorded intake, nutrient targets and food options.</p></div><a className="text-button" href="#crew" onClick={() => navigate?.('crew')}>Review crew data <ArrowRight size={16}/></a></header>
    <div className="astronaut-guidance-controls">
      <label className="field"><span>Astronaut</span><select aria-label="Astronaut" value={selectedId} disabled={!report?.members?.length} onChange={event => chooseMember(event.target.value)}>{!report?.members?.length && <option value="">Waiting for crew records</option>}{(report?.members || []).map(person => <option value={person.profile_id} key={person.profile_id}>{person.name}</option>)}</select></label>
      <label className="field"><span>Mission day</span><input type="number" min="1" max={horizon} step="1" value={day} disabled={!setMissionDay} onChange={event => {const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= horizon) setMissionDay?.(value);}}/></label>
      <label className="field"><span>Nutrient focus</span><select value={focus} onChange={event => setFocus(event.target.value)}><option value="auto">Automatic from this person’s data</option>{Object.entries(nutrientLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
    </div>
    {!planningConfig && <div className="empty-state"><h2>Load a mission to begin</h2><p>Individual guidance uses the current mission configuration and crew records.</p></div>}
    {busy && <p role="status">Reviewing crew records for Day {day}…</p>}
    {error && <div className="notice warning" role="alert"><p>{error}</p><button className="text-button" type="button" onClick={calculate}>Retry guidance</button></div>}
    {report && !member && <div className="empty-state"><h2>No named crew profile available</h2><p>Add or apply individual crew profiles in Crew & nutrition.</p><a href="#crew" onClick={() => navigate?.('crew')}>Open crew data →</a></div>}
    {member && <div className="astronaut-guidance-result" aria-live="polite">
      <div className="astronaut-person-heading"><div><span className="eyebrow">DAY {report.day ?? day} · INDIVIDUAL REVIEW</span><h2>{member.name}</h2>{member.target_source && <small className="astronaut-target-source">{member.target_source === 'accepted_mission' ? 'Accepted mission targets' : 'Current personal profile targets'}</small>}</div><div className="astronaut-guidance-badges">{report.sample_only && <span className="source-pill">Sample crew data</span>}<span className={'source-pill ' + (member.targets_reviewed ? '' : 'astronaut-unreviewed')}>{member.targets_reviewed ? 'Reviewed targets' : 'Unreviewed targets'}</span><span className="source-pill">{logComplete ? 'Complete intake log' : 'Incomplete intake log'}</span></div></div>
      {member.pending_target_change && <div className="notice warning">Target edits are pending. This personal analysis uses the provided target edits; the saved mission keeps its accepted targets until changes are applied.</div>}
      {member.mission_membership === 'not_matched' && <div className="astronaut-data-note"><Activity size={18}/><span>This profile is available for personal analysis and is not matched to the saved mission roster. Apply reviewed crew changes separately to include this person in resource planning.</span></div>}
      {!logComplete && <div className="astronaut-data-note"><Activity size={18}/><span>{member.log_status === 'missing' || member.log_status === 'missing_log' ? 'No intake was recorded for this day.' : 'This day’s food log is not complete.'} Missing intake is unknown; it is not counted as zero or diagnosed as a deficiency.</span></div>}
      <NutrientChart member={member}/>
      <div className="astronaut-guidance-actions">
        <section aria-labelledby="astronaut-next-title"><div className="astronaut-section-title"><h3 id="astronaut-next-title">What to review next</h3></div>{member.actions?.length ? <ol>{member.actions.map((action, index) => <li key={action.id || index}><strong>{action.title}</strong>{action.message && <p>{action.message}</p>}</li>)}</ol> : <p className="muted">No additional action was identified from the available records.</p>}</section>
        <section aria-labelledby="astronaut-health-title"><div className="astronaut-section-title"><h3 id="astronaut-health-title">Health observations</h3></div>{member.health_alerts?.length ? <ul className="astronaut-health-observations">{member.health_alerts.map((alert, index) => <li className={alert.severity || ''} key={alert.id || alert.kind + '-' + index}>{alert.sample_only && <span className="source-pill">Sample observation</span>}{alert.title && <strong>{alert.title}</strong>}<p>{alert.message}</p>{alert.day != null && <small>Recorded on Day {alert.day}</small>}</li>)}</ul> : <p className="muted">No flagged comparison in the supplied health records. Missing measurements remain unknown.</p>}{!!member.missing_metrics?.length && <dl className="astronaut-missing-metrics">{member.missing_metrics.map((metric, index) => <div key={index}><dt>{typeof metric === 'string' ? metric.replace(' for one or more crew members', '') : metric.name || metric.metric || 'Measurement'}</dt><dd>Unknown</dd></div>)}</dl>}</section>
      </div>
      <FoodOptions options={member.food_options}/>
      <section className="astronaut-explanation" aria-labelledby="astronaut-explanation-title"><div><span className="eyebrow">EXPLAIN THE EVIDENCE</span><h3 id="astronaut-explanation-title">Understand this guidance</h3><p>Only computed anonymous nutrient and food facts are sent when you request an AI explanation.</p></div>{report.ai?.available && report.evidence_id ? <button className="btn" type="button" disabled={aiBusy} onClick={explain}><Sparkles size={16}/>{aiBusy ? 'Preparing explanation…' : 'Explain with Gemini'}</button> : <span className="astronaut-local-label">Local guidance · no API key required</span>}
        {aiError && <p role="alert" className="astronaut-ai-message">{aiError}</p>}
        {explanation && <div className="astronaut-ai-summary"><strong>{explanation.mode === 'gemini_fact_selection' ? 'AI explanation of computed facts' : 'Local evidence explanation'}</strong><ul>{explanation.summary.map((text, index) => <li key={index}>{text}</li>)}</ul>{explanation.reason && <small>{explanation.reason}</small>}</div>}
      </section>
      <details className="astronaut-guidance-scope"><summary>Data sources and limits</summary>{member.target_source && <p>Target source: {readable(member.target_source)}.</p>}{(member.facts || []).map((fact, index) => <p key={fact.id || index}>{fact.text}</p>)}{(report.scope?.limitations || []).map((text, index) => <p key={index}>{text}</p>)}</details>
    </div>}
  </section>;
}
