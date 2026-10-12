import React from 'react';
import {Activity, ArrowUpRight, ChevronLeft, ChevronRight, Droplets, Sprout, Utensils} from 'lucide-react';

const value = (n, unit='') => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString(undefined,{maximumFractionDigits:2})+unit;
const finite = n => n != null && Number.isFinite(Number(n));
export function missionEvents(plan, scenario) {
  const days = new Set((plan?.daily||[]).map(r=>r.day));
  const events=[];
  if(days.has(scenario?.event_day)) events.push({day:scenario.event_day,type:'event',label:'Scenario begins',detail:scenario.name||'Submitted scenario'});
  const harvests=new Map();
  for(const batch of plan?.planting||[]) if(days.has(batch.harvest_day)) harvests.set(batch.harvest_day,(harvests.get(batch.harvest_day)||0)+1);
  for(const [day,count] of harvests) events.push({day,type:'harvest',label:count+' planned '+(count===1?'harvest':'harvests'),detail:'Nominal batch date; daily results show realized modeled yield.'});
  const gap=(plan?.daily||[]).find(r=>r.shortfall_normalized>1e-6);
  if(gap) events.push({day:gap.day,type:'gap',label:'First target gap',detail:'One or more tracked dietary targets are unmet in the model.'});
  return events.sort((a,b)=>a.day-b.day||a.type.localeCompare(b.type));
}
function Node({icon:Icon,label,amount,detail,destination,navigate}) {
  return <button className="ecosystem-node" onClick={()=>navigate(destination)}><span className="ecosystem-node-label"><Icon size={17}/>{label}<ArrowUpRight size={13}/></span><strong>{amount}</strong><small>{detail}</small></button>;
}
export default function MissionExplorer({plan,scenario,policy,selectedDay,onSelectDay,navigate}) {
  const rows=plan?.daily||[];
  if(!rows.length) return null;
  const first=rows[0].day,last=rows.at(-1).day;
  const row=rows.find(r=>r.day===selectedDay);
  const index=rows.findIndex(r=>r.day===selectedDay);
  const events=missionEvents(plan,scenario);
  const next=events.find(e=>e.type==='harvest'&&e.day>selectedDay);
  const today=events.filter(e=>e.day===selectedDay);
  const milestones=[events.find(e=>e.type==='event'),events.find(e=>e.type==='gap'),...events.filter(e=>e.type==='harvest'&&e.day>=selectedDay).slice(0,2)].filter(Boolean).sort((a,b)=>a.day-b.day);
  const active=(plan.planting||[]).filter(b=>b.day<=selectedDay&&b.harvest_day>selectedDay).length;
  const coverage=['energy','protein','vitamin_c'].map(n=>row?.[n+'_coverage_pct']);
  const lowest=coverage.every(finite)?Math.min(...coverage):null;
  const before=index>0?rows[index-1].day:null,after=index>=0&&index<rows.length-1?rows[index+1].day:null;
  return <section className="mission-explorer" aria-label="Mission day explorer">
    <div className="mission-day-heading"><div className="mission-day-title"><span className="eyebrow">EXPLORE THE SAVED PLAN</span><h2>Day <strong>{selectedDay}</strong><span> / {last}</span></h2><small>{policy==='baseline'?'Fixed baseline':'Adaptive plan'} · simulated mission day</small></div>
      <div className="mission-day-brief"><span className="eyebrow">{today.length?'ON THIS DAY':'NEXT IN THE PLAN'}</span><strong>{today.length?today.map(e=>e.label).join(' · '):next?'Next planned harvest on Day '+next.day:'No later harvest batches scheduled'}</strong><small>{today.some(e=>e.type==='event')?scenario.name:next?next.day-selectedDay+' simulated '+(next.day-selectedDay===1?'day':'days')+' until the next batch date':'Inspect the crop schedule for batch detail.'}</small></div>
    </div>
    <div className="mission-scrubber"><button className="icon-button" aria-label="Previous mission day" disabled={before==null} onClick={()=>onSelectDay(before)}><ChevronLeft size={18}/></button><div className="mission-range"><label className="sr-only" htmlFor="mission-day">Explore mission day</label><input id="mission-day" type="range" min={first} max={last} step={1} value={selectedDay} onChange={e=>{const day=Number(e.target.value);if(rows.some(r=>r.day===day))onSelectDay(day);}} aria-valuetext={'Simulated day '+selectedDay} style={{'--day-progress':((selectedDay-first)/Math.max(1,last-first))*100+'%'}}/><div className="mission-range-labels"><span>Day {first}</span><span>Day {last}</span></div></div><button className="icon-button" aria-label="Next mission day" disabled={after==null} onClick={()=>onSelectDay(after)}><ChevronRight size={18}/></button></div>
    <div className="mission-events" aria-label="Saved plan milestones">{milestones.map(e=><button key={e.type+e.day} className={'mission-event '+e.type+(e.day===selectedDay?' selected':'')} onClick={()=>onSelectDay(e.day)} aria-pressed={e.day===selectedDay} title={e.detail}><span/>Day {e.day}<small>{e.label}</small></button>)}</div>
    <div className="ecosystem-flow" role="group" aria-label={'Modeled ecosystem on day '+selectedDay}>
      <Node icon={Activity} label="CREW" amount={value(row?.crew,' crew')} detail={'Lowest tracked coverage: '+value(lowest,'%')} destination="crew" navigate={navigate}/>
      <Node icon={Utensils} label="FOOD RESERVE" amount={value(row?.reserve_days_available,' days')} detail={value(row?.reserve_kg,' kg')+' reserve at end of day'} destination="pantry" navigate={navigate}/>
      <Node icon={Sprout} label="CROPS" amount={value(row?.harvest_kg,' kg')} detail={'Modeled harvest today · '+active+' growing batches'} destination="crops" navigate={navigate}/>
      <Node icon={Droplets} label="RESOURCES" amount={value(row?.water_l,' L')} detail={'Water / budget '+value(row?.water_available_l,' L')+' · electricity '+value(row?.power_kwh,' kWh')} destination="simulator" navigate={navigate}/>
    </div>
    <p className="mission-scope">Daily modeled values · only three nutrients tracked · sensor observations are separate.</p>
  </section>;
}

export function PlanComparison({metadata}) {
  if(!metadata?.adaptive?.metrics||!metadata?.baseline?.metrics) return null;
  const metrics=[['shortfall_days','Target-gap days','days'],['total_harvest_kg','Calculated harvest','kg'],['total_water_l','Modeled water use','L']];
  return <section className="plan-comparison" aria-label="Whole-run policy comparison"><div className="comparison-heading"><h2>What changes with adaptation?</h2><p>Same submitted scenario · {metadata.config?.days} days</p></div><div className="comparison-values">{metrics.map(([key,label,unit])=>{const a=metadata.adaptive.metrics[key],b=metadata.baseline.metrics[key];const delta=finite(a)&&finite(b)?Number(a)-Number(b):null;return <div key={key}><span>{label}</span><div><small>Fixed</small><strong>{value(b)}</strong><span>→</span><small>Adaptive</small><strong>{value(a)}</strong><small>{unit}</small></div><em>{delta==null?'Difference unavailable':(delta>0?'+':'')+value(delta)+' '+unit+' difference'}</em></div>;})}</div><p className="mission-scope">Calculated comparison, not measured savings. Resource changes must be read alongside achieved nutrition.</p></section>;
}
