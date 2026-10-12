import React,{useEffect,useState} from 'react';

const percent=value=>value==null?'Unavailable':(Math.round(value*1000)/10).toFixed(1)+'%';
const number=value=>value==null?'Unavailable':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});

export default function ModelEvidence({request,notify,setPlantModel,Chart,focus='plant'}) {
  const [evidence,setEvidence]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState('base'),[busy,setBusy]=useState(false);
  useEffect(()=>{let active=true; request('/models').then(data=>{if(active){setEvidence(data);setSelected(data.plant.active_id==='unavailable'?'base':data.plant.active_id);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[request]);
  async function select(){setBusy(true);try{const data=await request('/models/plant/select',{candidate_id:selected});setPlantModel?.(data.plant_model);setEvidence(v=>({...v,plant:data.registry}));notify('Plant model selected. Screen a new image to use this version.');}catch(e){notify(e.message,true);}finally{setBusy(false);}}
  return <details className="panel model-evidence"><summary>{focus==='plant'?'Model versions and evaluation':'Measured growth and crop response'}</summary>
    {error&&<p role="alert">Model evidence could not be loaded: {error}</p>}
    {!error&&!evidence&&<p className="muted">Loading recorded model evidence…</p>}
    {evidence&&focus==='plant'&&<>
      <p className="muted">Active model: {evidence.plant.active_id}. Training runs locally through the training launcher; opening this section does not train a model.</p>
      <label className="field"><span>Plant model version</span><select value={selected} onChange={e=>setSelected(e.target.value)}><option value="base">Original pretrained model</option>{evidence.plant.candidates.map(model=><option key={model.candidate_id} value={model.candidate_id} disabled={!model.ready||!model.eligible}>{model.candidate_id}{!model.eligible?' · evaluation gate not met':''}</option>)}</select></label>
      <button className="btn" disabled={busy||selected===evidence.plant.active_id} onClick={select}>{busy?'Selecting…':'Use selected model'}</button>
      {!evidence.plant.candidates.length&&<p className="muted">No completed fine-tuning run is recorded yet.</p>}
      {evidence.plant.candidates.map(model=><section key={model.candidate_id} style={{marginTop:24}}><h2>{model.candidate_id}</h2><p className="muted">{model.reason}</p>{model.metrics&&<>
        <div className="metrics-row model-metrics"><div className="metric"><span>Held-out accuracy</span><strong>{percent(model.metrics.accuracy)}</strong><small>Original: {percent(model.baseline_metrics.accuracy)}</small></div><div className="metric"><span>Present-class macro F1</span><strong>{number(model.metrics.macro_f1)}</strong><small>Original: {number(model.baseline_metrics.macro_f1)}</small></div><div className="metric"><span>Test images</span><strong>{model.metrics.known_samples}</strong><small>{model.tested_classes.length} / {model.output_classes} output classes evaluated</small></div></div>
        <p className="muted">Confidence temperature fitted on validation images only: {number(model.temperature)}. Held-out accepted coverage: {percent(model.metrics.abstention?.coverage)}. These are source-dataset measurements, not tray accuracy.</p>
        <p className="muted">Accepted visual matches: {model.metrics.abstention?.accepted_known_count ?? 'Unavailable'} / {model.metrics.known_samples} test images. Accuracy among accepted images: {percent(model.metrics.abstention?.selective_accuracy)}. Few accepted images do not establish reliable screening; unfamiliar-object rejection has not been measured here.</p>
        {model.metrics.per_class&&<details><summary>Results by class</summary><div className="table-wrap"><table><thead><tr><th>Class</th><th>Test images</th><th>Recall</th><th>F1</th></tr></thead><tbody>{model.metrics.per_class.map(row=><tr key={row.label}><td>{row.label.replaceAll('_',' ')}</td><td>{row.support}</td><td>{percent(row.recall)}</td><td>{number(row.f1)}</td></tr>)}</tbody></table></div></details>}
      </>}{model.limitations?.map(text=><p className="muted" key={text}>{text}</p>)}</section>)}
    </>}
    {evidence&&focus==='crops'&&<>
      <h2 style={{marginTop:24}}>Measured lettuce growth</h2><p className="muted">Status: {evidence.growth.status}. {evidence.growth.record_count} measured plant/day records across {evidence.growth.independent_cycle_count} independent cycle(s).</p>
      {evidence.growth.validation&&<p>Held-out fresh-mass MAE: {number(evidence.growth.validation.curve?.mae_g_per_plant)} g/plant. Whole plants are withheld; the source plants share one growing cycle.</p>}
      {Chart&&evidence.growth.parameters&&<Chart data={evidence.growth.parameters.ages_days_after_transplant.map((day,i)=>({day,fresh_mass_g:evidence.growth.parameters.fitted_fresh_mass_g[i]}))} lines={[{key:'fresh_mass_g',name:'Fitted source fresh mass'}]} unit=" g" height={220} labelPrefix="Days after transplant"/>}
      <p className="muted">A source-specific age curve. Whole fresh mass is not confirmed edible yield. It does not replace the planner's harvest endpoint or establish a resource-stress response.</p>
      <h2 style={{marginTop:24}}>Environmental response calibration</h2><p className="muted">Status: {evidence.crop_response.status}. Real repeated cycles and matched environmental measurements are required before fitting a tray response.</p>
      <button className="btn" onClick={async()=>{try{const response=await fetch('/api/models/crop-trial-template');if(!response.ok)throw new Error('Template could not be loaded');const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download='astra-bio-crop-trials.csv';anchor.click();URL.revokeObjectURL(url);}catch(e){notify(e.message,true);}}}>Download blank crop-trial template</button>
      <p className="muted">Record actual cycle IDs, cultivar, environment, fresh mass, area, light, net makeup water and equipment power. Sensors provide exposures; harvest weights and independent cycles provide training ground truth.</p>
    </>}
  </details>;
}
