import React, {useEffect, useRef, useState} from 'react';
import CrewHealthGraphs from './CrewHealthGraphs.jsx';

const clone=value=>structuredClone(value);
const units={energy:'kcal',protein:'g',vitamin_c:'mg'};
const number=value=>value==null?'Unknown':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
export default function NutritionPanel({config,setConfig,bootstrap,request,notify,run,missionDay=1,onProfilesChange,navigate}) {
  const seed=bootstrap.crew_sample;
  const [sample,setSample]=useState(seed?clone(seed):null);
  const [profiles,setProfiles]=useState(clone((seed?.profiles||bootstrap.profiles).slice(0,config.crew))),[entries,setEntries]=useState(clone(seed?.entries||[])),[complete,setComplete]=useState(clone(seed?.complete_days||{})),[day,setDay]=useState(1),[person,setPerson]=useState((seed?.profiles||bootstrap.profiles)[0]?.profile_id||''),[food,setFood]=useState('oats'),[grams,setGrams]=useState(100),[assessment,setAssessment]=useState(seed?{rows:seed.assessments.filter(r=>r.day===1),contributions:[],scope:seed.scope}:null),[busy,setBusy]=useState(false),[inventory,setInventory]=useState({oats:0,lentils:0,peanut_butter:0}),[name,setName]=useState(seed?'SAMPLE · Named crew and dietary logs':'Crew intake log'),[snapshots,setSnapshots]=useState([]);
  const revision=useRef(0);
  const activeCrew=run?.metadata?.adaptive?.daily?.find(row=>row.day===missionDay)?.crew||config.crew;
  const count=Math.min(12,activeCrew),previousCount=useRef(config.crew);
  const rosterEvents=(run?.metadata?.config?.planning_events||[]).filter(event=>event.day<=missionDay && event.crew_profiles?.length);
  const datedRoster=rosterEvents.at(-1)?.crew_profiles;
  const rosterKey=JSON.stringify(datedRoster||null),previousRoster=useRef('null');
  useEffect(()=>{onProfilesChange?.(profiles);},[profiles,onProfilesChange]);
  useEffect(()=>()=>{revision.current++;},[]);
  useEffect(()=>{request('/snapshots/nutrition').then(setSnapshots).catch(e=>notify(e.message,true));},[]);
  async function task(fn){setBusy(true);try{await fn();}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  function invalidate(){revision.current++;setAssessment(null);setBusy(false);}
  const edit=(i,key,value)=>{setProfiles(v=>v.map((p,index)=>index===i?{...p,[key]:value}:p));invalidate();};
  function addLog(e){e.preventDefault();if(!person||!food||!(grams>=0))return;setEntries(v=>[...v,{profile_id:person,day,food_key:food,grams}]);invalidate();}
  function addProfile(){const id='crew-'+Date.now();setProfiles(v=>[...v,{profile_id:id,name:(sample?'Sample Crew ':'Crew ')+(v.length+1),targets:clone(config.targets_per_crew),age:null,sex:'unspecified',targets_reviewed:false}]);if(!person)setPerson(id);invalidate();}
  const state={schema_version:1,profiles,entries,complete_days:complete,...(sample?{sample_context:{sample_only:true,fixture_version:1}}:{})};
  async function assessDay(value=day){
    const ticket=++revision.current;setDay(value);setAssessment(null);setBusy(true);
    try{const result=await request('/nutrition/assess',{...state,day:value});if(ticket===revision.current)setAssessment(result);}
    catch(error){if(ticket===revision.current)notify(error.message,true);}
    finally{if(ticket===revision.current)setBusy(false);}
  }
  async function loadSample(number=count,merge=false){
    const ticket=++revision.current;setBusy(true);
    try{
      const fixture=await request('/nutrition/sample?count='+number);
      if(ticket!==revision.current)return;
      const nextProfiles=merge?fixture.profiles.map(p=>profiles.find(old=>old.profile_id===p.profile_id)||p):fixture.profiles;
      const ids=new Set(nextProfiles.map(p=>p.profile_id)),oldIds=new Set(profiles.map(p=>p.profile_id));
      const nextEntries=merge?[...entries.filter(e=>ids.has(e.profile_id)),...fixture.entries.filter(e=>!oldIds.has(e.profile_id))]:fixture.entries;
      const nextComplete=merge?{...fixture.complete_days,...Object.fromEntries(Object.entries(complete).filter(([key])=>ids.has(key.split(':')[0])))}:fixture.complete_days;
      const selectedDay=Math.min(day,7);
      const result=await request('/nutrition/assess',{profiles:nextProfiles,entries:nextEntries,complete_days:nextComplete,day:selectedDay});
      if(ticket!==revision.current)return;
      setSample(fixture);setProfiles(nextProfiles);setEntries(nextEntries);setComplete(nextComplete);setDay(selectedDay);setAssessment(result);
      setPerson(old=>ids.has(old)?old:nextProfiles[0]?.profile_id||'');setName('SAMPLE · Named crew and dietary logs');
      if(!merge)notify('Fictional named crew, food logs and blood examples loaded. Mission planning inputs are unchanged.');
    }catch(error){if(ticket===revision.current)notify(error.message,true);}
    finally{if(ticket===revision.current)setBusy(false);}
  }
  useEffect(()=>{
    if(rosterKey!=='null' && previousRoster.current!==rosterKey){
      previousRoster.current=rosterKey;previousCount.current=count;
      invalidate();setProfiles(clone(datedRoster));
      setPerson(old=>datedRoster.some(p=>p.profile_id===old)?old:datedRoster[0]?.profile_id||'');
      return;
    }
    if(rosterKey!=='null'){previousCount.current=count;return;}
    if(previousRoster.current!=='null'){
      previousRoster.current='null';previousCount.current=count;
      if(sample)loadSample(count,false);
      return;
    }
    if(previousCount.current===count)return;
    previousCount.current=count;
    if(sample)loadSample(count,true);
  },[count,rosterKey]);
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
  return <>
    <div className="page-heading"><div><span className="eyebrow">CREW · NUTRITION · BLOOD EXAMPLES</span><h1>Nutrition assessment</h1><p>Compare each crew member’s dietary intake with their planning targets, and view separate fictional blood-test examples.</p></div><button className="btn" disabled={busy} onClick={()=>loadSample()}>Load named sample crew</button></div>
    <p className="muted">{profiles.length} profiles · {activeCrew} mission crew at simulated Day {missionDay}. Added sample profiles are numbered; missing blood tests remain unknown.</p>
    {run?.metadata && navigate && <div className="actions"><button className="btn" onClick={()=>navigate('simulator')}>Change crew during this mission</button><span className="muted">Apply future needs from a chosen day while keeping completed mission history.</span></div>}
    <CrewHealthGraphs sample={sample} profiles={profiles} assessments={assessment?.rows||[]} day={day} onDayChange={value=>assessDay(value)}/>
    {!assessment&&<p className="notice">Food logs or targets changed. Assess recorded intake to refresh the nutrition graph; blood examples remain separate.</p>}
    <details className="panel" open={!sample}><summary>Crew profiles and daily targets</summary><div className="section-heading"><h2>Edit crew profiles</h2><button className="btn" disabled={profiles.length>=12||busy} onClick={addProfile}>Add crew profile</button></div>
      <div className="table-wrap"><table><thead><tr><th>Alias</th><th>Energy kcal</th><th>Protein g</th><th>Vitamin C mg</th><th>Age (optional)</th><th>Reference sex</th><th>Targets reviewed</th><th/></tr></thead><tbody>{profiles.map((p,i)=>
        <tr key={p.profile_id}><td><input aria-label={'Alias '+(i+1)} value={p.name} onChange={e=>edit(i,'name',e.target.value)}/></td>
          {Object.keys(units).map(n=><td key={n}><input aria-label={p.name+' '+n+' target'} type="number" min={0} step="any" value={p.targets[n]??''} onChange={e=>edit(i,'targets',{...p.targets,[n]:Number(e.target.value)})}/></td>)}
          <td><input aria-label={p.name+' age'} type="number" min={0} step={1} value={p.age??''} onChange={e=>edit(i,'age',e.target.value===''?null:Number(e.target.value))}/></td>
          <td><select aria-label={p.name+' reference sex'} value={p.sex} onChange={e=>edit(i,'sex',e.target.value)}><option value="unspecified">Unspecified</option><option value="male">Male</option><option value="female">Female</option></select></td>
          <td><input aria-label={p.name+' reviewed targets'} type="checkbox" checked={p.targets_reviewed} onChange={e=>edit(i,'targets_reviewed',e.target.checked)}/></td>
          <td><button className="text-button" onClick={()=>{setProfiles(v=>v.filter(row=>row.profile_id!==p.profile_id));setEntries(v=>v.filter(row=>row.profile_id!==p.profile_id));if(person===p.profile_id)setPerson(profiles.find(row=>row.profile_id!==p.profile_id)?.profile_id||'');invalidate();}}>Remove</button></td>
        </tr>)}</tbody></table></div>
      <div className="notice">Energy and protein targets are manually reviewed inputs. Optional NIH vitamin C healthy-adult references are 90 mg/day for men and 75 mg/day for women; the adult upper limit is 2,000 mg/day. These references exclude pregnancy, lactation and smoking and are not astronaut prescriptions. <a href="https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/" target="_blank" rel="noreferrer">Read NIH source</a></div>
      <button className="btn" disabled={busy||profiles.length!==config.crew} onClick={()=>task(async()=>{const result=await request('/nutrition/apply-targets',{config,profiles});setConfig(result.config);})}>Apply mean reviewed targets to planner</button>
      <p className="muted">Profile count ({profiles.length}) must match planner crew ({config.crew}). Applying mean targets retains shared crew allocations; it does not generate individual menus.</p>
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
      {snapshots.map(s=><div className="archive-row" key={s.id}><div><strong>{s.name}</strong><small>{new Date(s.created_at_utc).toLocaleString()}</small></div><button className="btn" disabled={busy} onClick={()=>restoreSnapshot(s.id)}>Restore intake snapshot</button></div>)}
    </section>
  </>;
}
