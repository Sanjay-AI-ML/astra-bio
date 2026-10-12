import React, {useEffect, useRef, useState} from 'react';
import './plant-overview.css';

const crops=['tomato','bell pepper','potato'];
const modelNames={'tomato-ripeness-3':'Tomato maturity · 3 stages','tomato-ripeness-6':'Tomato maturity · 6 stages','tomato-detection':'Tomato counts','produce-detection':'Visible produce · counts only'};
const MAX_BYTES=10*1024*1024;
const score=value=>Number.isFinite(value)?Math.round(value*100)+'%':'Unavailable';
const validBox=box=>Array.isArray(box)&&box.length===4&&box.every(value=>Number.isFinite(value)&&value>=0&&value<=1)&&box[2]>box[0]&&box[3]>box[1];

function Photograph({file,label,detections=[]}){
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
    </div><figcaption>{detections.length?'Numbered fruit detections are listed below. Leaf analysis uses the whole photo.':label}</figcaption></figure>:null;
}

export default function PlantOverview({request}){
  const [crop,setCrop]=useState('tomato'),[plantId,setPlantId]=useState('Plant 01'),[model,setModel]=useState('tomato-ripeness-3');
  const [photo,setPhoto]=useState(null);
  const [report,setReport]=useState(null),[overview,setOverview]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [ai,setAi]=useState(null);
  const revision=useRef(0);
  useEffect(()=>{let active=true;request('/plant-overview/status').then(value=>{if(active)setAi(value.ai);}).catch(()=>{});return()=>{active=false;revision.current++;};},[request]);
  function change(fn){revision.current++;setReport(null);setOverview(null);setError('');setBusy('');fn();}
  function pick(event){const files=event.target.files;const file=files?.[0]||null;change(()=>setPhoto(file));if(files?.length>1){setPhoto(null);setError('Choose one plant photograph.');}else if(file&&!['image/jpeg','image/png','image/webp'].includes(file.type)){setPhoto(null);setError('Choose a JPEG, PNG or WebP photograph.');}}
  async function screen(event){
    event.preventDefault();
    if(!photo)return;
    if(photo.size>MAX_BYTES){setError('Keep the plant photograph within 10 MiB.');return;}
    const token=++revision.current;
    const form=new FormData();form.append('crop_species',crop);form.append('plant_id',plantId);form.append('fruit_model_id',model);form.append('file',photo);
    setBusy('screen');setError('');setReport(null);setOverview(null);
    try{const value=await request('/plant-overview',form);if(token!==revision.current)return;setReport(value);setOverview(value.overview);setAi(value.ai);}catch(failure){if(token===revision.current)setError(failure.message);}finally{if(token===revision.current)setBusy('');}
  }
  async function summarize(){
    if(!report||!ai?.configured)return;
    const token=++revision.current;setBusy('ai');setError('');
    try{const result=await request('/plant-overview/ai',{evidence_id:report.evidence_id});if(token===revision.current)setOverview(result);}catch(failure){if(token===revision.current)setError(failure.message);}finally{if(token===revision.current)setBusy('');}
  }
  function exportOverview(){const url=URL.createObjectURL(new Blob([JSON.stringify({...report,overview},null,2)],{type:'application/json'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='astra-bio-plant-overview.json';anchor.click();URL.revokeObjectURL(url);}
  const models=crop==='tomato'?Object.keys(modelNames):['produce-detection'];
  const detections=report?.fruit?.status==='observed'?(report.fruit.detections||[]):[];
  const leafReason=report?.leaf?.reason?.replace('retake a clear single-leaf photograph','retake a clear plant photograph with a prominent leaf');
  return <section className="plant-overview" aria-labelledby="plant-overview-heading">
    <div className="plant-overview-heading"><span className="eyebrow">ONE PHOTO · LEAF + FRUIT ANALYSIS</span><h2 id="plant-overview-heading">One plant. One photograph.</h2><p>Upload a clear photo with visible leaves and fruit where present. Both local models analyze the same image and bring their observations together below.</p></div>
    <form onSubmit={screen}>
      <div className="plant-overview-controls"><label className="field"><span>Plant or batch label</span><input maxLength={64} required value={plantId} onChange={e=>change(()=>setPlantId(e.target.value))}/></label><label className="field"><span>Plant species</span><select value={crop} onChange={e=>change(()=>{setCrop(e.target.value);if(e.target.value!=='tomato')setModel('produce-detection');})}>{crops.map(value=><option key={value}>{value}</option>)}</select></label><label className="field"><span>Fruit observation model</span><select value={model} onChange={e=>change(()=>setModel(e.target.value))}>{models.map(id=><option value={id} key={id}>{modelNames[id]}</option>)}</select></label></div>
      <div className="plant-overview-upload"><label className="field"><span>Plant photograph</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={pick}/></label><Photograph file={photo} label="One photograph used for leaf and fruit analysis" detections={detections}/></div>
      <p className="muted">JPEG, PNG or WebP · one image up to 10 MiB. Small or hidden leaves and fruit may remain unresolved.</p>
      <div className="actions"><button className="btn primary" type="submit" disabled={!!busy||!photo}>{busy==='screen'?'Analyzing the plant…':'Analyze plant'}</button><small className="muted">The photograph stays in local inference.</small></div>
      {error&&<p role="alert" className="notice warning">{error}</p>}
    </form>
    {overview&&<section className="plant-overview-result" aria-label="Combined plant overview" aria-live="polite">
      <div className="section-heading"><div><span className="eyebrow">{report.plant_id} · {report.crop_species}</span><h2>Plant overview</h2></div><span className="pill">{overview.mode==='gemini_fact_selection'?'AI-curated evidence':'Local evidence summary'}</span></div>
      <p className="plant-overview-brief">{overview.brief_overview}</p>
      <div className="plant-overview-observations"><section><h3>Leaves in this photo</h3><p>{leafReason||'Leaf detail could not be assessed in this photograph.'}</p>{report.leaf?.status==='tentative'&&report.leaf?.predictions?.slice(0,3).map((row,i)=><p className="plant-overview-evidence" key={i}><span>{row.condition}</span><strong>{score(row.score)} model score</strong></p>)}</section><section><h3>Fruit in this photo</h3><p>{report.fruit?.reason||'Fruit detail could not be assessed in this photograph.'}</p>{report.fruit?.status==='observed'&&<><strong>{report.fruit.visible_count} visible detections</strong>{Object.entries(report.fruit.counts_by_stage||{}).map(([stage,count])=><p className="plant-overview-evidence" key={stage}><span>{stage}</span><strong>{count}</strong></p>)}</>}{detections.length>0&&<details><summary>Individual fruit observations</summary><div className="table-wrap"><table aria-label="Fruit markers in the plant photograph"><thead><tr><th>Marker</th><th>Visual stage</th><th>Model score</th></tr></thead><tbody>{detections.map((row,index)=><tr key={row.id??index}><td>{index+1}</td><td>{row.stage||row.class_label||'Not assessed'}</td><td>{score(row.score)}</td></tr>)}</tbody></table></div></details>}</section></div>
      <div className="plant-overview-observations"><section><h3>What to check next</h3><ul>{overview.next_steps.map((text,i)=><li key={i}>{text}</li>)}</ul></section><section><h3>How to use this observation</h3>{overview.possible_use.map((text,i)=><p key={i}>{text}</p>)}</section></div>
      <details><summary>Evidence limits & sources</summary>{overview.limitations.map((text,i)=><p className="muted" key={i}>{text}</p>)}{overview.references?.map(item=><a className="source-link" key={item.url} href={item.url} target="_blank" rel="noreferrer">{item.title}</a>)}</details>
      <div className="plant-overview-ai"><div><h3>Optional Gemini summary</h3><p>{ai?.configured?'Only the result text is sent to Gemini when you press this button. Photos remain local.':'Connect a server-side Gemini API key to enable AI curation. The complete overview above already works locally.'}</p><p className="muted">AI can select existing evidence and care notes; it cannot add diagnoses, treatment doses or claims that produce is safe to eat.</p>{overview.fallback_reason&&<p role="status">{overview.fallback_reason}</p>}</div><button className="btn" type="button" disabled={!!busy||!ai?.configured} onClick={summarize}>{busy==='ai'?'Curating overview…':'Create brief Gemini overview'}</button></div>
      <button className="btn" type="button" onClick={exportOverview}>Export combined overview</button>
    </section>}
  </section>;
}
