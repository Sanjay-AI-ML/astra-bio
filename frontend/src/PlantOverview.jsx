import React, {useEffect, useRef, useState} from 'react';
import './plant-overview.css';

const crops=['tomato','bell pepper','potato'];
const modelNames={'tomato-ripeness-3':'Tomato maturity · 3 stages','tomato-ripeness-6':'Tomato maturity · 6 stages','tomato-detection':'Tomato counts','produce-detection':'Visible produce · counts only'};
const speciesKey=value=>String(value||'').toLowerCase().replaceAll('_',' ').replaceAll('-',' ').replace('capsicum','bell pepper').trim();
const supportsCrop=(model,crop)=>Array.isArray(model?.species)&&model.species.some(value=>speciesKey(value)===crop);
const MAX_BYTES=10*1024*1024;
const score=value=>Number.isFinite(value)?Math.round(value*100)+'%':'Unavailable';
const leafScore=value=>Number.isFinite(value)?value.toFixed(3):'Unavailable';
const validBox=box=>Array.isArray(box)&&box.length===4&&box.every(value=>Number.isFinite(value)&&value>=0&&value<=1)&&box[2]>box[0]&&box[3]>box[1];
const leafOutcome=leaf=>({tentative:'Tentative leaf match',uncertain:'Model prediction needs review',rejected:'Crop mismatch · result withheld',unavailable:'Leaf model unavailable'})[leaf?.status]||'Leaf result unresolved';

function LeafEvidence({leaf,fallbackReason}){
  const summary=leaf?.screening_summary;
  const predictions=Array.isArray(leaf?.predictions)?leaf.predictions.slice(0,3):[];
  const checks=Array.isArray(summary?.checks)?summary.checks:[];
  const nextSteps=Array.isArray(summary?.next_steps)&&summary.next_steps.length?summary.next_steps:leaf?.status==='uncertain'?['Retake one sharp leaf close-up in even light. Let the leaf fill most of the frame.','Check the selected species, then inspect both sides of the leaf.']:leaf?.status==='rejected'?['Check the selected species and upload a clear photograph of one matching leaf.']:[];
  const checkValue=(value,unit)=>unit==='boolean'&&typeof value==='boolean'?(value?'Yes':'No'):Number.isFinite(value)?(unit==='ratio'?leafScore(value):`${Number(value.toFixed(3))}${unit==='%'?'%':unit?' '+unit:''}`):'Unavailable';
  return <div className="leaf-screening-evidence">
    {['rejected','unavailable'].includes(leaf?.status)&&<p className="leaf-screening-summary">{summary?.summary||fallbackReason||'Leaf detail could not be assessed in this photograph.'}</p>}
    {leaf?.status==='tentative'&&predictions.map((row,index)=><p className="plant-overview-evidence" key={index}><span>{row.condition}</span><strong>{leafScore(row.score)} model score</strong></p>)}
    {leaf?.status==='rejected'&&nextSteps.length>0&&<div className="leaf-screening-next"><h3>Next steps</h3><ul>{nextSteps.map((text,index)=><li key={index}>{text}</li>)}</ul></div>}
    {leaf?.status==='uncertain'&&predictions.length>0&&<section className="leaf-screening-matches" aria-label="Unconfirmed model matches"><h3>Closest model matches · unconfirmed</h3>{predictions.map((row,index)=><p className="plant-overview-evidence" key={index}><span>{row.condition}</span><strong>{leafScore(row.score)} model score</strong></p>)}</section>}
    {checks.length>0&&<details className="leaf-screening-details" open={leaf?.status==='uncertain'}><summary>Why this result?</summary><div className="table-wrap"><table aria-label="Leaf screening reliability checks"><thead><tr><th>Check</th><th>Value</th><th>Required</th><th>Result</th></tr></thead><tbody>{checks.map((row,index)=><tr key={index}><td>{row.label}</td><td>{checkValue(row.actual,row.unit)}</td><td>{checkValue(row.required,row.unit)}</td><td>{row.passed?'Met':'Not met'}</td></tr>)}</tbody></table></div></details>}
  </div>;
}

