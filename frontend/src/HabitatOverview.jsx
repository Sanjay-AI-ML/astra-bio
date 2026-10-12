import React, {useEffect, useRef, useState} from 'react';
import {Activity, ArrowRight, ArrowUpRight, ChevronRight, CircleHelp, Radio, Settings2} from 'lucide-react';
import {useTelemetry} from './useTelemetry.js';
import MissionExplorer, {PlanComparison, scenarioCrewCanceled} from './MissionExplorer.jsx';
import MissionChangePanel from './MissionChangePanel.jsx';

const number = value => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
function Metric({label,value,unit,detail,warning=false}) {
  return <div className={'ops-metric'+(warning?' warning':'')}><span>{label}</span><strong>{number(value)}{value!=null&&unit&&<small> {unit}</small>}</strong><small>{detail}</small></div>;
}
function ReviewItem({icon:Icon,title,detail,onClick}) {
  return <button className="ops-review-item" onClick={onClick}><Icon size={17}/><span><strong>{title}</strong><small>{detail}</small></span><ChevronRight size={16}/></button>;
}

export default function HabitatOverview({config,run,setRun,request,notify,crewProfiles=[],navigate,Chart,planPolicy:policy,setPlanPolicy:setPolicy,missionDay:selectedDay,setMissionDay:setSelectedDay}) {
  const [window,setWindow]=useState('full');
  const [chartView,setChartView]=useState('nutrients');
  const [editingCrew,setEditingCrew]=useState(false);
  const crewEditor=useRef(null);
  const {data:telemetry,error,fresh}=useTelemetry('hardware');
  const metadata=run?.metadata;
  const plan=metadata?.[policy];
  const savedConfig=metadata?.config||config;
  const mixed=Object.keys(savedConfig.input_provenance||{}).length>0;
  const metrics=plan?.metrics;
  const batches=[...(plan?.planting||[])].sort((a,b)=>a.harvest_day-b.harvest_day).slice(0,5);
  const eventDay=metadata?.scenario?.event_day;
  const daily=(plan?.daily||[]).filter(row=>window==='full'||eventDay==null||row.day>=eventDay);
  useEffect(()=>{if(daily.length&&!daily.some(row=>row.day===selectedDay))setSelectedDay(daily[0].day);},[plan,window,eventDay,selectedDay]);
  const selectDay=day=>{if(window==='event'&&day<eventDay)setWindow('full');setSelectedDay(day);};
  useEffect(()=>{if(editingCrew){crewEditor.current?.scrollIntoView?.({behavior:'smooth',block:'start'});crewEditor.current?.focus();}},[editingCrew]);
  function changeCrew(day){selectDay(day);setPolicy('adaptive');setEditingCrew(true);}
  const chartOptions={nutrients:{title:'Nutrient coverage',subtitle:'Daily modeled intake / target (%)',unit:'%',reference:100,lines:[{key:'energy_coverage_pct',name:'Energy'},{key:'protein_coverage_pct',name:'Protein'},{key:'vitamin_c_coverage_pct',name:'Vitamin C'}]},water:{title:'Water use and budget',subtitle:'Crew and crop model · L/day',unit:' L',lines:[{key:'water_l',name:'Modeled use'},{key:'water_available_l',name:'Available budget',color:'var(--chart-budget)'}]},power:{title:'Electricity use and budget',subtitle:'Configured crop coefficients · kWh/day',unit:' kWh',lines:[{key:'power_kwh',name:'Modeled use'},{key:'power_available_kwh',name:'Available budget',color:'var(--chart-budget)'}]}};
  const chart=chartOptions[chartView];
  const policyName=policy==='adaptive'?'Adaptive plan':'Fixed baseline';
  const deviceTitle=error?'Device status unavailable':!telemetry?'Checking device readings…':!telemetry.latest?'Awaiting device readings':fresh?'Recent hardware readings':'Hardware readings need review';
  const reviewItems=[];
  if(!plan) reviewItems.push({icon:Settings2,title:'Create a scenario comparison',detail:'No saved result to review yet.',destination:'simulator'});
  if(metrics?.shortfall_days>0) reviewItems.push({icon:Activity,title:number(metrics.shortfall_days)+' days below tracked targets',detail:'Review allocation and resource limits.',destination:'simulator'});
  if(plan?.warnings?.length) reviewItems.push({icon:CircleHelp,title:plan.warnings.length+' model '+(plan.warnings.length===1?'note':'notes'),detail:'Inspect assumptions and solver warnings.',destination:'simulator'});
  reviewItems.push({icon:CircleHelp,title:mixed?'Review combined input sources':'Demo coefficients in use',detail:mixed?'References and entered assumptions are combined.':'Review food, crop and dietary inputs.',destination:mixed?'models':'inputs'});
  if(!fresh) reviewItems.push({icon:Radio,title:error?'Device refresh unavailable':telemetry?.latest?'Hardware readings need review':'No hardware readings',detail:error?'Last readings may be retained; freshness is unknown.':telemetry?.latest?'Check receipt age and device availability.':'Connect a device to begin physical monitoring.',destination:'telemetry'});
  const receipt=telemetry?.age_seconds==null?'receipt age unknown':telemetry.age_seconds< -5?'future timestamp; check clock':Math.max(0,Math.round(telemetry.age_seconds))+'s since receipt';

  return <div className="ops-overview">
    <div className="ops-heading"><div><h1>Mission overview</h1><p>{savedConfig.crew} starting crew · {savedConfig.days} days · {number(savedConfig.area_m2)} m² growing area</p></div><div><button className="text-button" aria-label="Review mission inputs" onClick={()=>navigate('inputs')}>Review inputs <ArrowUpRight size={15}/></button><button className="btn primary" onClick={()=>navigate('simulator')}>Open what-if simulator <ArrowRight size={16}/></button></div></div>

    <div className="ops-run-status"><div><span className={'source-pill '+(mixed?'mixed':'demo')}>{mixed?'Mixed inputs':'Demo inputs'}</span><span>{plan?'Calculated result':'No saved result'}</span>{plan&&<span>{policyName} · {plan.status?.replaceAll('_',' ')}</span>}</div>{metadata?.created_at_utc&&<span>Submitted {new Date(metadata.created_at_utc).toLocaleString()}</span>}</div>
    {metadata?.scenario&&<p className="ops-footnote">Scenario: {metadata.scenario.name}{(metadata.continuation?.pending_scenario_crew_cancelled||scenarioCrewCanceled(metadata.scenario,savedConfig.planning_events))&&' · Original scheduled crew arrival replaced by the reviewed roster.'}</p>}
    <MissionExplorer plan={plan} scenario={metadata?.scenario} planningEvents={metadata?.config?.planning_events} policy={policy} selectedDay={selectedDay} onSelectDay={selectDay} navigate={navigate} onChangeCrew={changeCrew} editingCrew={editingCrew}/>
    {editingCrew&&<div className="overview-crew-editor" ref={crewEditor} tabIndex={-1}><div className="overview-crew-editor-status"><span>Simulation paused · edit the crew for the remaining mission</span><button className="btn" onClick={()=>setEditingCrew(false)}>Close crew editor</button></div><MissionChangePanel run={run} config={savedConfig} sampleProfiles={crewProfiles} missionDay={selectedDay} setMissionDay={selectDay} setRun={setRun} request={request} notify={notify}/></div>}
    <section className="ops-metrics" aria-label="Saved plan totals">
      <Metric label="Days below tracked targets" value={metrics?.shortfall_days} detail="Energy, protein and vitamin C" warning={metrics?.shortfall_days>0}/>
      <Metric label="Calculated harvest" value={metrics?.total_harvest_kg} unit="kg" detail="Estimated edible crop mass"/>
      <Metric label="Minimum stored-food reserve" value={metrics?.min_reserve_days} unit="days" detail={'Configured target: '+number(savedConfig.reserve_days)+' days'} warning={metrics?.min_reserve_days<savedConfig.reserve_days}/>
      <Metric label="Modeled water use" value={metrics?.total_water_l} unit="L" detail="Crew and crop model"/>
    </section>
    <p className="ops-footnote">{plan?policyName+' · whole-run totals for '+savedConfig.days+' days':'Metrics appear after a completed comparison. No model run starts automatically.'}</p>

    <div className="ops-grid">
      <section className="ops-panel ops-chart" aria-label="Plan charts"><div className="ops-panel-header"><h2>{chart.title}</h2><span>{chart.subtitle}</span></div>
        <div className="chart-tabs" aria-label="Chart metric">{[['nutrients','Nutrients'],['water','Water'],['power','Electricity']].map(([key,label])=><button key={key} className={chartView===key?'active':''} aria-pressed={chartView===key} onClick={()=>setChartView(key)}>{label}</button>)}</div>
        <div className="ops-chart-toolbar"><label>Plan<select aria-label="Overview plan" value={policy} onChange={e=>setPolicy(e.target.value)} disabled={!metadata}><option value="adaptive">Adaptive plan</option><option value="baseline">Fixed baseline</option></select></label><label>Period<select aria-label="Overview period" value={window} onChange={e=>setWindow(e.target.value)} disabled={!plan||eventDay==null}><option value="full">Full horizon</option><option value="event">From event day {eventDay??'—'}</option></select></label><span>Mission day{daily.length?' '+daily[0].day+'–'+daily.at(-1).day:''}</span></div>
        <div className="ops-panel-body">{daily.length?<><Chart data={daily} unit={chart.unit} height={260} reference={chart.reference} focusDay={selectedDay} eventDay={eventDay} lines={chart.lines}/><p className="ops-footnote">{chartView==='nutrients'?'Dashed line: 100% of target · ':''}{daily.length} modeled days · {chartView==='nutrients'?'intake gaps require review.':'use and budget are saved model values.'}</p><p className="chart-focus-caption">Selected day {selectedDay} · sage marker{eventDay!=null?' · scenario begins on day '+eventDay+' (amber)':''}</p></>:<div className="ops-empty"><h3>{plan?'No daily values in this result':'No completed comparison'}</h3><p>{plan?'Inspect the solver status in the simulator.':'Run a scenario to compare food allocation, future harvests and resource limits.'}</p></div>}</div>
      </section>
      <section className="ops-panel ops-review"><div className="ops-panel-header"><h2>Review items</h2><span className="ops-review-count">{reviewItems.length}</span></div><div className="ops-review-list">{reviewItems.map((item,index)=><ReviewItem key={index} {...item} onClick={()=>navigate(item.destination)}/>)}</div><p className="ops-footnote">Planning checks · no clinical diagnosis or automatic intervention.</p></section>
    </div>
    <PlanComparison metadata={metadata}/>

    <div className="ops-lower">
      <section className="ops-panel"><div className="ops-panel-header"><div><h2>Harvest schedule</h2><p>{policyName} · first five batches by harvest date</p></div><button className="text-button" onClick={()=>navigate('crops')}>All crops <ArrowUpRight size={15}/></button></div>
        {!plan?<div className="ops-empty"><h3>No completed plan yet</h3><p>Harvest dates and quantities appear after a model run.</p></div>:!batches.length?<div className="ops-empty"><h3>No crop batches in this result</h3><p>Review resources, inventory and the configured crop profiles.</p></div>:<div className="table-wrap ops-harvest-table"><table><thead><tr><th>Crop</th><th>Planting</th><th>Harvest</th><th>Estimate (kg)</th></tr></thead><tbody>{batches.map((batch,index)=><tr key={index}><td>{batch.crop}</td><td>Day {batch.day}</td><td>Day {batch.harvest_day}</td><td>{number(batch.predicted_harvest_kg)}</td></tr>)}</tbody></table></div>}
        <p className="ops-footnote">{policy==='baseline'?'Nominal batch estimates; realized yields are in the daily comparison.':'Estimates from saved inputs · local harvest validation pending.'}</p>
      </section>
      <section className="ops-panel"><div className="ops-panel-header"><h2>Hardware observations</h2><button className="text-button" onClick={()=>navigate('telemetry')}>Device workspace <ArrowUpRight size={15}/></button></div><div className="ops-panel-body"><div className="ops-device-status"><span className={'ops-status '+(fresh?'good':telemetry?.latest||error?'warning':'muted')}><span/><h3>{deviceTitle}</h3></span></div>
        {telemetry?.latest?<><div className="table-wrap ops-device-table"><table><thead><tr><th>Measurement</th><th>Last value</th></tr></thead><tbody>{[['Air temperature','air_temp_c','°C'],['Relative humidity','relative_humidity_pct','%'],['Solution temperature','solution_temp_c','°C'],['DC power','bus_power_w','W']].map(([label,key,unit])=><tr key={key}><td>{label}</td><td>{telemetry.latest[key]==null?'Unavailable':number(telemetry.latest[key])+' '+unit}</td></tr>)}</tbody></table></div><p className="ops-footnote">Hardware · device {telemetry.device_id||'unknown'} · {receipt} · {telemetry.availability?.status||'availability unknown'}{error?' · retained reading':''}</p></>:<div className="ops-empty"><p>No physical sensor packets received. Generated test streams are shown separately in Live devices.</p></div>}
        {error&&<p className="ops-footnote">{error}</p>}<p className="ops-footnote">Monitoring only · outputs disabled · recent receipt does not establish calibration.</p>
      </div></section>
    </div>
    <details className="ops-assumptions"><summary>Data sources and assumptions</summary><section className="ops-toolbar" aria-label="Current mission configuration"><div className="ops-context"><span><strong>{savedConfig.crew}</strong> starting crew</span><span><strong>{savedConfig.days}</strong> days</span><span><strong>{number(savedConfig.area_m2)}</strong> m² growing area</span><span><strong>{number(savedConfig.water_budget_l_per_day)}</strong> L/day initial water</span><span><strong>{number(savedConfig.power_budget_kwh_per_day)}</strong> kWh/day initial energy</span></div></section><p>{mixed?'The represented configuration combines entered inputs and declared sources.':'The represented configuration uses editable demonstration food, crop and crew coefficients.'} Crop references come from terrestrial experiments; local harvest accuracy remains unvalidated. Only energy, protein and vitamin C are tracked. Nutrition targets are planning inputs, and the modeled water budget does not represent a complete closed-loop life-support system.</p></details>
  </div>;
}

