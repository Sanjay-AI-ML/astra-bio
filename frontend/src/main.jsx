import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowRight, ArrowUpRight, Beaker, Check, ChevronRight, CircleHelp, Eye, Layers3, Leaf, Menu, Radio, Search, Settings2, Sprout, Utensils, X } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ReferenceLine } from 'recharts';
import NutritionPanel from './NutritionPanel.jsx';
import HabitatOverview from './HabitatOverview.jsx';
import CommandPalette from './CommandPalette.jsx';
import ModelEvidence from './ModelEvidence.jsx';
import PlantOverview from './PlantOverview.jsx';
import CameraImages from './CameraImages.jsx';
import RecoveryPanel from './RecoveryPanel.jsx';
import CropAdvisor from './CropAdvisor.jsx';
import MissionChangePanel from './MissionChangePanel.jsx';
import BioProduction from './BioProduction.jsx';
import {validateCrewRoster} from './crew-roster.js';
import {initialNutritionRoster, missionCrewContext} from './mission-crew.js';
import {currentCrewState, readNutritionDraft} from './crew-state.js';
import { useTelemetry } from './useTelemetry.js';
import astraLogo from './assets/astra-bio-logo.png';
import './style.css';
import {apiUrl, readApiResponse} from './api-url.js';

export async function request(path, body) {
  const multipart = body instanceof FormData;
  const url = apiUrl('/api' + path);
  const response = await fetch(url, {method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined || multipart ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body)});
  return readApiResponse(response, url);
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
function Chart({data, lines, unit = '', height = 270, reference, focusDay, eventDay, labelPrefix = 'Mission day'}) {
  const ticks=data?.length>12?[...new Set(Array.from({length:7},(_,i)=>data[Math.round(i*(data.length-1)/6)].day))]:undefined;
  return <div className="chart" style={{height}}><ResponsiveContainer width="100%" height="100%">
    <LineChart data={data}><CartesianGrid stroke="var(--line-soft)" vertical={false}/><XAxis dataKey="day" ticks={ticks} minTickGap={18} interval="preserveStartEnd" tick={{fill:'var(--muted)',fontSize:13}} axisLine={false} tickLine={false}/>
      <YAxis unit={unit} tick={{fill:'var(--muted)',fontSize:13}} axisLine={false} tickLine={false} width={55}/>
      <Tooltip contentStyle={{background:'var(--surface-high)',border:'1px solid var(--line)',borderRadius:12,color:'var(--text)'}} labelFormatter={value=>labelPrefix+' '+value} formatter={v => pretty(v) + unit}/>
      <Legend iconType="plainline" wrapperStyle={{fontSize:13,paddingTop:14}}/>
      {reference!=null&&<ReferenceLine y={reference} stroke="var(--muted)" strokeDasharray="4 4"/>}
      {eventDay!=null&&data?.some(row=>row.day===eventDay)&&<ReferenceLine x={eventDay} stroke="var(--warning)" strokeDasharray="3 5"/>}
      {focusDay!=null&&data?.some(row=>row.day===focusDay)&&<ReferenceLine x={focusDay} stroke="var(--accent)" strokeWidth={1.5}/>}
      {lines.map((line,i) => <Line key={line.key} type="linear" dataKey={line.key} name={line.name} stroke={line.color || ['var(--green)','var(--chart-blue)','var(--chart-gold)'][i]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/>)}
    </LineChart></ResponsiveContainer></div>;
}
const NAV = [
  ['overview','Mission overview',Layers3],['crew','Crew & nutrition',Activity],
  ['production','Biological production',Beaker],['crops','Crops & food',Sprout],['simulator','What-if simulator',Settings2],
  ['leaf','Leaf screening',Leaf],['fruit','Fruit checking',Eye],['telemetry','Live devices',Radio],
];
const SETTINGS = ['settings','Workspace settings',Settings2];
const PAGE_GROUP = {inputs:'crew',pantry:'crops',models:'settings'};
function currentPage() {
  const hash = location.hash.slice(1);
  const aliases = {nutrition:'crew',research:'models',archive:'settings','crew-inputs':'inputs',vision:'fruit'};
  const page = aliases[hash] || hash;
  return [...NAV,SETTINGS].some(([key]) => key === page) || page in PAGE_GROUP ? page : 'overview';
}

function App() {
  const [bootstrap,setBootstrap] = useState(null), [config,updateConfig] = useState(null), [run,setRun] = useState(null);
  const [planPolicy,setPlanPolicy] = useState('adaptive');
  const [missionDay,setMissionDay] = useState(1);
  const [crewProfiles,setCrewProfiles] = useState([]);
  const [crewState,setCrewState] = useState(null);
  const [crewPlanningBusy,setCrewPlanningBusy] = useState(false);
  const [page,setPage] = useState(currentPage), [message,setMessage] = useState(null);
  const [initialError,setInitialError] = useState('');
  const [menuOpen,setMenuOpen] = useState(false);
  const [searchOpen,setSearchOpen] = useState(false);
  const menuToggle = useRef(null), navigationRef = useRef(null), bootstrapRun = useRef(null);
  useEffect(() => { request('/bootstrap').then(data => {
    const saved=readNutritionDraft(),profiles=saved?.profiles||initialNutritionRoster(data),sample=saved?saved.sample:data.crew_sample;
    setBootstrap(data); updateConfig(data.config);setCrewProfiles(profiles);
    setCrewState(currentCrewState({profiles,entries:saved?.entries||sample?.entries||[],complete_days:saved?.complete_days||sample?.complete_days||{},sample}));
    if(data.last_run){bootstrapRun.current=data.last_run;setRun(data.last_run);}
  }).catch(e => setInitialError(e.message)); }, []);
  useEffect(()=>{if(run?.metadata?.config){updateConfig(run.metadata.config);setMissionDay(v=>run.metadata.continuation?Math.max(v,run.metadata.continuation.next_day):1);
    const members=missionCrewContext(run,run.metadata.config,run.metadata.continuation?.next_day||1).members;
    if(members.length&&run!==bootstrapRun.current)setCrewProfiles(members);
    bootstrapRun.current=null;
  }},[run]);
  useEffect(() => { const change = () => {setPage(currentPage());setMenuOpen(false);}; window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  useEffect(() => {document.documentElement.scrollTop=0;document.body.scrollTop=0;},[page]);
  useEffect(()=>{const shortcut=event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();setMenuOpen(false);setSearchOpen(v=>!v);}};window.addEventListener('keydown',shortcut);return()=>window.removeEventListener('keydown',shortcut);},[]);
  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    navigationRef.current?.querySelector('a[aria-current="page"]')?.focus();
    const resize = () => {if(window.innerWidth>780)setMenuOpen(false);};
    const close = event => {
      if (event.key === 'Escape') {setMenuOpen(false);menuToggle.current?.focus();}
      if (event.key === 'Tab') {
        const items = [...navigationRef.current?.querySelectorAll('a,button') || []];
        const index = items.indexOf(document.activeElement);
        if (event.shiftKey && index === 0) {event.preventDefault();items.at(-1)?.focus();}
        else if (!event.shiftKey && index === items.length-1) {event.preventDefault();items[0]?.focus();}
      }
    };
    window.addEventListener('keydown',close);
    window.addEventListener('resize',resize);
    return () => {document.body.style.overflow=previousOverflow;window.removeEventListener('keydown',close);window.removeEventListener('resize',resize);};
  },[menuOpen]);
  const notify = (text, error = false) => setMessage({text,error});
  const setConfig = value => {updateConfig(value); setRun(null); notify('Inputs updated. Run the simulator to evaluate this configuration.');};
  const navigate = key => {location.hash = key;setPage(currentPage());if(menuOpen)document.getElementById('main-content')?.focus();setMenuOpen(false);};
  async function applyNutritionCrew(profiles,{through_day=missionDay}={}) {
    const error=validateCrewRoster(profiles);
    if(error)throw new Error(error);
    if(crewPlanningBusy)throw new Error('Wait for the current crew update to finish.');
    setCrewPlanningBusy(true);
    try {
      const reviewed=profiles.map(profile=>({...copy(profile),name:profile.name.trim()}));
      let result;
      if(run?.metadata) {
        result=await request('/plans/continue',{...(run.history_id?{run_id:run.history_id}:{metadata:run.metadata}),through_day,
          mission_change:{crew_profiles:reviewed,replace_future_crew_changes:true,reason:'Reviewed crew roster and targets from Crew & nutrition'}});
      } else {
        const freshConfig={...copy(config),crew:reviewed.length,crew_profiles:[],planning_events:[]};
        if(freshConfig.input_provenance){delete freshConfig.input_provenance.simulation_continuation;delete freshConfig.input_provenance.rolling_demo;}
        const response=await request('/nutrition/apply-targets',{config:freshConfig,profiles:reviewed});
        result=await request('/plans',{config:response.config,scenario:{...copy(bootstrap.presets.nominal),event_day:response.config.days+1,extra_crew:0,water_factor:1,power_factor:1,target_factors:{},failed_crop_ids:[],crop_yield_factors:{},name:'Named crew mission · no scheduled changes'}});
      }
      if(!result.metadata?.adaptive?.daily?.length)throw new Error('The crew plan did not complete. The previous saved plan remains available.');
      setMissionDay(run?.metadata?through_day+1:1);
      setCrewProfiles(reviewed);setRun(result);setPlanPolicy('adaptive');navigate('overview');
      notify(result.history_warning || 'The mission now uses these '+reviewed.length+' crew profiles and their reviewed nutrient targets.',!!result.history_warning);
      return result;
    } finally {setCrewPlanningBusy(false);}
  }
  if (!bootstrap || !config) return <main className="loading"><img className="loading-logo" src={astraLogo} alt="ASTRA-BIO" width={1536} height={1024}/><p>{initialError || 'Opening the planning workspace…'}</p>{initialError && <button onClick={() => location.reload()}>Retry connection</button>}</main>;
  const setPlantModel = plant_model => setBootstrap(v=>({...v,plant_model}));
  const activeCrewContext=missionCrewContext(run,config,missionDay);
  const context = {config,setConfig,bootstrap,request,notify,run,setRun,navigate,planPolicy,setPlanPolicy,missionDay,setMissionDay,setPlantModel,crewProfiles,crewState,onProfilesChange:setCrewProfiles,onCrewStateChange:setCrewState,
    activeCrewContext,missionCrewProfiles:activeCrewContext.members,onApplyCrew:applyNutritionCrew,crewPlanningBusy};
  const group = PAGE_GROUP[page] || page;
  const current = [...NAV, SETTINGS].find(n => n[0] === group) || NAV[0];
  const mixedInputs = Object.keys(config.input_provenance || {}).length > 0;
  const tabs = group==='crew' ? [['crew','Nutrition & logs'],['inputs','Mission inputs']] : group==='crops' ? [['crops','Crop schedules'],['pantry','Food inventory']] : group==='settings' ? [['settings','Saved plans'],['models','Model settings']] : null;
  const commandDetails={overview:'Explore saved results by mission day.',crew:'Review crew targets and recorded intake.',production:'Compare microbial protein, assisted plants and catalyst research against mission resources.',crops:'Inspect planting and harvest schedules.',simulator:'Prepare a disruption and compare policies.',leaf:'Screen a close-up photograph of one leaf.',fruit:'Check visible fruit and maturity in a plant photograph.',telemetry:'Inspect physical or synthetic device streams.',inputs:'Edit crew, nutrition and resource budgets.',pantry:'Review stored food and expiry policies.',settings:'Restore saved configurations and runs.',models:'Review crop references, calibration and model assumptions.'};
  const commands=[...NAV.map(([id,label])=>({id,label})),{id:'inputs',label:'Mission inputs'},{id:'pantry',label:'Food inventory'},{id:'settings',label:'Saved plans'},{id:'models',label:'Model settings'}].map(command=>({...command,description:commandDetails[command.id],keywords:command.id==='pantry'?config.foods.map(f=>f.name).join(' '):command.id==='crops'?config.crops.map(c=>c.name).join(' '):command.id==='models'?'calibration references research assumptions':command.id==='telemetry'?'mqtt iot sensors hardware':'',onSelect:()=>navigate(command.id)}));
  return <div className={'app-shell'+(menuOpen?' menu-open':'')}>
    <CommandPalette commands={commands} open={searchOpen} onClose={()=>setSearchOpen(false)}/>
    <a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus();}}>Skip to workspace</a>
    <button className="sidebar-scrim" aria-label="Close navigation" tabIndex={-1} onClick={()=>{setMenuOpen(false);menuToggle.current?.focus();}}/>
    <aside className="sidebar" id="habitat-navigation" ref={navigationRef}><a className="brand brand-with-logo" href="#overview" aria-label="ASTRA-BIO mission overview" onClick={()=>navigate('overview')}><img className="brand-logo-lockup" src={astraLogo} alt="ASTRA-BIO" width={1536} height={1024}/><small>Planning workspace</small></a><button className="drawer-close" aria-label="Close navigation drawer" onClick={()=>{setMenuOpen(false);menuToggle.current?.focus();}}><X size={19}/></button>
      <div className="sidebar-label">WORKSPACE</div><nav aria-label="Workspace navigation">{NAV.map(([key,label,Icon]) =>
        <a href={'#'+key} key={key} onClick={()=>navigate(key)} className={group===key?'active':''} aria-current={group===key?'page':undefined}><Icon size={18}/><span>{label}</span>{group===key && <ChevronRight size={14}/>}</a>)}</nav>
      <nav aria-label="Workspace settings" className="secondary-navigation"><a href="#settings" onClick={()=>navigate('settings')} className={group==='settings'?'active':''} aria-current={group==='settings'?'page':undefined}><Settings2 size={18}/><span>Workspace settings</span></a></nav>
      <div className="sidebar-bottom"><span className="sidebar-label">MISSION CONTEXT</span><strong>{run?.metadata?.adaptive?.daily?.find(row=>row.day===missionDay)?.crew || config.crew} crew · Day {missionDay} / {config.days}</strong><small>{pretty(run?.metadata?.adaptive?.daily?.find(row=>row.day===missionDay)?.area_available_m2 ?? config.area_m2)} m² growing area</small></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-title"><button className="mobile-menu-toggle" ref={menuToggle} aria-label={menuOpen?'Close workspace navigation':'Open workspace navigation'} aria-expanded={menuOpen} aria-controls="habitat-navigation" onClick={()=>setMenuOpen(v=>!v)}>{menuOpen?<X size={20}/>:<Menu size={20}/>}</button><span className="logo-emblem" aria-hidden="true"><img src={astraLogo} alt=""/></span><span>Workspace <ChevronRight size={14}/> <strong>{current[1]}</strong></span></div><button className="workspace-search" aria-label="Search workspace" aria-keyshortcuts="Control+K Meta+K" onClick={()=>{setMenuOpen(false);setSearchOpen(true);}}><Search size={17}/><span className="workspace-search-label">Search workspace</span><kbd>Ctrl K</kbd></button><div className="header-status"><span className={'status-chip '+(mixedInputs?'mixed':'demo')}>{mixedInputs?'Mixed inputs':'Demo inputs'}</span><span className="status-chip">Actuation disabled</span></div></header>
      <main className="content" id="main-content" tabIndex={-1}>
        {message && <div className={'toast '+(message.error?'error':'')} role={message.error?'alert':'status'}><span>{message.text}</span><button aria-label="Dismiss notification" onClick={() => setMessage(null)}><X size={16}/></button></div>}
        {tabs&&<nav className="workspace-tabs" aria-label={current[1]+' sections'}>{tabs.map(([key,label])=><a key={key} href={'#'+key} onClick={()=>navigate(key)} className={page===key?'active':''} aria-current={page===key?'page':undefined}>{label}</a>)}</nav>}
        {page === 'overview' && <HabitatOverview {...context} Chart={Chart}/>}
        <section hidden={!['inputs','pantry'].includes(page)}><Inputs {...context} inventory={page==='pantry'}/></section>
        <section hidden={page !== 'crew'}><NutritionPanel {...context}/></section>
        {page === 'crops' && <Crops {...context}/>}
        {page === 'production' && <BioProduction {...context}/>}
        {page === 'models' && <AdvancedSettings {...context}/>}
        {page === 'simulator' && <Simulator {...context}/>}
        {page === 'leaf' && <Vision {...context} mode="leaf"/>}
        {page === 'fruit' && <Vision {...context} mode="fruit"/>}
        {page === 'telemetry' && <Telemetry {...context}/>}
        {page === 'settings' && <Saved {...context}/>}
      </main><footer>ASTRA-BIO <span>Decision support · No clinical diagnosis</span></footer>
    </div>
  </div>;
}
function Title({eyebrow, children, description, action}) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{children}</h1><p>{description}</p></div>{action}</div>;
}
function Inputs({config,setConfig,bootstrap,notify,inventory=false}) {
  const [draft,setDraft] = useState(copy(config)), [busy,setBusy] = useState(false);
  useEffect(()=>setDraft(copy(config)),[config]);
  const set = (key,value) => setDraft(v => ({...v,[key]:value,...(['crew','targets_per_crew'].includes(key)?{crew_profiles:[]}:{} )}));
  const food = (i,key,value) => setDraft(v => ({...v,foods:v.foods.map((f,index)=>index===i?{...f,[key]:value}:f)}));
  async function submit(e) {e.preventDefault(); setBusy(true);try {const result=await request('/config/validate',{config:draft});setConfig(result.config);}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow={inventory?'FOOD AVAILABLE TODAY':'PLANNING INPUTS'} description={inventory?'Manage stored food, declared shelf life and reserve eligibility. Future harvests stay separate from food available today.':'Set crew, reviewed targets and resource budgets. Saving changes clears the previous comparison.'}>{inventory?'Food inventory':'Mission inputs'}</Title>
    <form onSubmit={submit}>{!inventory&&<><section className="panel"><h2>Mission configuration</h2><div className="form-grid">
      <Field label="Crew members" value={draft.crew} min={1} max={12} step={1} onChange={v=>set('crew',v)}/>
      <Field label="Horizon (days)" value={draft.days} min={7} max={180} step={1} onChange={v=>set('days',v)}/>
      <Field label="Reserve buffer (days)" value={draft.reserve_days} min={0} max={30} onChange={v=>set('reserve_days',v)}/>
      <Field label="Growing area (m²)" value={draft.area_m2} min={0} onChange={v=>set('area_m2',v)}/>
      <Field label="Water budget (L/day)" value={draft.water_budget_l_per_day} min={0} onChange={v=>set('water_budget_l_per_day',v)}/>
      <Field label="Energy budget (kWh/day)" value={draft.power_budget_kwh_per_day} min={0} onChange={v=>set('power_budget_kwh_per_day',v)}/>
      <label className="field"><span>Total usable mission water (L; optional)</span><input type="number" min={0} step="any" value={draft.initial_water_l ?? ''} placeholder="Daily allowance only" onChange={e=>set('initial_water_l',e.target.value===''?null:Number(e.target.value))}/></label>
      <label className="field"><span>Total mission electricity allowance (kWh; optional)</span><input type="number" min={0} step="any" value={draft.initial_energy_kwh ?? ''} placeholder="Daily allowance only" onChange={e=>set('initial_energy_kwh',e.target.value===''?null:Number(e.target.value))}/></label>
      <Field label="Crew water (L/person/day)" value={draft.crew_water_l_per_day} min={0} onChange={v=>set('crew_water_l_per_day',v)}/>
      <Field label="Fresh food limit (kg/person/day)" value={draft.max_fresh_kg_per_crew_day} min={0} onChange={v=>set('max_fresh_kg_per_crew_day',v)}/>
    </div><p className="muted">Optional totals add cumulative resource limits, carried into later replans. A daily allowance is a rate, not remaining tank volume. Use net makeup water consistently; recycling, energy replenishment, cooking water and a complete oxygen/CO₂ loop are outside this model.</p></section>
    <section className="panel"><h2>Daily dietary targets</h2><div className="form-grid">{Object.keys(draft.targets_per_crew).map(n =>
      <Field key={n} label={n.replaceAll('_',' ')+' ('+draft.nutrient_units[n]+')'} value={draft.targets_per_crew[n]} min={.001} onChange={v=>set('targets_per_crew',{...draft.targets_per_crew,[n]:v})}/>)}</div>
      <Notice>Targets are user-reviewed planning inputs. Intake gaps do not establish a clinical deficiency; only three nutrients are tracked.</Notice></section></>}
    {inventory&&<section className="panel"><div className="section-heading"><h2>Stored-food inventory</h2><span className="pill">kg of catalogued food form</span></div>
      <div className="table-wrap"><table><thead><tr><th>Food</th><th>Stock (kg)</th><th>Reserve eligible</th><th>Shelf life (days)</th><th>Initial age (days)</th><th>Vitamin C half life (days)</th></tr></thead><tbody>{draft.foods.map((f,i)=>
        <tr key={f.id}><td>{f.name}</td><td><input aria-label={f.name+' stock'} type="number" min={0} step="any" value={f.initial_kg} onChange={e=>food(i,'initial_kg',Number(e.target.value))}/></td>
          <td><input aria-label={f.name+' reserve eligible'} type="checkbox" checked={f.is_reserve} onChange={e=>food(i,'is_reserve',e.target.checked)}/></td>
          <td><input aria-label={f.name+' shelf life'} type="number" min={0} step={1} value={f.shelf_life_days||0} onChange={e=>food(i,'shelf_life_days',Number(e.target.value)||null)}/></td>
          <td><input aria-label={f.name+' initial age'} type="number" min={0} step={1} value={f.initial_age_days} onChange={e=>food(i,'initial_age_days',Number(e.target.value))}/></td>
          <td><input aria-label={f.name+' vitamin C half life'} type="number" min={0} step="any" value={f.nutrient_half_life_days.vitamin_c||0} onChange={e=>{const h={...f.nutrient_half_life_days};const v=Number(e.target.value);if(v)h.vitamin_c=v;else delete h.vitamin_c;food(i,'nutrient_half_life_days',h);}}/></td></tr>)}</tbody></table></div>
      <p className="muted">Shelf life 0 = unspecified. Half life 0 = fixed composition. Entered expiry is a stock policy; optional exponential retention is a sensitivity assumption requiring measured storage data, not a food-safety forecast. Reserve credit excludes food expiring within the buffer.</p></section>}
    {!inventory&&<details className="panel"><summary>Practical allocation limits</summary><div className="form-grid"><Field label="Planting increment (m²; 0 = continuous)" value={draft.planting_increment_m2} min={0} onChange={v=>set('planting_increment_m2',v)}/>
      <Field label="Food mass limit (kg/person/day; 0 = off)" value={draft.max_total_food_kg_per_crew_day} min={0} onChange={v=>set('max_total_food_kg_per_crew_day',v)}/>
      {Object.keys(draft.targets_per_crew).map(n => <Field key={n} label={n.replaceAll('_',' ')+' upper bound (0 = off)'} value={draft.nutrient_upper_per_crew[n]||0} min={0} onChange={v=>{const u={...draft.nutrient_upper_per_crew};if(v)u[n]=v;else delete u[n];set('nutrient_upper_per_crew',u);}}/>)}</div></details>}
    <div className="actions"><button className="btn primary" disabled={busy}>{busy?'Validating…':inventory?'Save food inventory':'Save planning inputs'}</button><button type="button" className="btn" onClick={()=>setDraft(copy(bootstrap.demo_config||bootstrap.config))}>Load demo into form</button></div></form>
  </>;
}
function RunMetrics({plan}) {
  const m=plan.metrics;return <div className="metrics-row"><Metric label="Days with nutrient gaps" value={m.shortfall_days} detail="Only tracked targets"/><Metric label="Total harvest" value={pretty(m.total_harvest_kg)+' kg'} detail="Simulated edible mass"/><Metric label="Water use" value={pretty(m.total_water_l)+' L'} detail="Crew plus crop model"/><Metric label="Electrical use" value={pretty(m.total_power_kwh)+' kWh'} detail="Configured crop coefficients"/></div>;
}
function Simulator({config,bootstrap,run,setRun,notify,missionDay,setMissionDay,crewProfiles,navigate,setPlanPolicy}) {
  const [s,setS] = useState(copy(bootstrap.presets.nominal)), [busy,setBusy] = useState(false), [day,setDay] = useState(1), [nutrient,setNutrient] = useState(Object.keys(config.targets_per_crew)[0]),[lossCrop,setLossCrop]=useState(''),[loss,setLoss]=useState(50),[targetIncrease,setTargetIncrease]=useState(0);
  const [localExplanation,setLocalExplanation]=useState(false),[model,setModel]=useState('llama3.2:3b'),[explanationText,setExplanationText]=useState(null);
  const [preset,setPreset]=useState('nominal');
  useEffect(()=>setExplanationText(null),[run]);
  const change=(k,v)=>{setPreset('');setS(prev=>({...prev,[k]:v}));};
  const choosePreset=key=>{const next=bootstrap.presets[key];if(!next)return;setS(copy(next));setPreset(key);const crop=Object.keys(next.crop_yield_factors||{})[0]||'';setLossCrop(crop);setLoss(crop?Math.round((1-next.crop_yield_factors[crop])*10000)/100:50);const target=Object.keys(next.target_factors||{})[0];if(target)setNutrient(target);setTargetIncrease(target?Math.round((next.target_factors[target]-1)*10000)/100:0);};
  async function solve(e) {e.preventDefault();setBusy(true);try {
    const scenario={...s,event_day:Math.min(s.event_day,config.days),crop_yield_factors:lossCrop?{[lossCrop]:1-loss/100}:{},target_factors:targetIncrease?{[nutrient]:1+targetIncrease/100}:{}};
    scenario.name='Day '+scenario.event_day+' · water '+Math.round(s.water_factor*100)+'% · power '+Math.round(s.power_factor*100)+'% · crew +'+s.extra_crew+(lossCrop?' · '+lossCrop+' yield −'+loss+'%':'')+(targetIncrease?' · '+nutrient+' target +'+targetIncrease+'%':'');
    const result=await request('/plans',{config,scenario});setRun(result);if(result.history_warning)notify(result.history_warning,true);else notify('Comparison complete. Inputs and results saved.');
  }catch(e){notify(e.message,true);}finally{setBusy(false);}}
  async function startNewMission(){
    if(busy)return;
    setBusy(true);
    const scenario={...copy(bootstrap.presets.nominal),event_day:config.days+1,water_factor:1,power_factor:1,extra_crew:0,target_factors:{},failed_crop_ids:[],crop_yield_factors:{},name:'New mission · no scheduled changes'};
    const freshConfig={...copy(config),planning_events:[]};
    if(freshConfig.input_provenance){delete freshConfig.input_provenance.simulation_continuation;delete freshConfig.input_provenance.rolling_demo;}
    try{
      const result=await request('/plans',{config:freshConfig,scenario});
      setRun(result);setMissionDay(1);setPlanPolicy('adaptive');setS(scenario);setPreset('nominal');setLossCrop('');setTargetIncrease(0);
      notify(result.history_warning||'New mission started at Day 1 with '+freshConfig.crew+' crew. Change the crew whenever needed from Mission overview.',!!result.history_warning);
      navigate('overview');
    }catch(failure){notify(failure.message,true);}finally{setBusy(false);}
  }
  const adaptive=run?.metadata.adaptive,baseline=run?.metadata.baseline;
  const rows=adaptive?.daily.map((r,i)=>({...r,adaptive:r[nutrient+'_coverage_pct'],fixed:baseline.daily[i]?.[nutrient+'_coverage_pct']}));
  return <><Title eyebrow="MISSION TRADE-OFFS" description="Compare a fixed plan with an adaptive plan under the same disruption.">What-if simulator</Title>
    <form className="panel" onSubmit={solve}><div className="section-heading"><h2>Define a disruption</h2><span className="pill">Event-day replan</span></div>
      <div className="scenario-presets" aria-label="Scenario starting points">{[['water','Water shortage'],['crop_loss','Crop loss'],['crew','Crew increase'],['targets','Dietary change'],['nominal','Nominal']].filter(([key])=>bootstrap.presets[key]).map(([key,label])=><button type="button" key={key} className={'scenario-preset'+(preset===key?' active':'')} aria-pressed={preset===key} onClick={()=>choosePreset(key)}>{label}</button>)}</div><p className="muted">Choose a starting point, adjust the inputs, then run the comparison.</p>
      <div className="form-grid"><Field label="Event day" value={Math.min(s.event_day,config.days)} min={1} max={config.days} step={1} onChange={v=>change('event_day',v)}/>
        <Field label="Daily water allowance (%)" value={Math.round(s.water_factor*100)} min={0} max={100} onChange={v=>change('water_factor',v/100)}/>
        <Field label="Daily electricity allowance (%)" value={Math.round(s.power_factor*100)} min={0} max={100} onChange={v=>change('power_factor',v/100)}/>
        <Field label="Additional crew" value={s.extra_crew} min={0} max={8} step={1} onChange={v=>change('extra_crew',v)}/>
        <label className="field"><span>Affected growing crop</span><select value={lossCrop} onChange={e=>{setPreset('');setLossCrop(e.target.value);}}><option value="">No crop loss</option>{config.crops.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <Field label="Active crop yield loss (%)" value={loss} min={0} max={100} onChange={v=>{setPreset('');setLoss(v);}}/>
        <label className="field"><span>Dietary target to change</span><select value={nutrient} onChange={e=>{setPreset('');setNutrient(e.target.value);}}>{Object.keys(config.targets_per_crew).map(n=><option key={n} value={n}>{n.replaceAll('_',' ')}</option>)}</select></label>
        <Field label="Target increase (%)" value={targetIncrease} min={0} max={100} onChange={v=>{setPreset('');setTargetIncrease(v);}}/></div>
      <div className="actions"><button className="btn primary" disabled={busy}>{busy?'Solving both policies…':'Run comparison'} <ArrowRight size={15}/></button><button className="btn" type="button" disabled={busy} onClick={startNewMission}>Start a new mission</button><small className="muted">Replacement crops require their full growth time.</small></div><p className="muted">A new mission starts at Day 1 with current starting inputs and no scheduled changes. Saved runs remain available.{config.planning_events?.length?' Comparison includes '+config.planning_events.length+' scheduled changes.':''}</p></form>
    {!run && <div className="empty-state"><h2>No saved comparison</h2><p>Submit a scenario to calculate food allocation, harvests and remaining resources.</p></div>}
    {run && <><Notice tone={adaptive.status==='feasible_with_shortfalls'?'warning':''}><strong>{adaptive.status==='feasible_with_shortfalls'?'Targets remain unmet in this model.':'Model run: '+adaptive.status}</strong> · {run.metadata.scenario.name}<br/><small>These results belong to submitted inputs at {new Date(run.metadata.created_at_utc).toLocaleString()}. Editing the scenario form does not change them.</small></Notice>
      <RunMetrics plan={adaptive}/>{adaptive.warnings.map((w,i)=><Notice key={i} tone="warning">{w}</Notice>)}
      <section className="panel"><div className="section-heading"><h2>{nutrient.replaceAll('_',' ')} coverage</h2><span className="pill">Day by day</span></div><Chart data={rows} unit="%" lines={[{key:'adaptive',name:'Adaptive plan'},{key:'fixed',name:'Fixed plan'}]}/></section>
      <div className="two-col"><section className="panel"><h2>Resource and reserve comparison</h2><DataTable rows={[
        ['shortfall_days','Days below tracked targets'],['total_water_l','Model water use (L)'],
        ['total_power_kwh','Model electricity use (kWh)'],['total_harvest_kg','Calculated harvest (kg)'],
        ['min_reserve_days','Minimum reserve (days)'],['total_waste_kg','Model food waste (kg)'],
        ['upper_bound_excess_days','Days above entered nutrient limits'],
      ].map(([key,label])=>({metric:label,fixed:baseline.metrics[key],adaptive:adaptive.metrics[key]}))}/></section>
        <section className="panel"><h2>Why the plan changed</h2>{run.explanation?.facts?.slice(0,8).map(f=><p className="fact" key={f.id}>{f.text}</p>)}<p className="muted">Explanations use saved model evidence. Resource-stress yield loss in the fixed plan remains a hypothetical proxy.</p>
          <details><summary>Local AI explanation</summary><label className="check-label"><input type="checkbox" checked={localExplanation} onChange={e=>setLocalExplanation(e.target.checked)}/>Use an installed Ollama model</label>
          {localExplanation&&<Field type="text" label="Installed Ollama model name" value={model} onChange={setModel}/>}</details>
          <button className="btn" onClick={async()=>{try{const e=await request('/explain',{metadata:run.metadata,ollama:localExplanation,model});setExplanationText(e);}catch(e){notify(e.message,true);}}}>Explain using verified facts</button>
          {explanationText&&<><p className="muted">{explanationText.mode} · {explanationText.fallback_reason||'Visible statements come from saved solver facts.'}</p><p className="fact">{explanationText.narrative}</p></>}
        </section></div>
      <MissionChangePanel run={run} config={config} sampleProfiles={crewProfiles} missionDay={missionDay} setMissionDay={setMissionDay} setRun={setRun} request={request} notify={notify} planningBusy={busy}/>
      <RecoveryPanel run={run} request={request} planningBusy={busy}/>
      <section className="panel"><div className="section-heading"><h2>Food allocation for a day</h2><Field label="Day" value={day} min={1} max={run.metadata.config.days} step={1} onChange={setDay}/></div>
        <DataTable rows={Object.entries(adaptive.consumption[day]||{}).filter(([,v])=>v>1e-6).map(([id,kg])=>({food:[...run.metadata.config.foods,...run.metadata.config.crops].find(f=>f.id===id)?.name||id,total_kg:kg,kg_per_crew:kg/(adaptive.daily[day-1]?.crew||1)}))}/>
        <p className="muted">Aggregate allocations for crew; cooking, recipes and individual menu preferences are outside this planner.</p></section>
      <details className="panel"><summary>Submitted inputs and provenance</summary><pre>{JSON.stringify({input_status:run.metadata.input_status,scenario:run.metadata.scenario,config:run.metadata.config},null,2)}</pre></details>
      <div className="actions"><button className="btn" onClick={()=>download('astra-bio-run.json',run.metadata)}>Export complete run</button><button className="btn" onClick={()=>download('astra-bio-daily.csv',csv([...baseline.daily.map(r=>({policy:'fixed',...r})),...adaptive.daily.map(r=>({policy:'adaptive',...r}))]),'text/csv')}>Export daily CSV</button></div>
    </>}</>;
}
function Crops({config,setConfig,run,setRun,notify,navigate,missionDay,setMissionDay,crewProfiles,crewState,planPolicy:policy,setPlanPolicy:setPolicy}) {
  const [draft,setDraft]=useState(copy(config.crops)),[busy,setBusy]=useState(false);
  useEffect(()=>setDraft(copy(config.crops)),[config.crops]);
  const keys=['grow_days','yield_kg_per_m2','water_l_per_m2_day','power_kwh_per_m2_day'];
  const labels=['Growth days','Edible yield kg/m²','Net water L/m²/day','Energy kWh/m²/day'];
  const plan=run?.metadata[policy];
  async function save(){setBusy(true);try{const provenance={...config.input_provenance};for(const crop of draft){if(JSON.stringify(crop)!==JSON.stringify(config.crops.find(c=>c.id===crop.id)))provenance['crop:'+crop.id+':user_edit']='User-edited endpoint/resource values override the loaded reference. Review these assumptions.';}const res=await request('/config/validate',{config:{...config,crops:draft,input_provenance:provenance}});setConfig(res.config);}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="HARVEST-AWARE SCHEDULING" description="Plan future food with explicit harvest delays. Fresh produce enters the food balance on its harvest day.">Crop schedules</Title>
    <CropAdvisor config={config} setConfig={setConfig} run={run} crewState={crewState} missionDay={missionDay} setMissionDay={setMissionDay} setRun={setRun} request={request} notify={notify} showContinuation={false}/>
    <MissionChangePanel run={run} config={config} sampleProfiles={crewProfiles} missionDay={missionDay} setMissionDay={setMissionDay} setRun={setRun} request={request} notify={notify} planningBusy={busy}/>
    <details className="panel"><summary>Crop profiles & assumptions</summary><div className="section-heading"><h2>Current crop coefficients</h2><button className="text-button" onClick={()=>navigate('models')}>Model settings <ArrowUpRight size={16}/></button></div>
      <div className="table-wrap"><table><thead><tr><th>Crop</th>{labels.map(l=><th key={l}>{l}</th>)}</tr></thead><tbody>{draft.map((c,i)=><tr key={c.id}><td>{c.name}</td>{keys.map(k=><td key={k}><input aria-label={c.name+' '+k} type="number" min={k==='grow_days'?1:0} step={k==='grow_days'?1:'any'} value={c[k]} onChange={e=>setDraft(v=>v.map((crop,index)=>index===i?{...crop,[k]:Number(e.target.value)}:crop))}/></td>)}</tr>)}</tbody></table></div>
      <div className="actions"><button className="btn primary" disabled={busy} onClick={save}>Save crop coefficients</button><small className="muted">Synthetic defaults stay labelled. Imported references keep their source provenance.</small></div></details>
    {!plan?<div className="empty-state"><h2>No saved harvest schedule</h2><p>Run the simulator to see planting dates and estimated harvests.</p><button className="btn" onClick={()=>navigate('simulator')}>Open simulator</button></div>:
      <section className="panel"><div className="section-heading"><h2>Planting and harvest timeline</h2><select aria-label="Schedule policy" value={policy} onChange={e=>setPolicy(e.target.value)}><option value="adaptive">Adaptive plan</option><option value="baseline">Fixed baseline</option></select></div>
        {policy==='baseline'&&<Notice tone="warning">Fixed planting and meals are replayed under the changed conditions. Batch estimates and daily harvest reflect modeled resource losses; the stress response is a synthetic proxy.</Notice>}
        <div className="timeline-axis"><span>Crop batch</span><div className="timeline-axis-scale"><span>Day 1</span><span>Day {Math.round(run.metadata.config.days/2)}</span><span>Day {run.metadata.config.days}</span></div><small>Estimate · harvest</small></div>
        <div className="timeline" tabIndex={0} aria-label="Planting and harvest batches">{plan.planting.slice(0,40).map((b,i)=><div className="timeline-row" key={i}><span>{b.crop}</span><div className="timeline-track"><div style={{left:((b.day-1)/Math.max(1,run.metadata.config.days-1)*100)+'%',width:((b.harvest_day-b.day)/Math.max(1,run.metadata.config.days-1)*100)+'%'}} title={'Day '+b.day+' → '+b.harvest_day}/></div><small>{pretty(b.predicted_harvest_kg)} kg · D{b.harvest_day}</small></div>)}</div>
        {plan.planting.length>40&&<p className="muted">Showing the first 40 timeline rows; the complete schedule is in the table and export.</p>}
        <DataTable rows={plan.planting} columns={['crop','day','harvest_day','area_m2','predicted_harvest_kg']}/>
        <button className="btn" onClick={()=>download('astra-bio-crops.csv',csv(plan.planting),'text/csv')}>Export planting schedule</button></section>}</>;
}
function AdvancedSettings({config,setConfig,bootstrap,notify}) {
  const refs=bootstrap.references,[reference,setReference]=useState(Object.keys(refs)[0]),[age,setAge]=useState(refs[Object.keys(refs)[0]].planning_grow_days),[area,setArea]=useState(1),[prediction,setPrediction]=useState(null);
  const [chosen,setChosen]=useState(['lettuce_batavia','radish_raxe']),[water,setWater]=useState(1.5),[efficacy,setEfficacy]=useState(2.5),[delivery,setDelivery]=useState(.8),[overhead,setOverhead]=useState(.15),[conservative,setConservative]=useState(false);
  const [observations,setObservations]=useState(bootstrap.observations),[holdouts,setHoldouts]=useState(['nasa_rlss_1992_cycle_2']),[fit,setFit]=useState(null),[sensitivity,setSensitivity]=useState(null),[busy,setBusy]=useState(false);
  const r=refs[reference];
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="MODEL SETTINGS" description="Optional crop references, harvest calibration and sensitivity tools. Open a section when you need to adjust assumptions.">Model settings</Title>
    <ModelEvidence request={request} notify={notify} Chart={Chart} focus="crops"/>
    <Notice>These controls change planning assumptions only when explicitly applied. Crop references come from terrestrial environments; transfer to a new tray or spaceflight is unvalidated.</Notice>
    <details className="panel"><summary>Crop reference details</summary><div className="section-heading" style={{marginTop:20}}><h2>A measured harvest endpoint</h2><span className="pill">Terrestrial controlled environment</span></div>
      <div className="form-grid"><label className="field"><span>Reference profile</span><select value={reference} onChange={e=>{setReference(e.target.value);setAge(refs[e.target.value].planning_grow_days);setPrediction(null);}}>{Object.values(refs).map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select></label>
        <Field label="Age from seeding (days)" value={age} min={0} onChange={setAge}/><Field label="Area (m²)" value={area} min={.01} onChange={setArea}/></div>
      <div className="metrics-row"><Metric label="Published fresh edible mean" value={r.yield_kg_per_m2+' kg/m²'}/><Metric label="Published mean cycle" value={r.grow_days+' days'}/><Metric label="Measured cycle count" value={r.reported_cycles}/><Metric label="Observed range" value={r.observed_min_kg_per_m2+'–'+r.observed_max_kg_per_m2+' kg/m²'}/></div>
      <a className="source-link" href={r.source_url} target="_blank" rel="noreferrer">Primary source · {r.source_table} <ArrowUpRight size={14}/></a>
      <p className="muted">{r.cultivar} · {r.ppfd_umol_m2_s} µmol/m²/s PPFD · {r.co2_ppm} ppm CO₂ · {r.cultivation_system}</p>
      <p className="muted">PPFD basis: {r.ppfd_basis}. {r.environment_notes}</p>
      <button className="btn" disabled={busy} onClick={()=>task(async()=>setPrediction(await request('/growth',{crop_id:reference,age_days:age,area_m2:area})))}>Calculate reference harvest</button>
      {prediction&&<Notice>Reference endpoint: {pretty(prediction.expected_harvest_kg)} kg. Available at the entered age: {pretty(prediction.available_harvest_kg)} kg. Intermediate growth was not fitted; observed bounds are experimental ranges, not prediction intervals.</Notice>}
    </details>
    <details className="panel"><summary>Load measured crop profiles</summary><div className="reference-options">{Object.values(refs).map(r=><label key={r.id}><input type="checkbox" checked={chosen.includes(r.id)} onChange={e=>setChosen(v=>e.target.checked?[...v,r.id]:v.filter(k=>k!==r.id))}/><span>{r.name}<small>{r.planning_grow_days} days · {r.yield_kg_per_m2} kg/m²</small></span></label>)}</div>
      <div className="form-grid"><Field label="Assumed net water (L/m²/day)" value={water} min={0} onChange={setWater}/><Field label="Assumed LED efficacy (µmol/J)" value={efficacy} min={.1} onChange={setEfficacy}/>
        <Field label="Photon delivery fraction" value={delivery} min={.01} max={1} onChange={setDelivery}/><Field label="Assumed overhead (kWh/m²/day)" value={overhead} min={0} onChange={setOverhead}/></div>
      <label className="check-label"><input type="checkbox" checked={conservative} onChange={e=>setConservative(e.target.checked)}/>Use observed minimum fresh yield</label>
      <Notice>Net makeup water and whole-system energy are missing from these references. Lighting uses reported PPFD/photoperiod and assumed efficiency; kohlrabi uses the reported range midpoint. Nursery stages are not resolved: final lighting and area apply across the whole cycle. HVAC/pump overhead is assumed. Applied irrigation is not net consumption. USDA composition is a species proxy.</Notice>
      <button className="btn primary" disabled={busy||!chosen.length} onClick={()=>task(async()=>{const result=await request('/config/research',{config,ids:chosen,water,efficacy,delivery,overhead,conservative});setConfig(result.config);})}>Apply measured crop references</button>
    </details>
    <details className="panel"><summary>Harvest calibration</summary><div className="section-heading" style={{marginTop:20}}><h2>Calibrate with measured harvests</h2><button className="text-button" onClick={()=>download('astra-bio-calibration-template.csv',csv(bootstrap.observations),'text/csv')}>Download observations / CSV template</button></div>
      <Notice>Published means count as summaries, not fabricated individual harvest cycles. The two NASA lettuce trials provide a small held-out diagnostic; they do not establish general prediction accuracy.</Notice>
      <label className="field upload-field"><span>Import your crop-cycle CSV</span><input type="file" accept=".csv,text/csv" onChange={e=>{const file=e.target.files[0];if(!file)return;task(async()=>{const form=new FormData();form.append('file',file);const result=await request('/calibrate/csv',form);setObservations(result.observations);setHoldouts([]);setFit(null);});}}/></label>
      <details><summary>Recorded observations ({observations.length})</summary><DataTable rows={observations} columns={['observation_id','crop_id','grow_days','area_m2','fresh_harvest_kg','observation_type']}/></details>
      <div className="holdouts"><p className="muted">Choose independent held-out cycles:</p>{observations.filter(o=>o.observation_type==='crop_cycle').map(o=><label className="check-label" key={o.observation_id}><input type="checkbox" checked={holdouts.includes(o.observation_id)} onChange={e=>setHoldouts(v=>e.target.checked?[...v,o.observation_id]:v.filter(k=>k!==o.observation_id))}/>{o.observation_id}</label>)}</div>
      <button className="btn primary" disabled={busy} onClick={()=>task(async()=>setFit(await request('/calibrate',{observations,holdout_ids:holdouts})))}>Fit endpoints and score holdouts</button>
      {fit&&<><DataTable rows={Object.values(fit.fit_parameters)} columns={['crop_id','yield_kg_per_m2','grow_days','training_cycle_count','training_summary_count']}/>
        {fit.validation?<Notice tone="warning">Held-out MAE: {pretty(fit.validation.mae_kg_per_m2)} kg/m² · MAPE: {pretty(fit.validation.mape_pct)}% · {fit.validation.holdout_record_count} cycle(s). {fit.validation.limitation}</Notice>:<Notice>Fit completed; no held-out accuracy is available for these data.</Notice>}
        <div className="actions"><button className="btn" onClick={()=>download('astra-bio-calibration.json',fit)}>Export calibration report</button><button className="btn" disabled={busy} onClick={()=>task(async()=>{const result=await request('/calibrate/apply',{config,observations,holdout_ids:holdouts});setConfig(result.config);})}>Apply fitted matching endpoints</button></div></>}
    </details>
    <details className="panel"><summary>Harvest sensitivity</summary><p className="muted">Low, mean and high cases use observed reference bounds. These are deterministic sensitivity cases, not confidence intervals. Apply measured crop profiles first.</p>
      <button className="btn" disabled={busy} onClick={()=>task(async()=>setSensitivity(await request('/sensitivity',{config})))}>{busy?'Calculating…':'Run harvest sensitivity'}</button>
      {sensitivity&&<DataTable rows={sensitivity.cases} columns={['case','status','shortfall_days','total_harvest_kg','total_water_l','total_power_kwh']}/>}</details>
  </>;
}
function Vision({mode='fruit'}) {
  const leaf=mode==='leaf';
  return <><Title eyebrow={leaf?'LEAF SCREENING':'FRUIT CHECKING'} description={leaf?'Upload one clear leaf close-up for a preliminary visual check.':'Upload a clear fruit photograph to check visible count and maturity.'}>{leaf?'Leaf screening':'Fruit checking'}</Title>
    <PlantOverview request={request} mode={mode}/>
  </>;
}
function Telemetry({notify,request}) {
  const [source,setSource]=useState('hardware'),[device,setDevice]=useState('');
  const {data,error}=useTelemetry(source,device);
  const latest=data?.latest,devices=data?.streams.filter(s=>s.source===source)||[];
  return <><Title eyebrow="ENVIRONMENTAL OBSERVATIONS" description="View device readings and when they last arrived.">Live devices</Title>
    <section className="panel"><div className="section-heading"><h2>Choose a sensor stream</h2></div><div className="form-grid">
      <label className="field"><span>Telemetry source</span><select value={source} onChange={e=>{setSource(e.target.value);setDevice('');}}><option value="hardware">Physical hardware</option><option value="synthetic">Synthetic test / replay</option></select></label>
      <label className="field"><span>Device</span><select value={device||data?.device_id||''} onChange={e=>setDevice(e.target.value)}><option value="">Select a stream</option>{devices.map(s=><option key={s.device_id}>{s.device_id}</option>)}</select></label></div>
      <Notice tone={(data?.storage?.backend==='mongodb'?data.storage.connected:data?.mqtt?.connected)&&!error?'':'warning'}>{data?.storage?.backend==='mongodb'?(error?'MongoDB telemetry refresh unavailable':'MongoDB telemetry connected'):data?.mqtt?.connected&&!error?'MQTT collector connected':'Collector connection unknown, stale or offline'}. {data?.storage?.backend!=='mongodb'&&data?.mqtt?.lan_host&&'Device endpoint: '+data.mqtt.lan_host+':8883'}</Notice>
      {source==='synthetic'&&<Notice tone="warning">SYNTHETIC {data?.metadata.transport==='mqtt'?'MQTT TEST':data?.metadata.transport==='https'?'WI-FI TEST':'REPLAY'} — generated readings do not come from physical sensors.</Notice>}
      {error&&<Notice tone="warning">{error}</Notice>}
      {!latest?<div className="empty-state"><Radio size={28}/><h2>No measurements for this stream.</h2><p>Connect a device or choose a test stream.</p></div>:
        <><Notice tone={data.age_seconds==null||data.age_seconds>120||data.age_seconds< -5||data.availability?.status==='offline'?'warning':''}>
          Last packet: {data.age_seconds==null?'unknown age':data.age_seconds< -5?'future timestamp; check clock':Math.max(0,Math.round(data.age_seconds))+' seconds ago'} · Last reported availability: {data.availability?.status||'unknown'}.
          {data.age_seconds>120&&' Stale readings; the device may be offline.'}</Notice>
        <div className="metrics-row"><Metric label="Air temperature" value={latest.air_temp_c==null?'Unavailable':pretty(latest.air_temp_c)+' °C'}/><Metric label="Relative humidity" value={latest.relative_humidity_pct==null?'Unavailable':pretty(latest.relative_humidity_pct)+'%'}/><Metric label="Solution temperature" value={latest.solution_temp_c==null?'Unavailable':pretty(latest.solution_temp_c)+' °C'}/><Metric label="Measured DC power" value={latest.bus_power_w==null?'Unavailable':pretty(latest.bus_power_w)+' W'}/></div>
        <Notice tone={latest.low_water?'warning':''}>{latest.low_water==null?'Low-water signal unavailable.':latest.low_water?'Low water detected. Inspect the tray.':'Tray low-water signal: clear.'}</Notice>
        <Chart data={data.history.map(r=>({...r,day:r.ts_utc.slice(11,19)}))} labelPrefix="Observation time (UTC)" lines={[{key:'air_temp_c',name:'Air °C'},{key:'solution_temp_c',name:'Solution °C'}]}/>
        <p className="muted">Lux is a light trend, not calibrated PPFD. DC power excludes uninstrumented equipment. Packet freshness does not establish sensor calibration.</p>
        <button className="btn" onClick={()=>download('astra-bio-telemetry.csv',csv(data.history),'text/csv')}>Export selected stream CSV</button></>}
    </section><CameraImages request={request}/><details className="panel"><summary>ESP32 Wi-Fi integration</summary><p>ESP32-S3 → HTTPS gateway → MongoDB Atlas → this workspace.</p><pre>{'.\\setup-mongodb.ps1 -DeviceId tray-01\n.\\.venv\\Scripts\\python.exe -m astra_bio.mongo_runtime check\n.\\run-gateway.ps1'}</pre><p className="muted">Use the private device header and sensor-specific firmware. Missing readings remain unavailable. The Atlas password stays on the backend. Outputs remain disabled.</p><details><summary>Existing MQTT integration</summary><pre>{'.\\setup-mqtt.ps1\n.\\provision-device.ps1 -DeviceId tray-01\n.\\run-stack.ps1'}</pre></details></details></>;
}
function Saved({config,setConfig,setRun,notify,navigate}) {
  const [name,setName]=useState('My habitat configuration'),[configs,setConfigs]=useState([]),[runs,setRuns]=useState([]),[busy,setBusy]=useState(false);
  async function refresh(){const [c,r]=await Promise.all([request('/snapshots/config'),request('/snapshots/run')]);setConfigs(c);setRuns(r);}
  useEffect(()=>{refresh().catch(e=>notify(e.message,true));},[]);
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <><Title eyebrow="WORKSPACE HISTORY" description="Save configurations or reopen a completed run with its original inputs and results.">Saved workspace</Title>
    <section className="panel"><h2>Save this configuration</h2><div className="inline-form"><Field type="text" label="Configuration name" value={name} onChange={setName}/><button className="btn primary" disabled={busy} onClick={()=>task(async()=>{await request('/snapshots/config',{name,config});await refresh();notify('Configuration saved.');})}>Save configuration</button><button className="btn" onClick={()=>download('astra-bio-config.json',{schema_version:1,config})}>Export JSON</button></div>
      <label className="field upload-field"><span>Import a configuration JSON</span><input type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files[0];if(!file)return;task(async()=>{if(file.size>12*1024*1024)throw new Error('Configuration exceeds 12 MB.');const imported=JSON.parse(await file.text());if(imported.schema_version!==1)throw new Error('Unsupported configuration schema.');const result=await request('/config/validate',{config:imported.config});setConfig(result.config);});}}/></label></section>
    <section className="panel"><h2>Saved configurations</h2>{configs.length?configs.map(c=><div className="archive-row" key={c.id}><div><strong>{c.name}</strong><small>{new Date(c.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={busy} onClick={()=>task(async()=>{const item=await request('/snapshots/config/'+c.id);const result=await request('/config/validate',{config:item.config});setConfig(result.config);})}>Restore configuration</button></div>):<p className="muted">Save a configuration to reuse it later.</p>}</section>
    <section className="panel"><h2>Completed comparisons</h2>{runs.length?runs.map(r=><div className="archive-row" key={r.id}><div><strong>{r.name}</strong><small>{new Date(r.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={busy} onClick={()=>task(async()=>{const metadata=await request('/snapshots/run/'+r.id);setConfig(metadata.config);setRun({metadata});navigate('simulator');notify('Restored the saved result without rerunning the solver.');})}>Open saved run</button><button className="text-button" onClick={()=>task(async()=>download('astra-bio-saved-run.json',await request('/snapshots/run/'+r.id)))}>Export</button></div>):<p className="muted">Successful simulator comparisons are saved automatically.</p>}</section>
    <details className="panel"><summary>Current input provenance</summary><pre>{JSON.stringify(config.input_provenance,null,2)}</pre></details>
  </>;
}

export { App, Field, DataTable, Chart };
if (document.getElementById('root')) createRoot(document.getElementById('root')).render(<App/>);
