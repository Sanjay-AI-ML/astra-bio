import React, {useEffect, useRef, useState} from 'react';
import CrewHealthGraphs from './CrewHealthGraphs.jsx';
import {crewNutrients, crewRosterSignature, validateCrewRoster} from './crew-roster.js';
import {randomCrewName} from './crew-names.js';
import './nutrition-roster.css';

const clone=value=>structuredClone(value);
const units={energy:'kcal',protein:'g',vitamin_c:'mg'};
const number=value=>value==null?'Unknown':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
export default function NutritionPanel({config,setConfig,bootstrap,request,notify,run,missionDay=1,crewProfiles,missionCrewProfiles,onProfilesChange,onApplyCrew,crewPlanningBusy=false,navigate}) {
  const seed=bootstrap.crew_sample;
  const [sample,setSample]=useState(seed?clone(seed):null);
  const controlled=Array.isArray(crewProfiles);
  const initialProfiles=crewProfiles ?? (seed?.profiles||bootstrap.profiles||[]).slice(0,config.crew);
  const [localProfiles,setLocalProfiles]=useState(()=>clone(initialProfiles)),[entries,setEntries]=useState(clone(seed?.entries||[])),[complete,setComplete]=useState(clone(seed?.complete_days||{})),[day,setDay]=useState(1),[person,setPerson]=useState(initialProfiles[0]?.profile_id||''),[food,setFood]=useState('oats'),[grams,setGrams]=useState(100),[assessment,setAssessment]=useState(seed&&crewRosterSignature(initialProfiles)===crewRosterSignature(seed.profiles)?{rows:seed.assessments.filter(r=>r.day===1),contributions:[],scope:seed.scope}:null),[busy,setBusy]=useState(false),[inventory,setInventory]=useState({oats:0,lentils:0,peanut_butter:0}),[name,setName]=useState(seed?'SAMPLE · Named crew and dietary logs':'Crew intake log'),[snapshots,setSnapshots]=useState([]),[applyError,setApplyError]=useState('');
  const profiles=controlled?crewProfiles:localProfiles;
  function setProfiles(value,notifyChange=true){const next=typeof value==='function'?value(profiles):value;previousProfiles.current=JSON.stringify(next);setLocalProfiles(next);if(notifyChange)onProfilesChange?.(next);}
  const revision=useRef(0);
  const activeCrew=run?.metadata?.adaptive?.daily?.find(row=>row.day===missionDay)?.crew||config.crew;
  const count=Math.min(12,activeCrew),previousCount=useRef(config.crew);
  const rosterEvents=(run?.metadata?.config?.planning_events||[]).filter(event=>event.day<=missionDay && event.crew_profiles?.length);
  const datedRoster=rosterEvents.at(-1)?.crew_profiles;
  const rosterKey=JSON.stringify(datedRoster||null),previousRoster=useRef('null');
  const activeRow=run?.metadata?.adaptive?.daily?.find(row=>row.day===missionDay);
  const totals=Object.fromEntries(crewNutrients.map(nutrient=>[nutrient,profiles.reduce((sum,profile)=>sum+(Number(profile.targets?.[nutrient])||0),0)]));
  const recordedRoster=missionCrewProfiles ?? datedRoster;
  const rosterChanged=recordedRoster?crewRosterSignature(profiles)!==crewRosterSignature(recordedRoster):true;
  const totalChanged=profiles.length!==activeCrew || crewNutrients.some(nutrient=>activeRow?.[nutrient+'_target']!=null && Math.abs(totals[nutrient]-activeRow[nutrient+'_target'])>0.001);
  const lastCompleted=Number(run?.metadata?.continuation?.through_day)||0;
  const canContinue=!!run?.metadata && missionDay<Number(run.metadata.config?.days ?? config.days) && missionDay>=lastCompleted;
  const rosterBusy=busy||crewPlanningBusy;
  const profilesKey=JSON.stringify(profiles),previousProfiles=useRef(profilesKey);
  useEffect(()=>{
    if(previousProfiles.current===profilesKey)return;
    previousProfiles.current=profilesKey;
    revision.current++;setAssessment(null);setBusy(false);setApplyError('');
    setPerson(old=>profiles.some(profile=>profile.profile_id===old)?old:profiles[0]?.profile_id||'');
  },[profilesKey]);
  useEffect(()=>()=>{revision.current++;},[]);
  useEffect(()=>{request('/snapshots/nutrition').then(setSnapshots).catch(e=>notify(e.message,true));},[]);
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  function invalidate(){revision.current++;setAssessment(null);setBusy(false);}
  const edit=(i,key,value)=>{if(rosterBusy)return;setProfiles(v=>v.map((p,index)=>index===i?{...p,[key]:value,...(key==='targets'?{targets_reviewed:false}:{})}:p));invalidate();setApplyError('');};
  function addLog(e){e.preventDefault();if(!person||!food||!(grams>=0))return;setEntries(v=>[...v,{profile_id:person,day,food_key:food,grams}]);invalidate();}
  function addProfile(){
    if(rosterBusy||profiles.length>=12)return;
    let id='crew-added-'+Date.now(),suffix=1;
    while(profiles.some(profile=>profile.profile_id===id))id='crew-added-'+Date.now()+'-'+suffix++;
    const targets=Object.fromEntries(crewNutrients.map(nutrient=>[nutrient,profiles.length?profiles.reduce((sum,profile)=>sum+(Number(profile.targets?.[nutrient])||0),0)/profiles.length:config.targets_per_crew[nutrient]]));
    setProfiles(v=>[...v,{profile_id:id,name:randomCrewName(v.map(profile=>profile.name)),targets,age:null,sex:'unspecified',targets_reviewed:false}]);if(!person)setPerson(id);invalidate();setApplyError('');
  }
  // A roster may be changed outside this tab. Logs for departed profiles stay in
  // local state but are omitted from the active assessment/snapshot payload.
  const profileIds=new Set(profiles.map(profile=>profile.profile_id));
  const state={schema_version:1,profiles,entries:entries.filter(entry=>profileIds.has(entry.profile_id)),complete_days:Object.fromEntries(Object.entries(complete).filter(([key])=>profileIds.has(key.split(':')[0]))),...(sample?{sample_context:{sample_only:true,fixture_version:1}}:{})};
  async function assessDay(value=day){
    const ticket=++revision.current;setDay(value);setAssessment(null);setBusy(true);
    try{const result=await request('/nutrition/assess',{...state,day:value});if(ticket===revision.current)setAssessment(result);}
    catch(error){if(ticket===revision.current)notify(error.message,true);}
    finally{if(ticket===revision.current)setBusy(false);}
  }
  async function loadSample(number=count,merge=false,notifyChange=true){
    const ticket=++revision.current;setBusy(true);
    try{
      const fixture=await request('/nutrition/sample?count='+number);
      if(ticket!==revision.current)return;
      const usedNames=profiles.map(profile=>profile.name);
      const nextProfiles=merge?fixture.profiles.map(p=>{
        const existing=profiles.find(old=>old.profile_id===p.profile_id);
        if(existing)return existing;
        const added={...p,name:randomCrewName(usedNames)};usedNames.push(added.name);return added;
      }):fixture.profiles;
      const ids=new Set(nextProfiles.map(p=>p.profile_id)),oldIds=new Set(profiles.map(p=>p.profile_id));
      const nextEntries=merge?[...entries.filter(e=>ids.has(e.profile_id)),...fixture.entries.filter(e=>!oldIds.has(e.profile_id))]:fixture.entries;
      const nextComplete=merge?{...fixture.complete_days,...Object.fromEntries(Object.entries(complete).filter(([key])=>ids.has(key.split(':')[0])))}:fixture.complete_days;
      const selectedDay=Math.min(day,7);
      const result=await request('/nutrition/assess',{profiles:nextProfiles,entries:nextEntries,complete_days:nextComplete,day:selectedDay});
      if(ticket!==revision.current)return;
      setSample(fixture);setProfiles(nextProfiles,notifyChange);setEntries(nextEntries);setComplete(nextComplete);setDay(selectedDay);setAssessment(result);
      setPerson(old=>ids.has(old)?old:nextProfiles[0]?.profile_id||'');setName('SAMPLE · Named crew and dietary logs');
      if(!merge)notify('Fictional named crew, food logs and blood examples loaded. Mission planning inputs are unchanged.');
    }catch(error){if(ticket===revision.current)notify(error.message,true);}
    finally{if(ticket===revision.current)setBusy(false);}
  }
  useEffect(()=>{
    // The parent owns the shared draft in the application. Playback and remounts
    // must never replace its names/targets with a fresh demonstration roster.
    if(controlled)return;
    if(rosterKey!=='null' && previousRoster.current!==rosterKey){
      previousRoster.current=rosterKey;previousCount.current=count;
      invalidate();setProfiles(clone(datedRoster),false);
      setPerson(old=>datedRoster.some(p=>p.profile_id===old)?old:datedRoster[0]?.profile_id||'');
      return;
    }
    if(rosterKey!=='null'){previousCount.current=count;return;}
    if(previousRoster.current!=='null'){
      previousRoster.current='null';previousCount.current=count;
      if(sample)loadSample(count,false,false);
      return;
    }
    if(previousCount.current===count)return;
    previousCount.current=count;
    if(sample)loadSample(count,true,false);
  },[count,rosterKey,controlled]);
  async function restoreSnapshot(identifier){
    const ticket=++revision.current;setBusy(true);
    try{
      const restored=await request('/snapshots/nutrition/'+identifier);
      const fixture=restored.sample_context?.sample_only===true?await request('/nutrition/sample?count='+Math.min(12,Math.max(1,restored.profiles.length))):null;
      const result=await request('/nutrition/assess',{...restored,day});
      if(ticket!==revision.current)return;
      setProfiles(restored.profiles);setEntries(restored.entries);setComplete(restored.complete_days);setPerson(restored.profiles[0]?.profile_id||'');setSample(fixture);setAssessment(result);
      notify('Restored local dietary logs. '+(fixture?'Fictional blood examples remain labelled.':'No fictional blood tests were attached to these logs.'));
    }catch(error){if(ticket===revision.current)notify(error.message,true);}
    finally{if(ticket===revision.current)setBusy(false);}
  }
  async function applyCrew(){
    if(busy||crewPlanningBusy)return;
    const error=validateCrewRoster(profiles);
    if(error){setApplyError(error);return;}
    setApplyError('');
    await task(async()=>onApplyCrew?.(clone(profiles),{through_day:missionDay}));
  }
  return <>
    <div className="page-heading"><div><span className="eyebrow">CREW · NUTRITION · BLOOD EXAMPLES</span><h1>Nutrition assessment</h1><p>Compare each crew member’s dietary intake with their planning targets, and view separate fictional blood-test examples.</p></div><button className="btn" disabled={rosterBusy} onClick={()=>loadSample()}>Load named sample crew</button></div>
    <p className="muted">{profiles.length} profiles · {activeCrew} mission crew at simulated Day {missionDay}. New members receive a unique randomly selected name; review their planning targets before applying the roster. Missing blood tests remain unknown.</p>
    <section className="nutrition-roster-plan" aria-label="Shared crew planning roster">
      <div className="nutrition-roster-summary"><div><span className="eyebrow">SHARED CREW ROSTER</span><h2>{profiles.length} crew · {run?.metadata?'selected mission Day '+missionDay:'planning draft'}</h2><p>{profiles.map(profile=>profile.name).join(' · ')||'Add a crew profile to begin.'}</p></div>
        <dl className="nutrition-roster-totals">{crewNutrients.map(nutrient=><div key={nutrient}><dt>{nutrient.replaceAll('_',' ')}</dt><dd>{number(totals[nutrient])}<small>{units[nutrient]}/day</small></dd></div>)}</dl></div>
      <p className="muted">Names and individual targets are shared with Mission overview. {run?.metadata?(rosterChanged||totalChanged?'This edited roster is pending. Replan to use it in the saved mission and crop recommendations.':'This roster matches the saved mission at the selected day.'):'These targets will be used when you start a mission.'} Blood examples do not generate dietary requirements.</p>
      <div className="actions">
        <button className="btn" disabled={rosterBusy||!!validateCrewRoster(profiles,false)||profiles.every(profile=>profile.targets_reviewed===true)} onClick={()=>{setProfiles(previous=>previous.map(profile=>({...profile,targets_reviewed:true})));setApplyError('');}}>Mark all planning targets reviewed</button>
        {onApplyCrew&&<button className="btn primary" disabled={busy||crewPlanningBusy||(run?.metadata&&!canContinue)} onClick={applyCrew}>{busy||crewPlanningBusy?'Replanning…':run?.metadata?'Use this crew & replan from Day '+(missionDay+1):'Use this crew & start mission'}</button>}
        {run?.metadata&&navigate&&<button className="text-button" onClick={()=>navigate('overview')}>Choose a mission day</button>}
      </div>
      {run?.metadata&&!canContinue&&<p className="muted">Choose a day with remaining mission time{lastCompleted?' at or after Day '+lastCompleted:''} to change future crew needs.</p>}
      {applyError&&<p className="notice warning" role="alert">{applyError}</p>}
    </section>
    <CrewHealthGraphs sample={sample} profiles={profiles} assessments={assessment?.rows||[]} day={day} onDayChange={value=>assessDay(value)}/>
    {!assessment&&<p className="notice">Food logs or targets changed. Assess recorded intake to refresh the nutrition graph; blood examples remain separate.</p>}
    <details className="panel" open><summary>Crew profiles and daily targets</summary><div className="section-heading"><h2>Edit crew profiles</h2><button className="btn" disabled={profiles.length>=12||rosterBusy} onClick={addProfile}>Add crew profile</button></div>
      <div className="table-wrap"><table><thead><tr><th>Alias</th><th>Energy kcal</th><th>Protein g</th><th>Vitamin C mg</th><th>Age (optional)</th><th>Reference sex</th><th>Targets reviewed</th><th/></tr></thead><tbody>{profiles.map((p,i)=>
        <tr key={p.profile_id}><td><input aria-label={'Alias '+(i+1)} value={p.name} disabled={rosterBusy} onChange={e=>edit(i,'name',e.target.value)}/></td>
          {Object.keys(units).map(n=><td key={n}><input aria-label={p.name+' '+n+' target'} type="number" min={0} step="any" value={p.targets?.[n]??''} disabled={rosterBusy} onChange={e=>edit(i,'targets',{...p.targets,[n]:e.target.value===''?'':Number(e.target.value)})}/></td>)}
          <td><input aria-label={p.name+' age'} type="number" min={0} step={1} value={p.age??''} disabled={rosterBusy} onChange={e=>edit(i,'age',e.target.value===''?null:Number(e.target.value))}/></td>
          <td><select aria-label={p.name+' reference sex'} value={p.sex??'unspecified'} disabled={rosterBusy} onChange={e=>edit(i,'sex',e.target.value)}><option value="unspecified">Unspecified</option><option value="male">Male</option><option value="female">Female</option></select></td>
          <td><input aria-label={p.name+' reviewed targets'} type="checkbox" checked={p.targets_reviewed===true} disabled={rosterBusy} onChange={e=>edit(i,'targets_reviewed',e.target.checked)}/></td>
          <td><button className="text-button" aria-label={'Remove '+p.name} disabled={rosterBusy||profiles.length<=1} onClick={()=>{if(rosterBusy||profiles.length<=1)return;setProfiles(v=>v.filter(row=>row.profile_id!==p.profile_id));setEntries(v=>v.filter(row=>row.profile_id!==p.profile_id));if(person===p.profile_id)setPerson(profiles.find(row=>row.profile_id!==p.profile_id)?.profile_id||'');invalidate();setApplyError('');}}>Remove</button></td>
        </tr>)}</tbody></table></div>
      <div className="notice">Energy and protein targets are manually reviewed inputs. Optional NIH vitamin C healthy-adult references are 90 mg/day for men and 75 mg/day for women; the adult upper limit is 2,000 mg/day. These references exclude pregnancy, lactation and smoking and are not astronaut prescriptions. <a href="https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/" target="_blank" rel="noreferrer">Read NIH source</a></div>
      {!run?.metadata&&<><button className="btn" disabled={rosterBusy||profiles.length!==config.crew||!!validateCrewRoster(profiles)} onClick={()=>task(async()=>{const result=await request('/nutrition/apply-targets',{config,profiles});setConfig(result.config);})}>Apply mean reviewed targets to planner</button>
        <p className="muted">Profile count ({profiles.length}) must match planner crew ({config.crew}). Applying mean targets retains shared crew allocations; it does not generate individual menus.</p></>}
      {run?.metadata&&<p className="muted">Use the replan action above to apply these names and targets from Day {missionDay+1}, keeping earlier results, remaining resources and growing crops.</p>}
    </details>
    <details className="panel" open={!sample}><summary>Food logs and dietary assessment</summary><h2>Food log</h2><form onSubmit={addLog}><div className="form-grid">
      <label className="field"><span>Assessment day</span><input type="number" value={day} min={1} max={180} step={1} onChange={e=>assessDay(Number(e.target.value))}/></label>
      <label className="field"><span>Crew profile</span><select value={person} onChange={e=>setPerson(e.target.value)}><option value="">Choose profile</option>{profiles.map(p=><option value={p.profile_id} key={p.profile_id}>{p.name}</option>)}</select></label>
      <label className="field"><span>Food and measured form</span><select value={food} onChange={e=>setFood(e.target.value)}>{Object.values(bootstrap.compositions).map(f=><option value={f.key} key={f.key}>{f.name}</option>)}</select></label>
      <label className="field"><span>Mass in listed form (g)</span><input type="number" value={grams} min={0} step="any" onChange={e=>setGrams(Number(e.target.value))}/></label>
    </div><p className="muted">Selected form: {bootstrap.compositions[food]?.food_form}. Raw/dry ingredient weights are not cooked plate weights; do not substitute them without a food-form conversion.</p><button className="btn primary" disabled={!person}>Add food to log</button></form>
      <div className="table-wrap"><table><thead><tr><th>Crew</th><th>Day</th><th>Food</th><th>Grams</th><th/></tr></thead><tbody>{entries.map((entry,i)=>entry.day===day&&<tr key={i}><td>{profiles.find(p=>p.profile_id===entry.profile_id)?.name||entry.profile_id}</td><td>{entry.day}</td><td>{bootstrap.compositions[entry.food_key]?.name}</td><td>{entry.grams}</td><td><button className="text-button" onClick={()=>{setEntries(v=>v.filter((_,index)=>index!==i));invalidate();}}>Delete log entry</button></td></tr>)}</tbody></table></div>
      <div className="reference-options">{profiles.map(p=><label key={p.profile_id}><input type="checkbox" checked={!!complete[p.profile_id+':'+day]} onChange={e=>{setComplete(v=>({...v,[p.profile_id+':'+day]:e.target.checked}));invalidate();}}/><span>{p.name}<small>All intake for day {day} recorded</small></span></label>)}</div>
      <button className="btn primary" disabled={busy||!profiles.length} onClick={()=>assessDay()}>{busy?'Calculating…':'Assess recorded intake'}</button>
    </details>
    {assessment&&<details className="panel"><summary>Assessment numbers and crop contributions</summary><h2>Recorded intake versus targets</h2><div className="notice">{assessment.scope} An incomplete log is a partial intake estimate. Below-target values prompt log review and dietary planning, not a diagnosis.</div>
      <div className="table-wrap"><table><thead><tr><th>Crew</th><th>Nutrient</th><th>Logged intake</th><th>Target</th><th>Logged gap</th><th>Coverage</th><th>Log complete</th></tr></thead><tbody>{assessment.rows.map((r,i)=><tr key={i}><td>{r.person}</td><td>{r.nutrient.replaceAll('_',' ')}</td><td>{number(r.intake)} {r.unit}</td><td>{number(r.target)} {r.unit}</td><td>{number(r.gap)} {r.unit}</td><td>{number(r.coverage_pct)}%</td><td>{r.log_complete?'Yes':'Partial / unknown'}</td></tr>)}</tbody></table></div>
      {assessment.rows.some(r=>r.above_adult_vitamin_c_ul)&&<div className="notice warning">Recorded vitamin C exceeds the optional NIH healthy-adult upper-limit reference for a selected profile. Review the data and target with a qualified professional.</div>}
      <h2>Example fresh-crop contributions</h2><p className="muted">Illustrative food masses ranked against the recorded crew gap. Availability depends on inventory and harvest timing; these are not prescribed servings.</p>
      <div className="table-wrap"><table><thead><tr><th>Crop food proxy</th><th>Example mass g</th><th>Vitamin C mg</th><th>Protein g</th><th>Energy kcal</th><th>Source</th></tr></thead><tbody>{assessment.contributions.map(c=><tr key={c.crop_id}><td>{c.food}</td><td>{c.serving_g}</td><td>{number(c.nutrients.vitamin_c)}</td><td>{number(c.nutrients.protein)}</td><td>{number(c.nutrients.energy)}</td><td><a href={c.source_url} target="_blank" rel="noreferrer">USDA {c.fdc_id}</a></td></tr>)}</tbody></table></div>
    </details>}
    <details className="panel"><summary>Food composition & planner setup</summary><h2>Use reference composition in the planner</h2><p className="muted">Replace the synthetic ration catalogue with USDA oats, lentils and peanut butter, plus matched crop composition. Enter stock explicitly. Dry lentils require cooking; food-preparation resources are outside this prototype.</p>
      <div className="form-grid">{Object.keys(inventory).map(k=><label key={k} className="field"><span>{k.replaceAll('_',' ')} stock (kg)</span><input type="number" min={0} step="any" value={inventory[k]} onChange={e=>setInventory(v=>({...v,[k]:Number(e.target.value)}))}/></label>)}</div>
      <button className="btn primary" disabled={busy} onClick={()=>task(async()=>{const result=await request('/config/usda',{config,inventory});setConfig(result.config);})}>Apply USDA food composition</button>
      <div className="table-wrap"><table><thead><tr><th>Food</th><th>Energy kcal/kg</th><th>Protein g/kg</th><th>Vitamin C mg/kg</th><th>USDA source</th></tr></thead><tbody>{Object.values(bootstrap.compositions).map(f=><tr key={f.key}><td>{f.name}</td><td>{number(f.nutrients_per_kg.energy)}</td><td>{number(f.nutrients_per_kg.protein)}</td><td>{number(f.nutrients_per_kg.vitamin_c)}</td><td><a href={f.source_url} target="_blank" rel="noreferrer">FDC {f.fdc_id}</a></td></tr>)}</tbody></table></div>
    </details>
    <section className="panel"><h2>Save profiles and dietary logs locally</h2><div className="inline-form"><label className="field"><span>Snapshot name</span><input value={name} onChange={e=>setName(e.target.value)} maxLength={120}/></label>
      <button className="btn" disabled={busy} onClick={()=>task(async()=>{await request('/nutrition/save',{name,state});setSnapshots(await request('/snapshots/nutrition'));notify('Crew profiles and logs saved locally.');})}>Save intake snapshot</button></div>
      {snapshots.map(s=><div className="archive-row" key={s.id}><div><strong>{s.name}</strong><small>{new Date(s.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={rosterBusy} onClick={()=>restoreSnapshot(s.id)}>Restore intake snapshot</button></div>)}
    </section>
  </>;
}
