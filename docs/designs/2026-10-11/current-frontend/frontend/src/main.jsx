import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowRight, ArrowUpRight, Archive, Beaker, Check, ChevronRight, CircleHelp, FlaskConical, Layers3, Leaf, Radio, Settings2, Sprout, Utensils, X, Zap } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import NutritionPanel from './NutritionPanel.jsx';
import './style.css';

export async function request(path, body) {
  const multipart = body instanceof FormData;
  const response = await fetch('/api' + path, {method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined || multipart ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || 'Request failed'));
  return data;
}
const copy = value => structuredClone(value);
const pretty = value => value == null ? 'Unavailable' : typeof value === 'number' ? value.toLocaleString(undefined, {maximumFractionDigits: 2}) : String(value);
function download(name, value, type = 'application/json') {
  const data = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const url = URL.createObjectURL(new Blob([data], {type}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}
function csv(rows) {
  if (!rows.length) return '';
  const keys = [...new Set(rows.flatMap(Object.keys))];
  const cell = v => '"' + (typeof v === 'object' && v !== null ? JSON.stringify(v) : v ?? '').toString().replaceAll('"', '""') + '"';
  return [keys.map(cell).join(','), ...rows.map(r => keys.map(k => cell(r[k])).join(','))].join('\n');
}
function Field({label, value, onChange, min, max, step = 'any', type = 'number', disabled = false}) {
  return <label className="field"><span>{label}</span><input type={type} value={value ?? ''} min={min} max={max} step={step} disabled={disabled}
    onChange={e => onChange(type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)}/></label>;
}
function Notice({children, tone = ''}) { return <div className={'notice ' + tone}>{children}</div>; }
function Metric({label, value, detail}) { return <div className="metric"><span>{label}</span><strong>{pretty(value)}</strong>{detail && <small>{detail}</small>}</div>; }
function DataTable({rows, columns}) {
  if (!rows?.length) return <p className="muted">No records for this selection.</p>;
  const keys = columns || Object.keys(rows[0]);
  return <div className="table-wrap"><table><thead><tr>{keys.map(k => <th key={k}>{k.replaceAll('_', ' ')}</th>)}</tr></thead>
    <tbody>{rows.map((r,i) => <tr key={i}>{keys.map(k => <td key={k}>{typeof r[k] === 'object' && r[k] !== null ? JSON.stringify(r[k]) : pretty(r[k])}</td>)}</tr>)}</tbody></table></div>;
}
function Chart({data, lines, unit = '', height = 270}) {
  return <div className="chart" style={{height}}><ResponsiveContainer width="100%" height="100%">
    <LineChart data={data}><CartesianGrid stroke="#263338" vertical={false}/><XAxis dataKey="day" tick={{fill:'#90a5ab',fontSize:11}} axisLine={false} tickLine={false}/>
      <YAxis unit={unit} tick={{fill:'#90a5ab',fontSize:11}} axisLine={false} tickLine={false} width={55}/>
      <Tooltip contentStyle={{background:'#172329',border:'1px solid #385057',borderRadius:8,color:'#e3ecec'}} formatter={v => pretty(v) + unit}/>
      <Legend iconType="plainline" wrapperStyle={{fontSize:12,paddingTop:10}}/>
      {lines.map((line,i) => <Line key={line.key} type="linear" dataKey={line.key} name={line.name} stroke={line.color || ['#9ad7b3','#94b9d7','#e5b46e'][i]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/>)}
    </LineChart></ResponsiveContainer></div>;
}
const NAV = [
  ['overview','Mission overview',Layers3],['inputs','Food & crew',Utensils],['nutrition','Nutrition assessment',Activity],
  ['crops','Crop schedules',Sprout],['research','Models & calibration',FlaskConical],['simulator','What-if simulator',Settings2],
  ['vision','Plant screening',Leaf],['telemetry','Live tray',Radio],['archive','Saved workspace',Archive],
];

function App() {
  const [bootstrap,setBootstrap] = useState(null), [config,updateConfig] = useState(null), [run,setRun] = useState(null);
  const [page,setPage] = useState(location.hash.slice(1) || 'overview'), [message,setMessage] = useState(null);
  const [initialError,setInitialError] = useState('');
  useEffect(() => { request('/bootstrap').then(data => {setBootstrap(data); updateConfig(data.config);if(data.last_run)setRun(data.last_run);}).catch(e => setInitialError(e.message)); }, []);
  useEffect(() => { const change = () => setPage(location.hash.slice(1) || 'overview'); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const notify = (text, error = false) => setMessage({text,error});
  const setConfig = value => {updateConfig(value); setRun(null); notify('Inputs updated. Run the simulator to evaluate this configuration.');};
  const navigate = key => {location.hash = key; setPage(key);};
  if (!bootstrap || !config) return <main className="loading"><Sprout size={36}/><h1>ASTRA-BIO</h1><p>{initialError || 'Opening your habitat workspace…'}</p>{initialError && <button onClick={() => location.reload()}>Retry connection</button>}</main>;
  const context = {config,setConfig,bootstrap,request,notify,run,setRun,navigate};
  const current = NAV.find(n => n[0] === page) || NAV[0];
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#overview"><span className="brand-symbol"><Sprout size={22}/></span><span>ASTRA-BIO<small>BIOLOGICAL SYSTEMS</small></span></a>
      <div className="sidebar-label">HABITAT WORKSPACE</div><nav aria-label="Workspace navigation">{NAV.map(([key,label,Icon]) =>
        <a href={'#'+key} key={key} className={page===key?'active':''} aria-current={page===key?'page':undefined}><Icon size={17}/><span>{label}</span>{page===key && <ChevronRight size={14}/>}</a>)}</nav>
      <div className="sidebar-bottom"><div className="status-dot"/><strong>Local research workspace</strong><small>{config.crew} crew · {config.days} day horizon</small><small>Actuation disabled</small></div>
    </aside>
    <div className="main-shell"><header className="topbar"><span>Workspace <ChevronRight size={13}/> {current[1]}</span><span className="pill"><span className="status-dot"/> Research prototype</span></header>
      <main className="content">
        {message && <div className={'toast '+(message.error?'error':'')} role={message.error?'alert':'status'}><span>{message.text}</span><button aria-label="Dismiss notification" onClick={() => setMessage(null)}><X size={16}/></button></div>}
        {page === 'overview' && <Overview {...context}/>}
        {page === 'inputs' && <Inputs {...context}/>}
        <section hidden={page !== 'nutrition'}><NutritionPanel {...context}/></section>
        {page === 'crops' && <Crops {...context}/>}
        {page === 'research' && <Research {...context}/>}
        {page === 'simulator' && <Simulator {...context}/>}
        {page === 'vision' && <Vision {...context}/>}
        {page === 'telemetry' && <Telemetry {...context}/>}
        {page === 'archive' && <Saved {...context}/>}
      </main><footer>ASTRA-BIO <span>Terrestrial research references · Simulated mission inputs · No clinical diagnosis</span></footer>
    </div>
  </div>;
}
function Title({eyebrow, children, description, action}) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{children}</h1><p>{description}</p></div>{action}</div>;
}
function Overview({config,run,navigate}) {
  const measured = Object.keys(config.input_provenance).some(k => k.endsWith(':harvest'));
  return <>
    <div className="mission-hero"><div><div className="eyebrow">CREW → FOOD → CROPS → RESOURCES</div><h1>Plan for the crew.<br/><em>Grow for the mission.</em></h1><p>A shared view of nutrition, harvest timing and resource limits. Explore the trade-offs before changing a habitat plan.</p>
      <button className="btn primary" onClick={() => navigate('simulator')}>Open what-if simulator <ArrowRight size={16}/></button><span className="hero-note">{measured?'Measured crop references loaded':'Editable demonstration inputs loaded'}</span></div>
      <div className="ecosystem" aria-label="Crew food and resources planning loop"><div className="orbit"/><div className="orbit inner"/><div className="ecosystem-core"><Sprout size={36}/><strong>ASTRA<br/>BIO</strong><small>Decision support</small></div>
        <span className="orbit-label crew"><Activity size={17}/>Crew needs</span><span className="orbit-label food"><Utensils size={17}/>Available food</span><span className="orbit-label plants"><Leaf size={17}/>Future harvest</span><span className="orbit-label resources"><Zap size={17}/>Resource budget</span></div></div>
    <div className="metrics-row"><Metric label="Crew members" value={config.crew} detail="Editable planning input"/><Metric label="Planning horizon" value={config.days+' days'} detail="Daily food and resource balance"/><Metric label="Crop profiles" value={config.crops.length} detail={measured?'Terrestrial measured endpoints':'Synthetic editable crop estimates'}/><Metric label="Growing area" value={config.area_m2+' m²'} detail="Shared cultivation capacity"/></div>
    <div className="two-col"><section className="panel"><div className="section-heading"><h2>A plan that shows its limits</h2><span className="pill">Three connected decisions</span></div>
      {[['01','Food today','Allocate inventory against tracked dietary targets. Future harvests cannot feed earlier meals.'],['02','Harvests tomorrow','Schedule whole trays when configured, with explicit harvest delays and reserves.'],['03','A changing mission','Compare a fixed plan with a replan that preserves every decision before the event.']].map(([num,title,body]) =>
        <div className="editorial-row" key={num}><span>{num}</span><div><h3>{title}</h3><p>{body}</p></div></div>)}</section>
      <section className="panel evidence-panel"><span className="eyebrow">MODEL EVIDENCE</span><h2>Built around observable inputs.</h2><p>NASA and EDEN ISS harvest references, a reproducible USDA food subset, and local plant-image inference are available without hardware.</p>
        <button className="text-button" onClick={() => navigate('research')}>Review measured crop data <ArrowUpRight size={16}/></button>
        <Notice>Harvest references come from terrestrial controlled environments. Transfer to a new tray or spaceflight is unvalidated.</Notice></section></div>
    {run && <section className="panel"><div className="section-heading"><h2>Latest adaptive plan</h2><button className="text-button" onClick={() => navigate('simulator')}>View comparison <ArrowRight size={16}/></button></div>
      <RunMetrics plan={run.metadata.adaptive}/><Notice>{run.metadata.scenario.name} · submitted {new Date(run.metadata.created_at_utc).toLocaleString()}</Notice></section>}
  </>;
}
function Inputs({config,setConfig,bootstrap,notify}) {
  const [draft,setDraft] = useState(copy(config)), [busy,setBusy] = useState(false);
  const set = (key,value) => setDraft(v => ({...v,[key]:value}));
  const food = (i,key,value) => setDraft(v => ({...v,foods:v.foods.map((f,index)=>index===i?{...f,[key]:value}:f)}));
  async function submit(e) {e.preventDefault(); setBusy(true);try {const result=await request('/config/validate',{config:draft});setConfig(result.config);}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="PLANNING INPUTS" description="Choose inventory, reviewed dietary targets and resource budgets. Saving changes clears the previous comparison.">Food & crew</Title>
    <form onSubmit={submit}><section className="panel"><h2>Mission configuration</h2><div className="form-grid">
      <Field label="Crew members" value={draft.crew} min={1} max={12} step={1} onChange={v=>set('crew',v)}/>
      <Field label="Horizon (days)" value={draft.days} min={7} max={180} step={1} onChange={v=>set('days',v)}/>
      <Field label="Reserve buffer (days)" value={draft.reserve_days} min={0} max={30} onChange={v=>set('reserve_days',v)}/>
      <Field label="Growing area (m²)" value={draft.area_m2} min={0} onChange={v=>set('area_m2',v)}/>
      <Field label="Water budget (L/day)" value={draft.water_budget_l_per_day} min={0} onChange={v=>set('water_budget_l_per_day',v)}/>
      <Field label="Energy budget (kWh/day)" value={draft.power_budget_kwh_per_day} min={0} onChange={v=>set('power_budget_kwh_per_day',v)}/>
      <Field label="Crew water (L/person/day)" value={draft.crew_water_l_per_day} min={0} onChange={v=>set('crew_water_l_per_day',v)}/>
      <Field label="Fresh food limit (kg/person/day)" value={draft.max_fresh_kg_per_crew_day} min={0} onChange={v=>set('max_fresh_kg_per_crew_day',v)}/>
    </div><p className="muted">Use net makeup water consistently. Recycling, cooking water and a complete oxygen/CO₂ loop are outside this model.</p></section>
    <section className="panel"><h2>Daily dietary targets</h2><div className="form-grid">{Object.keys(draft.targets_per_crew).map(n =>
      <Field key={n} label={n.replaceAll('_',' ')+' ('+draft.nutrient_units[n]+')'} value={draft.targets_per_crew[n]} min={.001} onChange={v=>set('targets_per_crew',{...draft.targets_per_crew,[n]:v})}/>)}</div>
      <Notice>Targets are user-reviewed planning inputs. Intake gaps do not establish a clinical deficiency; only three nutrients are tracked.</Notice></section>
    <section className="panel"><div className="section-heading"><h2>Stored-food inventory</h2><span className="pill">kg of catalogued food form</span></div>
      <div className="table-wrap"><table><thead><tr><th>Food</th><th>Stock (kg)</th><th>Reserve eligible</th><th>Shelf life (days)</th><th>Initial age (days)</th><th>Vitamin C half life (days)</th></tr></thead><tbody>{draft.foods.map((f,i)=>
        <tr key={f.id}><td>{f.name}</td><td><input aria-label={f.name+' stock'} type="number" min={0} step="any" value={f.initial_kg} onChange={e=>food(i,'initial_kg',Number(e.target.value))}/></td>
          <td><input aria-label={f.name+' reserve eligible'} type="checkbox" checked={f.is_reserve} onChange={e=>food(i,'is_reserve',e.target.checked)}/></td>
          <td><input aria-label={f.name+' shelf life'} type="number" min={0} step={1} value={f.shelf_life_days||0} onChange={e=>food(i,'shelf_life_days',Number(e.target.value)||null)}/></td>
          <td><input aria-label={f.name+' initial age'} type="number" min={0} step={1} value={f.initial_age_days} onChange={e=>food(i,'initial_age_days',Number(e.target.value))}/></td>
          <td><input aria-label={f.name+' vitamin C half life'} type="number" min={0} step="any" value={f.nutrient_half_life_days.vitamin_c||0} onChange={e=>{const h={...f.nutrient_half_life_days};const v=Number(e.target.value);if(v)h.vitamin_c=v;else delete h.vitamin_c;food(i,'nutrient_half_life_days',h);}}/></td></tr>)}</tbody></table></div>
      <p className="muted">Shelf life 0 = unspecified. Half life 0 = fixed composition. Entered expiry is a stock policy; optional exponential retention is a sensitivity assumption requiring measured storage data, not a food-safety forecast. Reserve credit excludes food expiring within the buffer.</p></section>
    <section className="panel"><h2>Practical allocation limits</h2><div className="form-grid"><Field label="Planting increment (m²; 0 = continuous)" value={draft.planting_increment_m2} min={0} onChange={v=>set('planting_increment_m2',v)}/>
      <Field label="Food mass limit (kg/person/day; 0 = off)" value={draft.max_total_food_kg_per_crew_day} min={0} onChange={v=>set('max_total_food_kg_per_crew_day',v)}/>
      {Object.keys(draft.targets_per_crew).map(n => <Field key={n} label={n.replaceAll('_',' ')+' upper bound (0 = off)'} value={draft.nutrient_upper_per_crew[n]||0} min={0} onChange={v=>{const u={...draft.nutrient_upper_per_crew};if(v)u[n]=v;else delete u[n];set('nutrient_upper_per_crew',u);}}/>)}</div></section>
    <div className="actions"><button className="btn primary" disabled={busy}>{busy?'Validating…':'Save planning inputs'}</button><button type="button" className="btn" onClick={()=>setDraft(copy(bootstrap.demo_config||bootstrap.config))}>Load demo into form</button></div></form>
  </>;
}
function RunMetrics({plan}) {
  const m=plan.metrics;return <div className="metrics-row"><Metric label="Days with nutrient gaps" value={m.shortfall_days} detail="Only tracked targets"/><Metric label="Total harvest" value={pretty(m.total_harvest_kg)+' kg'} detail="Simulated edible mass"/><Metric label="Water use" value={pretty(m.total_water_l)+' L'} detail="Crew plus crop model"/><Metric label="Electrical use" value={pretty(m.total_power_kwh)+' kWh'} detail="Configured crop coefficients"/></div>;
}
function Simulator({config,bootstrap,run,setRun,notify}) {
  const [s,setS] = useState(copy(bootstrap.presets.nominal)), [busy,setBusy] = useState(false), [day,setDay] = useState(1), [nutrient,setNutrient] = useState(Object.keys(config.targets_per_crew)[0]),[lossCrop,setLossCrop]=useState(''),[loss,setLoss]=useState(50),[targetIncrease,setTargetIncrease]=useState(0);
  const [localExplanation,setLocalExplanation]=useState(false),[model,setModel]=useState('llama3.2:3b'),[explanationText,setExplanationText]=useState(null);
  useEffect(()=>setExplanationText(null),[run]);
  const change=(k,v)=>setS(prev=>({...prev,[k]:v}));
  async function solve(e) {e.preventDefault();setBusy(true);try {
    const scenario={...s,event_day:Math.min(s.event_day,config.days),crop_yield_factors:lossCrop?{[lossCrop]:1-loss/100}:{},target_factors:targetIncrease?{[nutrient]:1+targetIncrease/100}:{}};
    scenario.name='Day '+scenario.event_day+' · water '+Math.round(s.water_factor*100)+'% · power '+Math.round(s.power_factor*100)+'% · crew +'+s.extra_crew+(lossCrop?' · '+lossCrop+' yield −'+loss+'%':'')+(targetIncrease?' · '+nutrient+' target +'+targetIncrease+'%':'');
    const result=await request('/plans',{config,scenario});setRun(result);if(result.history_warning)notify(result.history_warning,true);else notify('Comparison complete. The submitted inputs and results were saved locally.');
  }catch(e){notify(e.message,true);}finally{setBusy(false);}}
  const adaptive=run?.metadata.adaptive,baseline=run?.metadata.baseline;
  const rows=adaptive?.daily.map((r,i)=>({...r,adaptive:r[nutrient+'_coverage_pct'],fixed:baseline.daily[i]?.[nutrient+'_coverage_pct']}));
  return <><Title eyebrow="MISSION TRADE-OFFS" description="Apply the same disruption to a fixed plan and an adaptive plan. Charts show calculated outcomes, not promised savings.">What-if simulator</Title>
    <form className="panel" onSubmit={solve}><div className="section-heading"><h2>Define a disruption</h2><span className="pill">Event-day replan</span></div>
      <div className="form-grid"><Field label="Event day" value={Math.min(s.event_day,config.days)} min={1} max={config.days} step={1} onChange={v=>change('event_day',v)}/>
        <Field label="Water remaining (%)" value={Math.round(s.water_factor*100)} min={0} max={100} onChange={v=>change('water_factor',v/100)}/>
        <Field label="Power remaining (%)" value={Math.round(s.power_factor*100)} min={0} max={100} onChange={v=>change('power_factor',v/100)}/>
        <Field label="Additional crew" value={s.extra_crew} min={0} max={8} step={1} onChange={v=>change('extra_crew',v)}/>
        <label className="field"><span>Affected growing crop</span><select value={lossCrop} onChange={e=>setLossCrop(e.target.value)}><option value="">No crop loss</option>{config.crops.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <Field label="Active crop yield loss (%)" value={loss} min={0} max={100} onChange={setLoss}/>
        <label className="field"><span>Dietary target to change</span><select value={nutrient} onChange={e=>setNutrient(e.target.value)}>{Object.keys(config.targets_per_crew).map(n=><option key={n} value={n}>{n.replaceAll('_',' ')}</option>)}</select></label>
        <Field label="Target increase (%)" value={targetIncrease} min={0} max={100} onChange={setTargetIncrease}/></div>
      <div className="actions"><button className="btn primary" disabled={busy}>{busy?'Solving both policies…':'Run comparison'} <ArrowRight size={15}/></button><small className="muted">Replacement crops still require their full growth time.</small></div></form>
    {!run && <div className="empty-state"><Settings2 size={30}/><h2>Your next decision starts here.</h2><p>Submit a scenario to calculate meals, harvests and remaining resources.</p></div>}
    {run && <><Notice tone={adaptive.status==='feasible_with_shortfalls'?'warning':''}><strong>{adaptive.status==='feasible_with_shortfalls'?'Targets remain unmet in this model.':'Model run: '+adaptive.status}</strong> · {run.metadata.scenario.name}<br/><small>These results belong to submitted inputs at {new Date(run.metadata.created_at_utc).toLocaleString()}. Editing the scenario form does not change them.</small></Notice>
      <RunMetrics plan={adaptive}/>{adaptive.warnings.map((w,i)=><Notice key={i} tone="warning">{w}</Notice>)}
      <section className="panel"><div className="section-heading"><h2>{nutrient.replaceAll('_',' ')} coverage</h2><span className="pill">Day by day</span></div><Chart data={rows} unit="%" lines={[{key:'adaptive',name:'Adaptive plan'},{key:'fixed',name:'Fixed plan'}]}/></section>
      <div className="two-col"><section className="panel"><h2>Resource and reserve comparison</h2><DataTable rows={['shortfall_days','total_water_l','total_power_kwh','total_harvest_kg','min_reserve_days','total_waste_kg','upper_bound_excess_days'].map(k=>({metric:k, fixed:baseline.metrics[k],adaptive:adaptive.metrics[k]}))}/></section>
        <section className="panel"><h2>Why the plan changed</h2>{run.explanation?.facts?.slice(0,8).map(f=><p className="fact" key={f.id}>{f.text}</p>)}<p className="muted">Explanations use saved model evidence. Resource-stress yield loss in the fixed plan remains a hypothetical proxy.</p>
          <label className="check-label"><input type="checkbox" checked={localExplanation} onChange={e=>setLocalExplanation(e.target.checked)}/>Optional local Ollama fact selection</label>
          {localExplanation&&<Field type="text" label="Installed Ollama model name" value={model} onChange={setModel}/>}
          <button className="btn" onClick={async()=>{try{const e=await request('/explain',{metadata:run.metadata,ollama:localExplanation,model});setExplanationText(e);}catch(e){notify(e.message,true);}}}>Explain using verified facts</button>
          {explanationText&&<><p className="muted">{explanationText.mode} · {explanationText.fallback_reason||'Visible statements come from saved solver facts.'}</p><p className="fact">{explanationText.narrative}</p></>}
        </section></div>
      <section className="panel"><div className="section-heading"><h2>Food allocation for a day</h2><Field label="Day" value={day} min={1} max={run.metadata.config.days} step={1} onChange={setDay}/></div>
        <DataTable rows={Object.entries(adaptive.consumption[day]||{}).filter(([,v])=>v>1e-6).map(([id,kg])=>({food:[...run.metadata.config.foods,...run.metadata.config.crops].find(f=>f.id===id)?.name||id,total_kg:kg,kg_per_crew:kg/(adaptive.daily[day-1]?.crew||1)}))}/>
        <p className="muted">Aggregate allocations for crew; cooking, recipes and individual menu preferences are outside this planner.</p></section>
      <details className="panel"><summary>Submitted inputs and provenance</summary><pre>{JSON.stringify({input_status:run.metadata.input_status,scenario:run.metadata.scenario,config:run.metadata.config},null,2)}</pre></details>
      <div className="actions"><button className="btn" onClick={()=>download('astra-bio-run.json',run.metadata)}>Export complete run</button><button className="btn" onClick={()=>download('astra-bio-daily.csv',csv([...baseline.daily.map(r=>({policy:'fixed',...r})),...adaptive.daily.map(r=>({policy:'adaptive',...r}))]),'text/csv')}>Export daily CSV</button></div>
    </>}</>;
}
function Crops({config,setConfig,run,notify,navigate}) {
  const [draft,setDraft]=useState(copy(config.crops)),[policy,setPolicy]=useState('adaptive'),[busy,setBusy]=useState(false);
  const keys=['grow_days','yield_kg_per_m2','water_l_per_m2_day','power_kwh_per_m2_day'];
  const labels=['Growth days','Edible yield kg/m²','Net water L/m²/day','Energy kWh/m²/day'];
  const plan=run?.metadata[policy];
  async function save(){setBusy(true);try{const provenance={...config.input_provenance};for(const crop of draft){if(JSON.stringify(crop)!==JSON.stringify(config.crops.find(c=>c.id===crop.id)))provenance['crop:'+crop.id+':user_edit']='User-edited endpoint/resource values override the loaded reference. Review these assumptions.';}const res=await request('/config/validate',{config:{...config,crops:draft,input_provenance:provenance}});setConfig(res.config);}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="HARVEST-AWARE SCHEDULING" description="Harvests enter the food balance only after their growth period. Fresh produce is consumed or discarded on harvest day.">Crop schedules</Title>
    <section className="panel"><div className="section-heading"><h2>Current crop coefficients</h2><button className="text-button" onClick={()=>navigate('research')}>Use measured references <ArrowUpRight size={16}/></button></div>
      <div className="table-wrap"><table><thead><tr><th>Crop</th>{labels.map(l=><th key={l}>{l}</th>)}</tr></thead><tbody>{draft.map((c,i)=><tr key={c.id}><td>{c.name}</td>{keys.map(k=><td key={k}><input aria-label={c.name+' '+k} type="number" min={k==='grow_days'?1:0} step={k==='grow_days'?1:'any'} value={c[k]} onChange={e=>setDraft(v=>v.map((crop,index)=>index===i?{...crop,[k]:Number(e.target.value)}:crop))}/></td>)}</tr>)}</tbody></table></div>
      <div className="actions"><button className="btn primary" disabled={busy} onClick={save}>Save crop coefficients</button><small className="muted">Synthetic defaults stay labelled. Imported references keep their source provenance.</small></div></section>
    {!plan?<div className="empty-state"><Sprout size={30}/><h2>A harvest timeline needs a plan.</h2><p>Run the simulator to see planting dates and available harvests.</p><button className="btn" onClick={()=>navigate('simulator')}>Open simulator</button></div>:
      <section className="panel"><div className="section-heading"><h2>Planting and harvest timeline</h2><select aria-label="Schedule policy" value={policy} onChange={e=>setPolicy(e.target.value)}><option value="adaptive">Adaptive plan</option><option value="baseline">Fixed baseline</option></select></div>
        {policy==='baseline'&&<Notice tone="warning">Fixed batches show nominal planned yields. Realized harvest after resource stress or loss is reported in the daily comparison.</Notice>}
        <div className="timeline">{plan.planting.slice(0,40).map((b,i)=><div className="timeline-row" key={i}><span>{b.crop}</span><div className="timeline-track"><div style={{left:(b.day/run.metadata.config.days*100)+'%',width:((b.harvest_day-b.day)/run.metadata.config.days*100)+'%'}} title={'Day '+b.day+' → '+b.harvest_day}/></div><small>{pretty(b.predicted_harvest_kg)} kg · D{b.harvest_day}</small></div>)}</div>
        {plan.planting.length>40&&<p className="muted">Showing the first 40 timeline rows; the complete schedule is in the table and export.</p>}
        <DataTable rows={plan.planting} columns={['crop','day','harvest_day','area_m2','predicted_harvest_kg']}/>
        <button className="btn" onClick={()=>download('astra-bio-crops.csv',csv(plan.planting),'text/csv')}>Export planting schedule</button></section>}</>;
}
function Research({config,setConfig,bootstrap,notify}) {
  const refs=bootstrap.references,[reference,setReference]=useState(Object.keys(refs)[0]),[age,setAge]=useState(refs[Object.keys(refs)[0]].planning_grow_days),[area,setArea]=useState(1),[prediction,setPrediction]=useState(null);
  const [chosen,setChosen]=useState(['lettuce_batavia','radish_raxe']),[water,setWater]=useState(1.5),[efficacy,setEfficacy]=useState(2.5),[delivery,setDelivery]=useState(.8),[overhead,setOverhead]=useState(.15),[conservative,setConservative]=useState(false);
  const [observations,setObservations]=useState(bootstrap.observations),[holdouts,setHoldouts]=useState(['nasa_rlss_1992_cycle_2']),[fit,setFit]=useState(null),[sensitivity,setSensitivity]=useState(null),[busy,setBusy]=useState(false);
  const r=refs[reference];
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="EVIDENCE & CALIBRATION" description="Ten measured cultivar/environment profiles. Fit batch harvest endpoints and inspect uncertainty before planning with them.">Models & calibration</Title>
    <section className="panel"><div className="section-heading"><h2>A measured harvest endpoint</h2><span className="pill">Terrestrial controlled environment</span></div>
      <div className="form-grid"><label className="field"><span>Reference profile</span><select value={reference} onChange={e=>{setReference(e.target.value);setAge(refs[e.target.value].planning_grow_days);setPrediction(null);}}>{Object.values(refs).map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select></label>
        <Field label="Age from seeding (days)" value={age} min={0} onChange={setAge}/><Field label="Area (m²)" value={area} min={.01} onChange={setArea}/></div>
      <div className="metrics-row"><Metric label="Published fresh edible mean" value={r.yield_kg_per_m2+' kg/m²'}/><Metric label="Published mean cycle" value={r.grow_days+' days'}/><Metric label="Measured cycle count" value={r.reported_cycles}/><Metric label="Observed range" value={r.observed_min_kg_per_m2+'–'+r.observed_max_kg_per_m2+' kg/m²'}/></div>
      <a className="source-link" href={r.source_url} target="_blank" rel="noreferrer">Primary source · {r.source_table} <ArrowUpRight size={14}/></a>
      <p className="muted">{r.cultivar} · {r.ppfd_umol_m2_s} µmol/m²/s PPFD · {r.co2_ppm} ppm CO₂ · {r.cultivation_system}</p>
      <p className="muted">PPFD basis: {r.ppfd_basis}. {r.environment_notes}</p>
      <button className="btn" disabled={busy} onClick={()=>task(async()=>setPrediction(await request('/growth',{crop_id:reference,age_days:age,area_m2:area})))}>Calculate reference harvest</button>
      {prediction&&<Notice>Reference endpoint: {pretty(prediction.expected_harvest_kg)} kg. Available at the entered age: {pretty(prediction.available_harvest_kg)} kg. Intermediate growth was not fitted; observed bounds are experimental ranges, not prediction intervals.</Notice>}
    </section>
    <section className="panel"><h2>Connect measured crop profiles to the planner</h2><div className="reference-options">{Object.values(refs).map(r=><label key={r.id}><input type="checkbox" checked={chosen.includes(r.id)} onChange={e=>setChosen(v=>e.target.checked?[...v,r.id]:v.filter(k=>k!==r.id))}/><span>{r.name}<small>{r.planning_grow_days} days · {r.yield_kg_per_m2} kg/m²</small></span></label>)}</div>
      <div className="form-grid"><Field label="Assumed net water (L/m²/day)" value={water} min={0} onChange={setWater}/><Field label="Assumed LED efficacy (µmol/J)" value={efficacy} min={.1} onChange={setEfficacy}/>
        <Field label="Photon delivery fraction" value={delivery} min={.01} max={1} onChange={setDelivery}/><Field label="Assumed overhead (kWh/m²/day)" value={overhead} min={0} onChange={setOverhead}/></div>
      <label className="check-label"><input type="checkbox" checked={conservative} onChange={e=>setConservative(e.target.checked)}/>Use observed minimum fresh yield</label>
      <Notice>Net makeup water and whole-system energy are missing from these references. Lighting uses reported PPFD/photoperiod and assumed efficiency; kohlrabi uses the reported range midpoint. Nursery stages are not resolved: final lighting and area apply across the whole cycle. HVAC/pump overhead is assumed. Applied irrigation is not net consumption. USDA composition is a species proxy.</Notice>
      <button className="btn primary" disabled={busy||!chosen.length} onClick={()=>task(async()=>{const result=await request('/config/research',{config,ids:chosen,water,efficacy,delivery,overhead,conservative});setConfig(result.config);})}>Apply measured crop references</button>
    </section>
    <section className="panel"><div className="section-heading"><h2>Calibrate with measured harvests</h2><button className="text-button" onClick={()=>download('astra-bio-calibration-template.csv',csv(bootstrap.observations),'text/csv')}>Download observations / CSV template</button></div>
      <Notice>Published means count as summaries, not fabricated individual harvest cycles. The two NASA lettuce trials provide a small held-out diagnostic; they do not establish general prediction accuracy.</Notice>
      <label className="field upload-field"><span>Import your crop-cycle CSV</span><input type="file" accept=".csv,text/csv" onChange={e=>{const file=e.target.files[0];if(!file)return;task(async()=>{const form=new FormData();form.append('file',file);const result=await request('/calibrate/csv',form);setObservations(result.observations);setHoldouts([]);setFit(null);});}}/></label>
      <details><summary>Recorded observations ({observations.length})</summary><DataTable rows={observations} columns={['observation_id','crop_id','grow_days','area_m2','fresh_harvest_kg','observation_type']}/></details>
      <div className="holdouts"><p className="muted">Choose independent held-out cycles:</p>{observations.filter(o=>o.observation_type==='crop_cycle').map(o=><label className="check-label" key={o.observation_id}><input type="checkbox" checked={holdouts.includes(o.observation_id)} onChange={e=>setHoldouts(v=>e.target.checked?[...v,o.observation_id]:v.filter(k=>k!==o.observation_id))}/>{o.observation_id}</label>)}</div>
      <button className="btn primary" disabled={busy} onClick={()=>task(async()=>setFit(await request('/calibrate',{observations,holdout_ids:holdouts})))}>Fit endpoints and score holdouts</button>
      {fit&&<><DataTable rows={Object.values(fit.fit_parameters)} columns={['crop_id','yield_kg_per_m2','grow_days','training_cycle_count','training_summary_count']}/>
        {fit.validation?<Notice tone="warning">Held-out MAE: {pretty(fit.validation.mae_kg_per_m2)} kg/m² · MAPE: {pretty(fit.validation.mape_pct)}% · {fit.validation.holdout_record_count} cycle(s). {fit.validation.limitation}</Notice>:<Notice>Fit completed; no held-out accuracy is available for these data.</Notice>}
        <div className="actions"><button className="btn" onClick={()=>download('astra-bio-calibration.json',fit)}>Export calibration report</button><button className="btn" disabled={busy} onClick={()=>task(async()=>{const result=await request('/calibrate/apply',{config,observations,holdout_ids:holdouts});setConfig(result.config);})}>Apply fitted matching endpoints</button></div></>}
    </section>
    <section className="panel"><h2>Test harvest uncertainty in the food plan</h2><p className="muted">Low, mean and high cases use observed reference bounds. These are deterministic sensitivity cases, not confidence intervals. Apply measured crop profiles first.</p>
      <button className="btn" disabled={busy} onClick={()=>task(async()=>setSensitivity(await request('/sensitivity',{config})))}>{busy?'Calculating…':'Run harvest sensitivity'}</button>
      {sensitivity&&<DataTable rows={sensitivity.cases} columns={['case','status','shortfall_days','total_harvest_kg','total_water_l','total_power_kwh']}/>}</section>
  </>;
}
function Vision({bootstrap,notify}) {
  const [file,setFile]=useState(null),[species,setSpecies]=useState('tomato'),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[preview,setPreview]=useState('');
  useEffect(()=>{if(!file){setPreview('');return;}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
  async function screen(){setBusy(true);try{const form=new FormData();form.append('file',file);setResult(await request('/plant-image?crop_species='+encodeURIComponent(species),form));}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="LOCAL VISUAL SCREENING" description="A pretrained terrestrial leaf classifier. Photographs are processed locally and are not saved or sent to an external service.">Plant screening</Title>
    <div className="two-col"><section className="panel"><h2>Inspect a leaf photograph</h2><label className="field"><span>Crop species</span><select value={species} onChange={e=>{setSpecies(e.target.value);setResult(null);}}>{['tomato','potato','bell pepper','lettuce','radish','kale'].map(s=><option key={s}>{s}</option>)}</select></label>
      <label className="field upload-field"><span>JPG, PNG or WebP · up to 10 MiB</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{setFile(e.target.files[0]||null);setResult(null);}}/></label>
      {preview&&<img className="leaf-preview" src={preview} alt="Selected leaf for local screening"/>}
      <button className="btn primary" disabled={!file||busy||!bootstrap.plant_model.ready} onClick={screen}>{busy?'Running local inference…':'Screen leaf image'}</button></section>
    <section className="panel"><span className="eyebrow">MODEL BOUNDARIES</span><h2>A tentative visual match.</h2><p>The installed MobileNetV3 model covers tomato, potato and bell pepper. Unsupported crops and ambiguous results are withheld.</p><Notice tone="warning">A high model score does not prove disease, pathogen identity, or safety. Scores are not calibrated correctness probabilities. No automatic crop removal, replanning or actuator action occurs.</Notice>
      <a className="source-link" href="https://huggingface.co/imaflower/plantvillage-mobilenetv3" target="_blank" rel="noreferrer">Upstream model card <ArrowUpRight size={14}/></a>
      <p className="muted">Local model: {bootstrap.plant_model.ready?'installed and hash verified':'unavailable; run scripts/setup-plant-model.ps1'}</p></section></div>
    {result&&<section className="panel"><div className="section-heading"><h2>Screening result</h2><span className="pill">{result.status}</span></div><Notice tone={result.status==='tentative'?'':'warning'}>{result.reason}</Notice>
      <DataTable rows={result.predictions?.map(p=>({condition:p.condition,global_score_pct:p.score*100}))}/>
      {result.warnings.map((w,i)=><p className="muted" key={i}>{w}</p>)}
      <button className="btn" onClick={()=>download('astra-bio-leaf-screening.json',result)}>Export screening evidence</button></section>}
  </>;
}
function Telemetry({notify}) {
  const [source,setSource]=useState('hardware'),[device,setDevice]=useState(''),[data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;let controller;
    const refresh=async()=>{controller=new AbortController();try{const response=await fetch('/api/telemetry?source='+source+(device?'&device_id='+encodeURIComponent(device):''),{signal:controller.signal});if(!response.ok)throw new Error('Telemetry unavailable');const result=await response.json();if(active){setData(result);setError('');}}catch(e){if(active&&e.name!=='AbortError')setError(e.message);}};
    setData(null);refresh();const timer=setInterval(refresh,10000);return()=>{active=false;clearInterval(timer);controller?.abort();};
  },[source,device]);
  const latest=data?.latest,devices=data?.streams.filter(s=>s.source===source)||[];
  return <><Title eyebrow="ENVIRONMENTAL OBSERVATIONS" description="Readings refresh every 10 seconds. Selecting a stream never reruns the planner or sends a device command.">Live tray</Title>
    <section className="panel"><div className="section-heading"><h2>Choose a sensor stream</h2><span className="pill">Outputs disabled</span></div><div className="form-grid">
      <label className="field"><span>Telemetry source</span><select value={source} onChange={e=>{setSource(e.target.value);setDevice('');}}><option value="hardware">Physical hardware</option><option value="synthetic">Synthetic test / replay</option></select></label>
      <label className="field"><span>Device</span><select value={device||data?.device_id||''} onChange={e=>setDevice(e.target.value)}><option value="">Select a stream</option>{devices.map(s=><option key={s.device_id}>{s.device_id}</option>)}</select></label></div>
      <Notice tone={data?.mqtt.connected?'':'warning'}>{data?.mqtt.connected?'MQTT collector connected':'Collector connection unknown, stale or offline'}. Sensor receipt and freshness are checked separately. {data?.mqtt.lan_host&&'Tray TLS endpoint: '+data.mqtt.lan_host+':8883'}</Notice>
      {source==='synthetic'&&<Notice tone="warning">SYNTHETIC {data?.metadata.transport==='mqtt'?'MQTT TEST':'REPLAY'} — generated readings do not come from physical sensors.</Notice>}
      {error&&<Notice tone="warning">{error}</Notice>}
      {!latest?<div className="empty-state"><Radio size={28}/><h2>No measurements for this stream.</h2><p>Connect a device or choose a synthetic stream. Availability alone is not a sensor reading.</p></div>:
        <><Notice tone={data.age_seconds==null||data.age_seconds>120||data.age_seconds< -5||data.availability?.status==='offline'?'warning':''}>
          Last packet: {data.age_seconds==null?'unknown age':data.age_seconds< -5?'future timestamp; check clock':Math.max(0,Math.round(data.age_seconds))+' seconds ago'} · Last reported availability: {data.availability?.status||'unknown'}.
          {data.age_seconds>120&&' Stale readings; the device may be offline.'}</Notice>
        <div className="metrics-row"><Metric label="Air temperature" value={latest.air_temp_c==null?'Unavailable':pretty(latest.air_temp_c)+' °C'}/><Metric label="Relative humidity" value={latest.relative_humidity_pct==null?'Unavailable':pretty(latest.relative_humidity_pct)+'%'}/><Metric label="Solution temperature" value={latest.solution_temp_c==null?'Unavailable':pretty(latest.solution_temp_c)+' °C'}/><Metric label="Measured DC power" value={latest.bus_power_w==null?'Unavailable':pretty(latest.bus_power_w)+' W'}/></div>
        <Notice tone={latest.low_water?'warning':''}>{latest.low_water==null?'Low-water signal unavailable.':latest.low_water?'Low-water signal present. Inspect the tray.':'No low-water signal in this record; sufficient habitat water is not established.'}</Notice>
        <Chart data={data.history.map(r=>({...r,day:r.ts_utc.slice(11,19)}))} lines={[{key:'air_temp_c',name:'Air °C'},{key:'solution_temp_c',name:'Solution °C'}]}/>
        <p className="muted">Lux is a light trend, not calibrated PPFD. DC power excludes uninstrumented equipment. Packet freshness does not establish sensor calibration.</p>
        <button className="btn" onClick={()=>download('astra-bio-telemetry.csv',csv(data.history),'text/csv')}>Export selected stream CSV</button></>}
    </section><details className="panel"><summary>Hardware integration commands</summary><pre>{'.\\setup-mqtt.ps1\n.\\provision-device.ps1 -DeviceId tray-01\n.\\run-stack.ps1'}</pre><p className="muted">Firmware is built but unflashed. Configure private Wi-Fi details, validate wiring and sensor units, then flash and bench-test the physical tray. Outputs remain disabled.</p></details></>;
}
function Saved({config,setConfig,setRun,notify,navigate}) {
  const [name,setName]=useState('My habitat configuration'),[configs,setConfigs]=useState([]),[runs,setRuns]=useState([]),[busy,setBusy]=useState(false);
  async function refresh(){const [c,r]=await Promise.all([request('/snapshots/config'),request('/snapshots/run')]);setConfigs(c);setRuns(r);}
  useEffect(()=>{refresh().catch(e=>notify(e.message,true));},[]);
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="LOCAL HISTORY" description="Named configurations and complete model runs persist locally. A restored run keeps its recorded scenario, inputs and calculated results.">Saved workspace</Title>
    <section className="panel"><h2>Save this configuration</h2><div className="inline-form"><Field type="text" label="Configuration name" value={name} onChange={setName}/><button className="btn primary" disabled={busy} onClick={()=>task(async()=>{await request('/snapshots/config',{name,config});await refresh();notify('Configuration saved locally.');})}>Save configuration</button><button className="btn" onClick={()=>download('astra-bio-config.json',{schema_version:1,config})}>Export JSON</button></div>
      <label className="field upload-field"><span>Import a configuration JSON</span><input type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files[0];if(!file)return;task(async()=>{if(file.size>12*1024*1024)throw new Error('Configuration exceeds 12 MB.');const imported=JSON.parse(await file.text());if(imported.schema_version!==1)throw new Error('Unsupported configuration schema.');const result=await request('/config/validate',{config:imported.config});setConfig(result.config);});}}/></label></section>
    <section className="panel"><h2>Saved configurations</h2>{configs.length?configs.map(c=><div className="archive-row" key={c.id}><div><strong>{c.name}</strong><small>{new Date(c.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={busy} onClick={()=>task(async()=>{const item=await request('/snapshots/config/'+c.id);const result=await request('/config/validate',{config:item.config});setConfig(result.config);})}>Restore configuration</button></div>):<p className="muted">Save a configuration to reuse it later.</p>}</section>
    <section className="panel"><h2>Completed comparisons</h2>{runs.length?runs.map(r=><div className="archive-row" key={r.id}><div><strong>{r.name}</strong><small>{new Date(r.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={busy} onClick={()=>task(async()=>{const metadata=await request('/snapshots/run/'+r.id);setConfig(metadata.config);setRun({metadata});navigate('simulator');notify('Restored the saved result without rerunning the solver.');})}>Open saved run</button><button className="text-button" onClick={()=>task(async()=>download('astra-bio-saved-run.json',await request('/snapshots/run/'+r.id)))}>Export</button></div>):<p className="muted">Successful simulator comparisons are saved automatically.</p>}</section>
    <details className="panel"><summary>Current input provenance</summary><pre>{JSON.stringify(config.input_provenance,null,2)}</pre></details>
  </>;
}

export { App, Field, DataTable, Chart };
if (document.getElementById('root')) createRoot(document.getElementById('root')).render(<App/>);