function Photograph({file,label,detections=[],caption}){
  const [preview,setPreview]=useState('');
  const [size,setSize]=useState(null);
  useEffect(()=>{setSize(null);if(!file){setPreview('');return;}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
  const fontSize=size?Math.max(12,Math.min(size.width,size.height)*.028):12;
  return preview?<figure className="plant-overview-photo"><div className="plant-overview-image-frame"><img src={preview} alt={label} onLoad={event=>{const image=event.currentTarget;setSize({width:image.naturalWidth,height:image.naturalHeight});}}/>
    {size?.width>0&&size?.height>0&&detections.some(row=>validBox(row.box))&&<svg className="plant-overview-fruit-markers" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label="Numbered fruit detections on the plant photograph">{detections.map((row,index)=>{
      if(!validBox(row.box))return null;
      const [x1,y1,x2,y2]=row.box,x=x1*size.width,y=y1*size.height;
      const labelWidth=String(index+1).length*fontSize*.7+fontSize*.5,labelX=Math.min(x,size.width-labelWidth),labelY=Math.max(fontSize*1.4,y);
      return <g key={row.id??index}><title>{`${index+1} · ${row.stage||row.class_label||'Visible produce'} · ${score(row.score)} model score`}</title><rect data-testid="plant-fruit-box" x={x} y={y} width={(x2-x1)*size.width} height={(y2-y1)*size.height} fill="none" stroke="#f3e88b" strokeWidth={Math.max(2,fontSize/7)}/><rect x={labelX} y={labelY-fontSize*1.4} width={labelWidth} height={fontSize*1.4} rx={fontSize*.12} fill="#145c3e"/><text x={labelX+fontSize*.25} y={labelY-fontSize*.3} fontSize={fontSize} fill="white">{index+1}</text></g>;
    })}</svg>}
    </div><figcaption>{caption||(detections.length?'Numbered fruit detections are listed below.':label)}</figcaption></figure>:null;
}

export default function PlantOverview({request,mode='combined'}){
  const leafOnly=mode==='leaf',fruitOnly=mode==='fruit';
  const [crop,setCrop]=useState('tomato'),[plantId,setPlantId]=useState('Plant 01'),[model,setModel]=useState('tomato-ripeness-3');
  const [photo,setPhoto]=useState(null),[leafPhoto,setLeafPhoto]=useState(null);
  const [report,setReport]=useState(null),[overview,setOverview]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [ai,setAi]=useState(null),[leafModel,setLeafModel]=useState(null),[catalog,setCatalog]=useState(null);
  const [availabilityError,setAvailabilityError]=useState(''),[reload,setReload]=useState(0);
  const revision=useRef(0);
  const leafInput=useRef(null);
  useEffect(()=>{
    let active=true;setAvailabilityError('');setLeafModel(null);setCatalog(null);
    if(!fruitOnly)request('/plant-overview/status').then(value=>{if(active){setAi(value.ai);setLeafModel(value.leaf_model||{ready:false});}}).catch(()=>{if(active){setLeafModel({ready:false});setAvailabilityError('Could not check leaf model availability.');}});
    if(!leafOnly)request('/fruit-models').then(value=>{if(active)setCatalog(value);}).catch(()=>{if(active){setCatalog({models:[]});setAvailabilityError('Could not check fruit model availability.');}});
    return()=>{active=false;revision.current++;};
  },[request,leafOnly,fruitOnly,reload]);
  const models=(Array.isArray(catalog?.models)?catalog.models:[]).filter(value=>value.ready===true&&supportsCrop(value,crop)&&Array.isArray(value.labels)&&value.labels.length>0);
  const selectedModel=models.find(value=>value.id===model);
  useEffect(()=>{if(!selectedModel)setModel(models.find(value=>value.id===catalog?.default_model_id)?.id||models[0]?.id||'');},[catalog,crop,model]);
  const modelReady=leafOnly?leafModel?.ready===true:fruitOnly?!!selectedModel:leafModel?.ready===true||!!selectedModel;
  const availabilityLoading=leafOnly?leafModel===null:fruitOnly?catalog===null:leafModel===null||catalog===null;
  function change(fn){revision.current++;setReport(null);setOverview(null);setError('');setBusy('');fn();}
  function clearLeaf(){setLeafPhoto(null);if(leafInput.current)leafInput.current.value='';}
  function pick(event,isLeaf=false){
    const files=event.target.files,file=files?.[0]||null,setFile=isLeaf?setLeafPhoto:setPhoto;
    change(()=>{setFile(file);if(!isLeaf)clearLeaf();});
    if(files?.length>1){setFile(null);setError(isLeaf?'Choose one leaf close-up.':'Choose one plant photograph.');}
    else if(file&&!['image/jpeg','image/png','image/webp'].includes(file.type)){setFile(null);setError('Choose a JPEG, PNG or WebP photograph.');}
  }
  async function screen(event){
    event.preventDefault();
    if(!photo||!modelReady||busy)return;
    if(photo.size>MAX_BYTES){setError('Keep the plant photograph within 10 MiB.');return;}
    if(leafPhoto?.size>MAX_BYTES){setError('Keep the leaf close-up within 10 MiB.');return;}
    const token=++revision.current;
    const form=new FormData();form.append('crop_species',crop);form.append('plant_id',plantId);if(!leafOnly&&model)form.append('fruit_model_id',model);form.append('screening_mode',mode);form.append('file',photo);
    if(!leafOnly&&leafPhoto)form.append('leaf_file',leafPhoto);
    setBusy('screen');setError('');setReport(null);setOverview(null);
    try{const value=await request('/plant-overview',form);if(token!==revision.current)return;setReport(value);setOverview(value.overview);setAi(value.ai);}catch(failure){if(token===revision.current)setError(failure.message);}finally{if(token===revision.current)setBusy('');}
  }
  async function summarize(){
    if(!report||!ai?.configured)return;
    const token=++revision.current;setBusy('ai');setError('');
    try{const result=await request('/plant-overview/ai',{evidence_id:report.evidence_id});if(token===revision.current)setOverview(result);}catch(failure){if(token===revision.current)setError(failure.message);}finally{if(token===revision.current)setBusy('');}
  }
  function exportOverview(){const url=URL.createObjectURL(new Blob([JSON.stringify({...report,overview},null,2)],{type:'application/json'}));const anchor=document.createElement('a');anchor.href=url;anchor.download=leafOnly?'astra-bio-leaf-screening.json':fruitOnly?'astra-bio-fruit-checking.json':'astra-bio-plant-overview.json';anchor.click();URL.revokeObjectURL(url);}
  const detections=report?.fruit?.status==='observed'?(report.fruit.detections||[]):[];
  const usingCloseup=report?.leaf_input_source==='leaf_closeup'||report?.leaf?.input_source==='leaf_closeup';
  const leafReason=report?.leaf?.status==='unavailable'?'The leaf model could not run. Retry when the service is available.':report?.leaf?.reason;
  const leafStatus=({tentative:'Tentative leaf match',uncertain:'Uncertain leaf result',rejected:'Leaf result withheld',unavailable:'Leaf model unavailable'})[report?.leaf?.status]||'Leaf result unresolved';
  const fruitStatus=({observed:'Visible produce observed',no_detections:'No produce found',rejected:'Image needs review',unavailable:'Fruit model unavailable'})[report?.fruit?.status]||'Fruit result unresolved';
  const fruitReason=report?.fruit?.status==='unavailable'?'The fruit model could not run. Retry when the service is available.':report?.fruit?.status==='no_detections'?'No visible produce was found in this photograph.':report?.fruit?.reason;
  return <section className="plant-overview" aria-labelledby={leafOnly||fruitOnly?undefined:'plant-overview-heading'} aria-label={leafOnly?'Leaf screening form':fruitOnly?'Fruit checking form':undefined}>
    {!leafOnly&&!fruitOnly&&<div className="plant-overview-heading"><span className="eyebrow">LEAF CONDITION · VISIBLE FRUIT</span><h2 id="plant-overview-heading">Inspect leaves and fruit.</h2><p>Upload a plant photograph. Add a close-up from the same plant for clearer leaf screening.</p></div>}
    <form onSubmit={screen}>
      <div className={'plant-overview-controls'+(leafOnly?' plant-overview-controls-two':'')}><label className="field"><span>Plant or batch label</span><input maxLength={64} required value={plantId} onChange={e=>change(()=>setPlantId(e.target.value))}/></label><label className="field"><span>Plant species</span><select value={crop} onChange={e=>change(()=>setCrop(e.target.value))}>{crops.map(value=><option key={value}>{value}</option>)}</select></label>{!leafOnly&&<label className="field"><span>Fruit observation model</span><select value={model} disabled={!models.length} onChange={e=>change(()=>setModel(e.target.value))}>{!models.length&&<option value="">{catalog?'No available model':'Checking availability…'}</option>}{models.map(value=><option value={value.id} key={value.id}>{modelNames[value.id]||value.name||value.id}</option>)}</select></label>}</div>
      <div className={'plant-overview-photos'+(leafOnly||fruitOnly?' plant-overview-single-photo':'')}>
        <div className="plant-overview-upload"><label className="field"><span>{leafOnly?'Leaf photograph':'Plant photograph'}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={event=>pick(event)}/></label><Photograph file={photo} label={leafOnly?'Selected leaf photograph':'Selected plant photograph'} detections={leafOnly?[]:detections} caption={detections.length?'Numbered detections match the observations below.':leafOnly?'One leaf should fill most of the frame.':fruitOnly?(crop==='potato'?'Use exposed potato tubers. Underground tubers cannot be seen.':'Keep the produce clearly visible.'):'Plant photograph'}/></div>
        {!leafOnly&&!fruitOnly&&<div className="plant-overview-upload plant-overview-leaf-upload"><label className="field"><span>Leaf close-up (optional)</span><input ref={leafInput} type="file" accept="image/jpeg,image/png,image/webp" onChange={event=>pick(event,true)}/></label><Photograph file={leafPhoto} label="Selected leaf close-up" caption="Leaf screening uses this close-up."/>{leafPhoto&&<button className="btn" type="button" onClick={()=>change(clearLeaf)}>Remove leaf close-up</button>}</div>}
      </div>
      <p className="muted">JPEG, PNG or WebP · up to 10 MiB.</p>
      {availabilityLoading&&!modelReady&&<p role="status" className="muted">Checking model availability…</p>}
      {!fruitOnly&&leafModel?.ready===false&&<p role="status" className="notice warning">Leaf screening is temporarily unavailable. The service needs its leaf model installed.</p>}
      {!leafOnly&&catalog!==null&&!models.length&&<p role="status" className="notice warning">Fruit checking is unavailable for {crop}. The service needs a compatible fruit model.</p>}
      {availabilityError&&<p role="alert" className="notice warning">{availabilityError}</p>}
      {!availabilityLoading&&!modelReady&&<button className="text-button" type="button" onClick={()=>setReload(value=>value+1)}>Retry availability</button>}
      <div className="actions"><button className="btn primary" type="submit" disabled={!!busy||!photo||!modelReady}>{busy==='screen'?'Analyzing…':leafOnly?'Screen leaf':fruitOnly?'Check fruit':'Analyze plant'}</button></div>
      {error&&<p role="alert" className="notice warning">{error}</p>}
    </form>
    {report&&!overview&&leafOnly&&<section className="plant-overview-result" aria-live="polite" aria-label="Leaf screening result"><div className="section-heading"><div><span className="eyebrow">{report.plant_id} · {report.crop_species}</span><h2>{report.leaf?.status==='uncertain'?leafOutcome(report.leaf):report.leaf?.screening_summary?.title||leafOutcome(report.leaf)}</h2></div><span className="pill">{report.leaf?.status==='uncertain'?'Model ran · review required':leafStatus}</span></div><LeafEvidence leaf={report.leaf} fallbackReason={leafReason}/><button className="btn" type="button" onClick={exportOverview}>Export screening evidence</button></section>}
    {report&&!overview&&fruitOnly&&<section className="plant-overview-result" aria-live="polite" aria-label="Fruit checking result"><div className="section-heading"><div><span className="eyebrow">{report.plant_id} · {report.crop_species}</span><h2>Fruit checking result</h2></div><span className="pill">{fruitStatus}</span></div><p>{fruitReason||'Fruit detail could not be assessed in this photograph.'}</p>{['observed','no_detections'].includes(report.fruit?.status)&&<><strong>{report.fruit.visible_count} visible detections</strong>{Object.entries(report.fruit.counts_by_stage||{}).map(([stage,count])=><p className="plant-overview-evidence" key={stage}><span>{stage}</span><strong>{count}</strong></p>)}</>}{detections.length>0&&<details><summary>Individual fruit observations</summary><div className="table-wrap"><table aria-label="Fruit detections"><thead><tr><th>Number</th><th>Visual stage</th><th>Model score</th></tr></thead><tbody>{detections.map((row,index)=><tr key={row.id??index}><td>{index+1}</td><td>{row.stage||row.class_label||'Not assessed'}</td><td>{score(row.score)}</td></tr>)}</tbody></table></div></details>}</section>}
    {(leafOnly||fruitOnly)&&<div className="plant-overview-limits"><p className="muted">{leafOnly?'Visual matches guide inspection; they do not confirm disease.':'Visible counts and maturity cues require review; they do not confirm food safety.'}</p><details><summary>Screening limits</summary><p>{leafOnly?'Model scores are similarity scores, not probabilities of a correct diagnosis. Use one sharp leaf photograph; the classifier does not locate individual leaves.':'Hidden produce may be missed, and repeated views can count the same fruit again. Potato checking covers exposed tubers; generic produce models provide counts without ripeness.'}</p><p>These terrestrial models have not been validated in space or under your growing conditions. Results do not change inventory or trigger treatment or hardware actions.</p></details></div>}
    {overview&&<section className="plant-overview-result" aria-label="Combined plant overview" aria-live="polite">
      <div className="section-heading"><div><span className="eyebrow">{report.plant_id} · {report.crop_species}</span><h2>Plant overview</h2></div><span className="pill">{overview.mode==='gemini_fact_selection'?'AI-curated evidence':'Evidence summary'}</span></div>
      <p className="plant-overview-brief">{overview.brief_overview}</p>
      <div className="plant-overview-observations"><section><h3>{usingCloseup?'Leaf close-up':'Leaves in plant photo'}</h3><span className="pill">{leafStatus}</span><p>{leafReason||'Leaf detail could not be assessed in this photograph.'}</p>{report.leaf?.status==='tentative'&&report.leaf?.predictions?.slice(0,3).map((row,i)=><p className="plant-overview-evidence" key={i}><span>{row.condition}</span><strong>{leafScore(row.score)} model score</strong></p>)}{report.leaf?.status!=='tentative'&&!usingCloseup&&<p className="plant-overview-leaf-help">Add a leaf close-up above and analyze again. Fruit counts can remain usable while leaf condition is unresolved.</p>}</section><section><h3>Fruit in plant photo</h3><p>{report.fruit?.reason||'Fruit detail could not be assessed in this photograph.'}</p>{report.fruit?.status==='observed'&&<><strong>{report.fruit.visible_count} visible detections</strong>{Object.entries(report.fruit.counts_by_stage||{}).map(([stage,count])=><p className="plant-overview-evidence" key={stage}><span>{stage}</span><strong>{count}</strong></p>)}</>}{detections.length>0&&<details><summary>Individual fruit observations</summary><div className="table-wrap"><table aria-label="Fruit markers in the plant photograph"><thead><tr><th>Marker</th><th>Visual stage</th><th>Model score</th></tr></thead><tbody>{detections.map((row,index)=><tr key={row.id??index}><td>{index+1}</td><td>{row.stage||row.class_label||'Not assessed'}</td><td>{score(row.score)}</td></tr>)}</tbody></table></div></details>}</section></div>
      <div className="plant-overview-observations"><section><h3>What to check next</h3><ul>{overview.next_steps.map((text,i)=><li key={i}>{text}</li>)}</ul></section><section><h3>How to use this observation</h3>{overview.possible_use.map((text,i)=><p key={i}>{text}</p>)}</section></div>
      <details><summary>Evidence limits & sources</summary>{overview.limitations.map((text,i)=><p className="muted" key={i}>{text}</p>)}{overview.references?.map(item=><a className="source-link" key={item.url} href={item.url} target="_blank" rel="noreferrer">{item.title}</a>)}</details>
      {ai?.configured&&<div className="plant-overview-ai"><div><h3>Brief AI summary</h3><p>Summarize the existing evidence. Only result text is sent to Gemini; images stay with the screening service.</p>{overview.fallback_reason&&<p role="status">{overview.fallback_reason}</p>}</div><button className="btn" type="button" disabled={!!busy} onClick={summarize}>{busy==='ai'?'Curating overview…':'Create brief Gemini overview'}</button></div>}
      <button className="btn" type="button" onClick={exportOverview}>Export combined overview</button>
    </section>}
  </section>;
}
