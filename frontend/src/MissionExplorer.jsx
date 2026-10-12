import React, {useEffect, useState} from 'react';
import {Activity, ArrowUpRight, ChevronLeft, ChevronRight, Droplets, Pause, Play, Sprout, UsersRound, Utensils} from 'lucide-react';

const value = (n, unit='') => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString(undefined,{maximumFractionDigits:2})+unit;
const finite = n => n != null && Number.isFinite(Number(n));
export const scenarioCrewCanceled = (scenario, planningEvents=[]) => Number(scenario?.extra_crew) > 0 && planningEvents.some(change=>change.cancel_scenario_crew===true&&change.day<=scenario.event_day);
export function missionEvents(plan, scenario, planningEvents=[]) {
  const days = new Set((plan?.daily||[]).map(r=>r.day));
  const events=[];
  if(days.has(scenario?.event_day)) events.push({day:scenario.event_day,type:'event',label:'Scenario begins',detail:(scenario.name||'Submitted scenario')+(scenarioCrewCanceled(scenario,planningEvents)?' · Original scheduled crew arrival replaced by the reviewed roster.':'')});
  const changes=new Map();
  for(const change of planningEvents)if(days.has(change.day))changes.set(change.day,{day:change.day,type:'change',label:change.crew ? 'Reviewed crew: '+change.crew : 'Reviewed mission change',detail:change.reason || 'Future targets or resource allowances updated; completed history preserved.'});
  events.push(...changes.values());
  const harvests=new Map();
  for(const batch of plan?.planting||[]) if(days.has(batch.harvest_day)) harvests.set(batch.harvest_day,(harvests.get(batch.harvest_day)||0)+1);
  for(const [day,count] of harvests) events.push({day,type:'harvest',label:count+' planned '+(count===1?'harvest':'harvests'),detail:'Saved batch date; daily results show the modeled harvest under this policy.'});
  const gap=(plan?.daily||[]).find(r=>r.shortfall_normalized>1e-6);
  if(gap) events.push({day:gap.day,type:'gap',label:'First target gap',detail:'One or more tracked dietary targets are unmet in the model.'});
  return events.sort((a,b)=>a.day-b.day||a.type.localeCompare(b.type));
}
function Node({icon:Icon,label,amount,detail,destination,navigate}) {
  return <button className="ecosystem-node" onClick={()=>navigate(destination)}><span className="ecosystem-node-label"><Icon size={17}/>{label}<ArrowUpRight size={13}/></span><strong>{amount}</strong><small>{detail}</small></button>;
}
export default function MissionExplorer({plan,scenario,planningEvents=[],policy,selectedDay,onSelectDay,navigate,onChangeCrew,editingCrew=false}) {
  const [playing,setPlaying] = useState(false);
  const rows=plan?.daily||[];
  useEffect(()=>{setPlaying(false);},[plan,policy,editingCrew]);
  useEffect(()=>{
    const pause=()=>setPlaying(false);
    window.addEventListener('hashchange',pause);
    document.addEventListener('visibilitychange',pause);
    return ()=>{window.removeEventListener('hashchange',pause);document.removeEventListener('visibilitychange',pause);};
  },[]);
  useEffect(()=>{
    if(!playing)return;
    const next=rows.find(r=>r.day>selectedDay);
    if(!next){setPlaying(false);return;}
    const timer=setTimeout(()=>onSelectDay(next.day),1500);
    return ()=>clearTimeout(timer);
  },[playing,selectedDay,rows,onSelectDay]);
  if(!rows.length) return null;
  const first=rows[0].day,last=rows.at(-1).day;
  const row=rows.find(r=>r.day===selectedDay);
  const index=rows.findIndex(r=>r.day===selectedDay);
  const events=missionEvents(plan,scenario,planningEvents);
  const next=events.find(e=>e.type==='harvest'&&e.day>selectedDay);
  const today=events.filter(e=>e.day===selectedDay);
  const milestones=[events.find(e=>e.type==='event'),...events.filter(e=>e.type==='change').slice(-2),events.find(e=>e.type==='gap'),...events.filter(e=>e.type==='harvest'&&e.day>=selectedDay).slice(0,2)].filter(Boolean).sort((a,b)=>a.day-b.day);
  const active=(plan.planting||[]).filter(b=>b.day<=selectedDay&&b.harvest_day>selectedDay).length;
  const coverage=['energy','protein','vitamin_c'].map(n=>row?.[n+'_coverage_pct']);
  const lowest=coverage.every(finite)?Math.min(...coverage):null;
  const before=index>0?rows[index-1].day:null,after=index>=0&&index<rows.length-1?rows[index+1].day:null;
  return <section className="mission-explorer" aria-label="Mission day explorer">
    <div className="mission-day-heading"><div className="mission-day-title"><span className="eyebrow">EXPLORE THE SAVED PLAN</span><h2>Day <strong>{selectedDay}</strong><span> / {last}</span></h2><small>{policy==='baseline'?'Fixed baseline':'Adaptive plan'} · simulated mission day</small></div>
      <div className="mission-day-brief"><span className="eyebrow">{today.length?'ON THIS DAY':'NEXT IN THE PLAN'}</span><strong>{today.length?today.map(e=>e.label).join(' · '):next?'Next planned harvest on Day '+next.day:'No later harvest batches scheduled'}</strong><small>{today.find(e=>e.type==='change')?.detail || (today.some(e=>e.type==='event')?today.find(e=>e.type==='event').detail:next?next.day-selectedDay+' simulated '+(next.day-selectedDay===1?'day':'days')+' until the next batch date':'Inspect the crop schedule for batch detail.')}</small></div>
    </div>
    <div className="actions"><button className="btn" disabled={editingCrew||(after==null&&!playing)} aria-label={playing?'Pause simulation':'Play simulation'} onClick={()=>setPlaying(v=>!v)}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?'Pause simulation':'Play simulation'}</button>{onChangeCrew&&<button className="btn primary" aria-expanded={editingCrew} disabled={after==null} onClick={()=>{setPlaying(false);onChangeCrew(selectedDay);}}><UsersRound size={16}/> Change crew at Day {selectedDay}</button>}<button className="text-button" onClick={()=>{setPlaying(false);onSelectDay(first);}}>Restart playback</button><button className="text-button" onClick={()=>navigate('crops')}>Recommend crops & continue planning <ArrowUpRight size={15}/></button></div>
    <div className="mission-scrubber"><button className="icon-button" aria-label="Previous mission day" disabled={before==null} onClick={()=>{setPlaying(false);onSelectDay(before);}}><ChevronLeft size={18}/></button><div className="mission-range"><label className="sr-only" htmlFor="mission-day">Explore mission day</label><input id="mission-day" type="range" min={first} max={last} step={1} value={selectedDay} onChange={e=>{setPlaying(false);const day=Number(e.target.value);if(rows.some(r=>r.day===day))onSelectDay(day);}} aria-valuetext={'Simulated day '+selectedDay} style={{'--day-progress':((selectedDay-first)/Math.max(1,last-first))*100+'%'}}/><div className="mission-range-labels"><span>Day {first}</span><span>Day {last}</span></div></div><button className="icon-button" aria-label="Next mission day" disabled={after==null} onClick={()=>{setPlaying(false);onSelectDay(after);}}><ChevronRight size={18}/></button></div>
    <div className="mission-events" aria-label="Saved plan milestones">{milestones.map(e=><button key={e.type+e.day} className={'mission-event '+e.type+(e.day===selectedDay?' selected':'')} onClick={()=>onSelectDay(e.day)} aria-pressed={e.day===selectedDay} title={e.detail}><span/>Day {e.day}<small>{e.label}</small></button>)}</div>
    <div className="ecosystem-flow" role="group" aria-label={'Modeled ecosystem on day '+selectedDay}>
      <Node icon={Activity} label="CREW" amount={value(row?.crew,' crew')} detail={'Lowest tracked coverage: '+value(lowest,'%')} destination="crew" navigate={navigate}/>
      <Node icon={Utensils} label="FOOD RESERVE" amount={value(row?.reserve_days_available,' days')} detail={value(row?.reserve_kg,' kg')+' reserve at end of day'} destination="pantry" navigate={navigate}/>
      <Node icon={Sprout} label="CROPS" amount={value(row?.harvest_kg,' kg')} detail={'Modeled harvest today · '+active+' growing batches'} destination="crops" navigate={navigate}/>
      <Node icon={Droplets} label="RESOURCES" amount={value(row?.water_l,' L')} detail={'Water / daily allowance '+value(row?.water_available_l,' L')+' · electricity '+value(row?.power_kwh,' kWh')+(finite(row?.water_remaining_l)?' · remaining water '+value(row.water_remaining_l,' L'):'')} destination="simulator" navigate={navigate}/>
    </div>
    <p className="mission-scope">{editingCrew?'Playback is paused while you review the crew change. Close the editor to resume.':'Play advances the saved plan, one day every 1.5 seconds. Pause on any day and choose Change crew to replan the remaining mission.'} Saved, dated changes are replayed on the timeline; crew changes are never generated by playback.</p>
  </section>;
}

export function PlanComparison({metadata}) {
  if(!metadata?.adaptive?.metrics||!metadata?.baseline?.metrics) return null;
  const metrics=[['shortfall_days','Target-gap days','days'],['total_harvest_kg','Calculated harvest','kg'],['total_water_l','Modeled water use','L']];
  return <section className="plan-comparison" aria-label="Whole-run policy comparison"><div className="comparison-heading"><h2>What changes with adaptation?</h2><p>Same submitted scenario · {metadata.config?.days} days</p></div><div className="comparison-values">{metrics.map(([key,label,unit])=>{const a=metadata.adaptive.metrics[key],b=metadata.baseline.metrics[key];const delta=finite(a)&&finite(b)?Number(a)-Number(b):null;return <div key={key}><span>{label}</span><div><small>Fixed</small><strong>{value(b)}</strong><span>→</span><small>Adaptive</small><strong>{value(a)}</strong><small>{unit}</small></div><em>{delta==null?'Difference unavailable':(delta>0?'+':'')+value(delta)+' '+unit+' difference'}</em></div>;})}</div><p className="mission-scope">Calculated comparison, not measured savings. Resource changes must be read alongside achieved nutrition.</p></section>;
}
