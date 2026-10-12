import React,{useEffect,useRef,useState} from 'react';
import {loadBioProductionScenario} from './bio-production-scenario.js';
import './mission-crew.css';

const nutrients=[
  {key:'energy',name:'Energy',unit:'kcal'},
  {key:'protein',name:'Protein',unit:'g'},
  {key:'vitamin_c',name:'Vitamin C',unit:'mg'},
];
const number=value=>value==null||!Number.isFinite(Number(value))?'Unknown':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
const percent=(amount,target)=>amount==null||target==null||Number(target)<=0?null:`${number(Number(amount)/Number(target)*100)}%`;

export default function MissionCropSuggestions({run,day,request,navigate}) {
  const horizon=run?.metadata?.config?.days||0;
  const plantingDay=day+1;
  const [deadline,setDeadline]=useState(horizon);
  const [timelineNutrient,setTimelineNutrient]=useState('protein');
  const [report,setReport]=useState(null),[bioReport,setBioReport]=useState(null),[error,setError]=useState(''),[bioError,setBioError]=useState(''),[busy,setBusy]=useState(false);
  const revision=useRef(0);
  const key=JSON.stringify([run?.history_id,run?.metadata?.created_at_utc,plantingDay,deadline]);
  useEffect(()=>{setDeadline(horizon);},[horizon,run?.history_id]);
  useEffect(()=>{
    const ticket=++revision.current;setReport(null);setBioReport(null);setError('');setBioError('');
    if(!run?.metadata||plantingDay>horizon){setBusy(false);return;}
    setBusy(true);
    const boundedDeadline=Math.max(plantingDay,Math.min(horizon,deadline));
    request('/crop-advisor',{...(run.history_id?{run_id:run.history_id}:{metadata:run.metadata}),day:plantingDay,deadline_day:boundedDeadline,priority:'balanced',area_m2:1})
      .then(value=>{if(ticket===revision.current){if(!Array.isArray(value.recommendations))throw new Error('Crop recommendations are unavailable.');setReport(value);}})
      .catch(failure=>{if(ticket===revision.current)setError(failure.message);})
      .finally(()=>{if(ticket===revision.current)setBusy(false);});
    const reviewedModules=loadBioProductionScenario(run);
    if(reviewedModules){
      const events=(reviewedModules.events||[]).filter(event=>event.day>=plantingDay&&event.day<=boundedDeadline);
      request('/bioproduction/simulate',{...(run.history_id?{run_id:run.history_id}:{metadata:run.metadata}),...reviewedModules,start_day:plantingDay,horizon_days:boundedDeadline-plantingDay+1,events})
        .then(value=>{if(ticket===revision.current)setBioReport(value);})
        .catch(failure=>{if(ticket===revision.current)setBioError(failure.message||'The reviewed biological production scenario could not be compared for this window.');});
    }
    return()=>{revision.current++;};
  },[key,request]);

  const actions=report?.planned_crop_actions||[];
  const timely=actions.filter(action=>action.fits_deadline!==false && action.harvest_day<=deadline);
  const grouped=new Map();
  for(const action of timely){
    const groupKey=`${action.crop_id}:${action.harvest_day}`;
    let item=grouped.get(groupKey);
    if(!item){item={key:groupKey,name:action.name,harvestDay:action.harvest_day,firstPlantDay:action.day,lastPlantDay:action.day,mass:0,area:0,amounts:Object.fromEntries(nutrients.map(n=>[n.key,0])),unknown:new Set(),targets:action.forecast_daily_targets||{}};grouped.set(groupKey,item);}
    item.mass+=Number(action.predicted_harvest_kg)||0;item.area+=Number(action.area_m2)||0;
    item.firstPlantDay=Math.min(item.firstPlantDay,action.day);item.lastPlantDay=Math.max(item.lastPlantDay,action.day);
    for(const n of nutrients){const value=action.nutrients_at_harvest?.[n.key];if(value==null||!Number.isFinite(Number(value)))item.unknown.add(n.key);else item.amounts[n.key]+=Number(value);}
  }
  const top=report?.recommendations?.find(crop=>crop.crop_id===report.top_choice_crop_id);
  const forecastNutrients=report?.forecast?.nutrients||[];
  const gap=forecastNutrients.filter(item=>item.earliest_gap_day!=null).sort((a,b)=>a.earliest_gap_day-b.earliest_gap_day)[0];
  const candidateAmounts=top?.nutrients_at_harvest||{};
  const candidateTargets=top?.score_daily_targets||{};
  const forecastSupply=nutrient=>{
    const value=forecastNutrients.find(item=>item.nutrient===nutrient);
    return value?.current_supply;
  };
  const proteinForecast=forecastNutrients.find(item=>item.nutrient==='protein');
  const selectedForecast=forecastNutrients.find(item=>item.nutrient===timelineNutrient);
  const timelineRows=selectedForecast?.daily||[];
  const chartWidth=1000,chartHeight=250,pad={left:54,right:22,top:24,bottom:34};
  const values=timelineRows.flatMap(row=>[row.target,row.supply]).filter(value=>value!=null&&Number.isFinite(Number(value))).map(Number);
  const chartMax=Math.max(...values,1)*1.12;
  const xFor=index=>pad.left+(timelineRows.length<=1?0:index*(chartWidth-pad.left-pad.right)/(timelineRows.length-1));
  const yFor=value=>pad.top+(chartHeight-pad.top-pad.bottom)*(1-Number(value)/chartMax);
  const linePath=field=>timelineRows.reduce((path,row,index)=>{
    const value=row[field];if(value==null||!Number.isFinite(Number(value)))return path;
    return path+(path?' L ':'M ')+xFor(index).toFixed(1)+' '+yFor(value).toFixed(1);
  },'');
  const dayX=missionDay=>{
    const index=timelineRows.findIndex(row=>row.day===missionDay);
    return index<0?null:xFor(index);
  };
  const plannedHarvests=timely.filter(action=>action.harvest_day>=plantingDay);
  const microbialDays=timelineNutrient==='protein'?(bioReport?.daily||[]).filter(row=>row.modules?.some(module=>Number(module.protein_g)>0)):[];
  const keyGaps=[...forecastNutrients].filter(item=>Number(item.cumulative_future_shortfall)>0).sort((a,b)=>(b.normalized_future_gap||0)-(a.normalized_future_gap||0));

  return <section className="mission-crop-suggestions" aria-labelledby="mission-crop-title">
    <div className="section-heading"><div><span className="eyebrow">CREW NEEDS → GROWING TIME → RESOURCES</span><h2 id="mission-crop-title">What to grow next</h2></div><button className="text-button" onClick={()=>navigate('crops')}>Compare crops & constraints →</button></div>
    {plantingDay>horizon?<p>The mission horizon is complete. There is no remaining growing window.</p>:<>
      <div className="mission-crop-window"><p>Adaptive plan · Planning from Day {plantingDay} · {horizon-day} mission days remaining. Recommendations use the saved roster, combined nutrient targets, food stocks, harvest timing and resource limits.</p><label className="field"><span>Harvest needed by Day</span><input type="number" min={plantingDay} max={horizon} step={1} value={Math.max(plantingDay,deadline)} onChange={event=>{const value=Number(event.target.value);if(Number.isInteger(value))setDeadline(Math.max(plantingDay,Math.min(horizon,value)));}}/></label></div>
      {busy&&<p role="status">Checking the combined crew’s nutrient needs, harvest timing and available resources…</p>}
      {error&&<p role="alert" className="notice warning">{error}</p>}
      {bioError&&<p role="alert" className="notice warning">Microorganism comparison: {bioError}</p>}
      {report&&<>
        <h3>Combined crew needs across the forecast window</h3>
        <p className="muted">Targets are summed across all crew members in the saved roster. Forecast supply and shortfall reflect the saved mission plan through Day {report.deadline_day}.</p>
        <div className="table-wrap"><table aria-label="Combined crew nutrient needs and forecast"><thead><tr><th>Nutrient</th><th>Combined daily target</th><th>Modeled supply today</th><th>Shortfall today</th><th>Forecast shortfall</th><th>Gap days</th><th>First gap</th></tr></thead><tbody>
          {nutrients.map(n=>{const item=forecastNutrients.find(row=>row.nutrient===n.key);return <tr key={n.key}><th scope="row">{n.name}</th><td>{number(item?.current_target)} {item?.unit||n.unit}/day</td><td>{number(forecastSupply(n.key))} {item?.unit||n.unit}</td><td>{number(item?.current_shortfall)} {item?.unit||n.unit}</td><td>{number(item?.cumulative_future_shortfall)} {item?.unit||n.unit}</td><td>{number(item?.gap_days)}</td><td>{item?.earliest_gap_day==null?'None forecast':`Day ${item.earliest_gap_day}`}</td></tr>;})}
        </tbody></table></div>

        <section className="mission-nutrition-timeline" aria-labelledby="mission-timeline-title">
          <div className="mission-timeline-heading"><div><span className="eyebrow">DAY-BY-DAY COVERAGE</span><h3 id="mission-timeline-title">Crew need and modeled supply</h3><p>Each nutrient uses its own unit and scale. A supply line below the target indicates a modeled gap.</p></div><label className="field"><span>Show nutrient</span><select value={timelineNutrient} onChange={event=>setTimelineNutrient(event.target.value)}>{nutrients.map(item=><option key={item.key} value={item.key}>{item.name} · {item.unit}</option>)}</select></label></div>
          {timelineRows.length?<>
            <div className="mission-timeline-chart-wrap"><svg className="mission-timeline-chart" viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label={`${selectedForecast?.nutrient?.replaceAll('_',' ')} daily combined crew target and modeled supply from Day ${timelineRows[0]?.day} to Day ${timelineRows.at(-1)?.day}`}>
              {[0,.25,.5,.75,1].map(fraction=>{const y=pad.top+(chartHeight-pad.top-pad.bottom)*(1-fraction);return <g key={fraction}><line x1={pad.left} x2={chartWidth-pad.right} y1={y} y2={y} className="mission-chart-grid"/><text x={pad.left-8} y={y+4} textAnchor="end" className="mission-chart-label">{number(chartMax*fraction)}</text></g>;})}
              <path d={linePath('target')} className="mission-chart-target"/><path d={linePath('supply')} className="mission-chart-supply"/>
              {timelineRows.filter((_,index)=>index===0||index===timelineRows.length-1||index%Math.max(1,Math.ceil(timelineRows.length/8))===0).map(row=>{const index=timelineRows.indexOf(row);return <text key={row.day} x={xFor(index)} y={chartHeight-8} textAnchor="middle" className="mission-chart-label">{row.day}</text>;})}
            </svg></div>
            <div className="mission-timeline-legend"><span><i className="mission-legend-target"/>Combined crew target</span><span><i className="mission-legend-supply"/>Saved-plan supply</span></div>
            <div className="mission-timeline-events" aria-label="Projected production events"><span className="mission-timeline-event-label">Events</span><div className="mission-timeline-track"><span className="mission-timeline-track-line"/>{plannedHarvests.map((action,index)=>{const x=dayX(action.harvest_day);return x==null?null:<span key={`${action.crop_id}-${action.harvest_day}-${index}`} className="mission-event-marker crop" style={{left:`${x/chartWidth*100}%`}} title={`${action.name} harvest · Day ${action.harvest_day}`} aria-label={`${action.name} harvest on Day ${action.harvest_day}`}/>;})}{microbialDays.map(row=>{const x=dayX(row.day);return x==null?null:<span key={`microbe-${row.day}`} className="mission-event-marker microbe" style={{left:`${x/chartWidth*100}%`}} title={`Modeled microorganism output · Day ${row.day}`} aria-label={`Modeled microorganism output on Day ${row.day}`}/>;})}</div></div>
            <div className="mission-timeline-legend"><span><i className="mission-legend-crop"/>Planned crop harvest</span>{bioReport&&timelineNutrient==='protein'&&<span><i className="mission-legend-microbe"/>Microorganism protein output</span>}</div>
            {!timelineRows.some(row=>row.supply!=null)&&<p className="notice">The saved plan has no supply values for this nutrient in the selected window; target values are shown for context.</p>}
          </>:<p className="notice">No daily forecast rows are available for this saved plan and deadline.</p>}
        </section>

        <details className="mission-suggestion-reason" open>
          <summary>Why this suggestion?</summary>
          <p>The crop ranking uses the saved crew targets, current plan, harvest timing and resource limits. {report.weight_basis}</p>
          {keyGaps.length>0?<><h4>Needs driving the comparison</h4><ul>{keyGaps.map(item=><li key={item.nutrient}><strong>{item.nutrient.replaceAll('_',' ')}:</strong> {number(item.cumulative_future_shortfall)} {item.unit} forecast shortfall over {number(item.gap_days)} gap day(s), first on Day {item.earliest_gap_day}; normalized gap weight {number((report.weights?.[item.nutrient]||0)*100)}%.</li>)}</ul></>:<p>No future energy, protein or vitamin C shortfall is forecast in this window. Crop ranking then uses configured targets and normalized production per area and growing day.</p>}
          {top&&<><h4>Timing and resources for {top.name}</h4><ul><li>Harvest: Day {top.harvest_day}; mission deadline: Day {report.deadline_day}; latest planting day under the deadline: Day {top.latest_planting_day}.</li><li>Daily water: {number(top.resources?.required_daily_water_l)} L needed / {number(top.resources?.available_daily_water_l)} L available; power: {number(top.resources?.required_daily_power_kwh)} kWh needed / {number(top.resources?.available_daily_power_kwh)} kWh available; tray area: {number(top.resources?.required_area_m2)} m² needed / {number(top.resources?.available_area_m2)} m² available.</li><li>Crop scoring mode: {report.score_mode?.replaceAll('_',' ')}. {top.provenance?.growth?.detail||'Growth values use configured planning coefficients.'}</li></ul></>}
          {bioReport&&<p>The reviewed microorganism scenario is screened separately for potential protein output on forecast gap days. Its output does not enter the mission meal solver; energy and vitamin C remain unknown for that route.</p>}
        </details>

        <p className="mission-crop-reason">{top?`Recommended additional batch: ${top.name}. A ${number(top.resources?.required_area_m2)} m² planting from Day ${report.day} is modeled to harvest on Day ${top.harvest_day}, within the selected deadline.`:report.selection_reason?.text}</p>
        {top&&<>
          <h3>Potential production from the recommended batch</h3>
          <p className="muted">This estimate covers one candidate harvest batch. “Share of one day” compares its modeled nutrient content with the combined crew target on harvest day; it does not mean the whole amount will be eaten or close a multi-day gap.</p>
          <div className="table-wrap"><table aria-label="Recommended crop batch modeled nutrient production"><thead><tr><th>Crop</th><th>Harvest</th><th>Modeled harvest</th>{nutrients.map(n=><th key={n.key}>{n.name} produced</th>)}<th>Water / day</th><th>Power / day</th></tr></thead><tbody>
            <tr><th scope="row">{top.name}</th><td>Day {top.harvest_day}</td><td>{number(top.estimated_harvest_kg)} kg · {number(top.resources?.required_area_m2)} m²</td>{nutrients.map(n=><td key={n.key}>{number(candidateAmounts[n.key])} {n.unit}<br/><small>{percent(candidateAmounts[n.key],candidateTargets[n.key])??'Unknown'} of one crew-day target</small></td>)}<td>{number(top.resources?.required_daily_water_l)} L</td><td>{number(top.resources?.required_daily_power_kwh)} kWh</td></tr>
          </tbody></table></div>
          {top.provenance?.composition?.detail&&<p className="muted">Nutrient basis: {top.provenance.composition.detail}</p>}
          {top.warnings?.length>0&&<p className="notice">{top.warnings.join(' ')}</p>}
        </>}

        {bioReport?<>
          <h3>Reviewed microorganism production option</h3>
          <p className="muted">Recalculated from the reviewed module settings for this mission window and crew roster. This is a separate research projection; its output is not treated as food or credited against the mission’s stored-food gaps.</p>
          <div className="table-wrap"><table aria-label="Reviewed microorganism production comparison"><thead><tr><th>Organism / module</th><th>Projected protein in window</th><th>Combined crew protein target</th><th>Modeled share</th><th>Potential protein aligned with forecast gaps</th><th>Best daily output</th><th>Resource holds</th></tr></thead><tbody>
            {bioReport.modules.map(module=>{
              const moduleRows=(bioReport.daily||[]).map(row=>({day:row.day,...row.modules?.find(item=>item.id===module.id),target:row.crew_protein_target_g}));
              const knownOutputs=moduleRows.filter(row=>row.protein_g!=null);
              const protein=knownOutputs.length?knownOutputs.reduce((sum,row)=>sum+Number(row.protein_g),0):null;
              const best=knownOutputs.sort((a,b)=>b.protein_g-a.protein_g)[0];
              const holds=moduleRows.filter(row=>row.status==='resource_hold').length;
              const gapByDay=new Map((proteinForecast?.daily||[]).map(row=>[row.day,row.shortfall]));
              const aligned=moduleRows.reduce((sum,row)=>{const gap=gapByDay.get(row.day);return gap==null||row.protein_g==null?sum:sum+Math.min(Number(gap),Number(row.protein_g));},0);
              return <tr key={module.id}><th scope="row">{module.name}</th><td>{number(protein)} g</td><td>{number(bioReport.totals?.crew_protein_target_g)} g</td><td>{percent(protein,bioReport.totals?.crew_protein_target_g)??'Unknown'}</td><td>{proteinForecast?`${number(aligned)} g potential`:'Unknown'}</td><td>{best?`${number(best.protein_g)} g · ${percent(best.protein_g,best.target)??'Unknown'} of Day ${best.day} target`:'No protein output projected'}</td><td>{holds?`${holds} days`:'None modeled'}</td></tr>;
            })}
          </tbody></table></div>
          {proteinForecast?.gap_days>0&&<p className="mission-crop-reason">This microbial run overlaps the saved crew’s forecast protein-gap days. The overlap is a candidate screening estimate; it is not credited as food or gap closure. Compare it with the crop harvest and address energy or vitamin C gaps through other validated sources.</p>}
          <p className="notice">This option supplies a modeled protein contribution only. Energy and vitamin C remain unknown for the microbial biomass, and food safety, digestibility, acceptability and intake are not established. Use it as a candidate for further validation, not as a capsule replacement or completed nutrition plan.</p>
          {bioReport.warnings?.map(warning=><p className="muted" key={warning}>{warning}</p>)}
          <button className="text-button" onClick={()=>navigate('production')}>Review biological production assumptions →</button>
        </>:<div className="notice"><strong>Microorganism options need a reviewed production run.</strong><p>Configure Limnospira or Wolffia in Grow targeted nutrition and run the production projection. Once reviewed, its output will appear here for the same crew and mission window. Catalyst-only and research-only routes stay out of food recommendations until a yield and nutrient composition are supported.</p><button className="text-button" onClick={()=>navigate('production')}>Configure microorganism options →</button></div>}

        {grouped.size>0?<><h3>Other future crops already in the saved plan</h3><p className="muted">These are planned harvests, grouped by crop and harvest day. Percentages compare each harvest with the combined crew’s one-day target for that day.</p><div className="table-wrap"><table aria-label="Timely planned crops and modeled nutrients for crew needs"><thead><tr><th>Crop</th><th>Planting → harvest</th><th>Modeled harvest</th>{nutrients.map(n=><th key={n.key}>{n.name} potential output</th>)}</tr></thead><tbody>{[...grouped.values()].sort((a,b)=>a.harvestDay-b.harvestDay||a.name.localeCompare(b.name)).map(item=><tr key={item.key}><th scope="row">{item.name}</th><td>{item.firstPlantDay===item.lastPlantDay?`Day ${item.firstPlantDay}`:`Days ${item.firstPlantDay}–${item.lastPlantDay}`} → Day {item.harvestDay}</td><td>{number(item.mass)} kg · {number(item.area)} m²</td>{nutrients.map(n=>{const amount=item.unknown.has(n.key)?null:item.amounts[n.key];return <td key={n.key}>{number(amount)} {n.unit}<br/><small>{percent(amount,item.targets?.[n.key])??'Unknown'} of one crew-day target</small></td>;})}</tr>)}</tbody></table></div></>:<p>No future plantings in the saved plan deliver a harvest by this deadline. Existing growing batches and stored food are considered separately.</p>}
        {gap&&<p className="notice warning">The first predicted {gap.nutrient.replaceAll('_',' ')} gap is on Day {gap.earliest_gap_day}. A new planting cannot supply food before its harvest; review stored food or recovery options for earlier needs.</p>}
        <p className="muted">The planner currently tracks energy, protein and vitamin C. Crop nutrient amounts use reference composition or configured assumptions with modeled yield; they are not measured harvest values, complete nutrition coverage, or guaranteed intake. Blood values and iron are not used as crop targets.</p>
      </>}
    </>}
  </section>;
}
