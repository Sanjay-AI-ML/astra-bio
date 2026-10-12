import React, {useEffect, useRef, useState} from 'react';

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const CROPS = ['tomato', 'bell pepper', 'potato'];
const humanize = value => String(value ?? 'unknown').replaceAll('_', ' ').replaceAll('-', ' ');
const speciesKey = value => {
  const key = humanize(value).toLowerCase().replace('bellpepper', 'bell pepper');
  return key === 'capsicum' ? 'bell pepper' : key;
};
const supportsCrop = (model, crop) => Boolean(model && (crop === 'tomato' || model.id === 'produce-detection') &&
  Array.isArray(model.species) && model.species.some(value => speciesKey(value) === crop));
const modelScore = value => typeof value === 'number' && Number.isFinite(value) ? Math.round(value * 100) + '%' : 'Unavailable';
const validBox = box => Array.isArray(box) && box.length === 4 && box.every(value => Number.isFinite(value) && value >= 0 && value <= 1) && box[2] > box[0] && box[3] > box[1];
const sourceLink = value => /^https?:\/\//i.test(value || '') ? value : null;

function downloadEvidence(evidence) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], {type: 'application/json'}));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'astra-bio-fruit-observation.json';
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function FruitMonitoring({request, exportEvidence = downloadEvidence}) {
  const [catalog, setCatalog] = useState(null), [catalogError, setCatalogError] = useState('');
  const [reload, setReload] = useState(0), [modelId, setModelId] = useState(''), [crop, setCrop] = useState('tomato');
  const [file, setFile] = useState(null), [preview, setPreview] = useState(''), [imageSize, setImageSize] = useState(null);
  const [observation, setObservation] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const revision = useRef(0);
  const currentCrop = useRef('tomato');
  const models = Array.isArray(catalog?.models) ? catalog.models : [];
  const selectedModel = models.find(model => model.id === modelId);
  const compatible = supportsCrop(selectedModel, crop);
  const hasLabels = Array.isArray(selectedModel?.labels) && selectedModel.labels.length > 0;
  const displayedLabels = hasLabels ? selectedModel.id === 'produce-detection'
    ? selectedModel.labels.filter(label => speciesKey(label) === crop) : selectedModel.labels : [];
  const canScreen = Boolean(file && selectedModel?.ready === true && compatible && hasLabels && !busy);

  function invalidate() {
    revision.current += 1;
    setObservation(null);
    setError('');
    setBusy(false);
  }

  useEffect(() => {
    let active = true;
    setCatalog(null);
    setCatalogError('');
    request('/fruit-models').then(data => {
      if (!active) return;
      setCatalog(data);
      const candidates = Array.isArray(data?.models) ? data.models : [];
      setModelId(previous => {
        if (candidates.some(model => model.id === previous && supportsCrop(model, currentCrop.current))) return previous;
        if (currentCrop.current === 'tomato' && data?.default_model_id) return data.default_model_id;
        return candidates.find(model => supportsCrop(model, currentCrop.current))?.id || '';
      });
    }).catch(error => {if (active) setCatalogError(error.message || 'Model availability could not be loaded.');});
    return () => {active = false;};
  }, [request, reload]);

  useEffect(() => {
    setImageSize(null);
    if (!file) {setPreview(''); return;}
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => {revision.current += 1;}, []);

  function chooseFile(event) {
    invalidate();
    const chosen = event.target.files?.[0] || null;
    if (chosen && chosen.size > MAX_IMAGE_BYTES) {
      setFile(null);
      setError('Photograph exceeds 10 MiB. Choose a smaller image.');
    } else if (chosen && !IMAGE_TYPES.includes(chosen.type)) {
      setFile(null);
      setError('Choose a JPG, PNG or WebP photograph.');
    } else setFile(chosen);
  }

  function chooseCrop(value) {
    invalidate();
    currentCrop.current = value;
    setCrop(value);
    if (!supportsCrop(selectedModel, value)) {
      setModelId(models.find(model => supportsCrop(model, value))?.id || '');
    }
  }

  async function screenPhotograph(event) {
    event.preventDefault();
    if (!canScreen) return;
    const currentRevision = ++revision.current;
    const input = {file_name: file.name, file_size_bytes: file.size, crop_species: crop, model_id: modelId};
    const form = new FormData();
    form.append('file', file);
    setObservation(null);
    setError('');
    setBusy(true);
    try {
      const result = await request('/fruit-image?crop_species=' + encodeURIComponent(crop) + '&model_id=' + encodeURIComponent(modelId), form);
      if (revision.current !== currentRevision) return;
      if (!['observed', 'no_detections', 'rejected', 'unavailable'].includes(result?.status)) throw new Error('The model returned an unreadable observation. Screen the photograph again.');
      setObservation({result, input, screened_at_utc: new Date().toISOString()});
    } catch (error) {
      if (revision.current === currentRevision) setError(error.message || 'The photograph could not be screened.');
    } finally {
      if (revision.current === currentRevision) setBusy(false);
    }
  }

  const result = observation?.result;
  const observed = result?.status === 'observed' || result?.status === 'no_detections';
  const detections = observed && Array.isArray(result.detections) ? result.detections : [];
  const width = imageSize?.width || result?.image_width || 1000;
  const height = imageSize?.height || result?.image_height || 1000;
  const fontSize = Math.max(14, Math.min(width, height) * .028);
  const count = Number.isInteger(result?.visible_count) && result.visible_count >= 0 ? result.visible_count : 'Unavailable';
  const stageCounts = observed && result.counts_by_stage && typeof result.counts_by_stage === 'object' ? Object.entries(result.counts_by_stage) : [];
  const catalogMessage = !catalog ? '' : !models.length ? 'No fruit models are registered.' : !selectedModel ? 'No model is available for this selection.' :
    !compatible ? 'This model does not support the selected crop.' : selectedModel.ready !== true ? selectedModel.reason || 'The selected model is not installed or its availability is unverified.' :
      !hasLabels ? 'Model labels are unavailable. Reload model availability before screening.' : '';

  return <div className="fruit-monitoring">
    <div className="fruit-introduction"><span className="eyebrow">VISIBLE PRODUCE OBSERVATIONS</span><h2>Inspect a fruit photograph</h2>
      <p>Count visible produce and review visual maturity when the selected model provides maturity labels. Images are processed locally.</p></div>
    <form onSubmit={screenPhotograph} className="fruit-form">
      <div className="fruit-selectors">
        <label className="field"><span>Fruit crop</span><select value={crop} onChange={event => chooseCrop(event.target.value)}>{CROPS.map(value => <option key={value} value={value}>{value === 'potato' ? 'potato · harvested tubers' : value}</option>)}</select></label>
        <label className="field"><span>Fruit model</span><select value={modelId} disabled={!models.length} onChange={event => {invalidate(); setModelId(event.target.value);}}>
          {!selectedModel && <option value={modelId}>{catalog ? 'No compatible model' : 'Loading models…'}</option>}
          {models.map(model => <option key={model.id} value={model.id} disabled={!supportsCrop(model, crop)}>{model.name || model.id}{model.ready === true ? '' : ' · unavailable'}</option>)}
        </select></label>
      </div>
      {!catalog && !catalogError && <p role="status" className="muted">Loading fruit model availability…</p>}
      {catalogError && <p role="alert" className="notice warning">Fruit model availability could not be loaded: {catalogError}</p>}
      {catalogMessage && <p role="status" className="notice warning">{catalogMessage}</p>}
      {(catalogError || catalogMessage) && <button className="text-button" type="button" onClick={() => {invalidate(); setReload(value => value + 1);}}>Reload fruit models</button>}
      {selectedModel && <div className="fruit-model-description">
        <p><strong>{selectedModel.capability === 'visual_maturity' || selectedModel.id?.startsWith('tomato-ripeness-') ? 'Visual maturity detection' : 'Visible produce detection'}</strong> · supported crops: {selectedModel.species?.map(humanize).join(', ') || 'Unverified'}</p>
        <p className="muted">Model labels for this crop: {displayedLabels.length ? displayedLabels.map(humanize).join(', ') : 'Unavailable'}.</p>
        {sourceLink(selectedModel.source_url) && <a className="source-link" href={selectedModel.source_url} target="_blank" rel="noreferrer">Upstream model card ↗</a>}
      </div>}
      {crop !== 'tomato' && <p className="notice">{crop === 'potato' ? 'Photograph harvested, exposed potato tubers. This model cannot see underground tubers or determine harvest readiness.' : 'Bell pepper uses the generic produce detector. It identifies visible produce without assessing ripeness.'}</p>}
      <label className="field upload-field"><span>Fruit photograph · JPG, PNG or WebP · up to 10 MiB</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseFile}/></label>
      {file && <p className="muted fruit-file-name">Selected photograph: {file.name}</p>}
      {preview && <figure className="fruit-image-figure"><div className="fruit-image-frame">
        <img src={preview} alt="Selected produce photograph for local screening" onLoad={event => {const image = event.currentTarget; setImageSize({width: image.naturalWidth, height: image.naturalHeight});}}/>
        {detections.some(detection => validBox(detection.box)) && <svg className="fruit-detection-overlay" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Detection boxes and model scores on the selected photograph">
          {detections.map((detection, index) => {
            if (!validBox(detection.box)) return null;
            const [x1, y1, x2, y2] = detection.box;
            const x = x1 * width, y = y1 * height;
            const label = `${index + 1} · ${humanize(detection.class_label)} · ${modelScore(detection.score)}`;
            const labelY = Math.max(fontSize * 1.35, y);
            const labelWidth = String(index + 1).length * fontSize * .62 + 12;
            const labelX = Math.min(x, width - labelWidth);
            return <g key={detection.id ?? index}><title>{label}</title>
              <rect data-testid="fruit-detection-box" x={x} y={y} width={(x2 - x1) * width} height={(y2 - y1) * height} fill="none" stroke="#145c3e" strokeWidth={Math.max(2, fontSize / 6)}/>
              <rect x={labelX} y={labelY - fontSize * 1.35} width={labelWidth} height={fontSize * 1.35} rx={fontSize * .12} fill="#145c3e"/>
              <text x={labelX + 5} y={labelY - fontSize * .3} fontSize={fontSize} fill="white">{index + 1}</text>
            </g>;
          })}
        </svg>}
      </div><figcaption>{detections.length ? 'Numbered boxes correspond to the observation list below. Scores are model outputs, not calibrated correctness probabilities.' : 'The selected photograph is ready for explicit local screening.'}</figcaption></figure>}
      {error && <p role="alert" className="notice warning">{error}</p>}
      <button className="btn primary" type="submit" disabled={!canScreen}>{busy ? 'Screening fruit photograph…' : 'Screen fruit image'}</button>
      {busy && <span className="fruit-screen-status muted" role="status">Running local inference. Changing an input clears this request’s result.</span>}
    </form>
    {result && <section className="fruit-result" aria-labelledby="fruit-result-title" aria-live="polite">
      <div className="section-heading"><h2 id="fruit-result-title">Fruit observation</h2><span className="pill">{humanize(result.status)}</span></div>
      <p className={'notice ' + (result.status === 'observed' ? '' : 'warning')}>{result.reason || 'No explanation was returned by the model.'}</p>
      {observed && <>
        <dl className="fruit-counts" aria-label="Visible produce counts"><div><dt>Visible produce</dt><dd>{count}</dd></div>{stageCounts.map(([stage, value]) => <div key={stage}><dt>{humanize(stage)}</dt><dd>{value}</dd></div>)}</dl>
        {result.status === 'no_detections' && <p>No produce was detected. This does not establish that the photograph or growing area contains no fruit.</p>}
        {!!detections.length && <div className="table-wrap"><table aria-label="Visible produce observations"><thead><tr><th>Box</th><th>Model label</th><th>Visual stage</th><th>Model score</th></tr></thead><tbody>{detections.map((detection, index) => <tr key={detection.id ?? index}><td>{index + 1}</td><td>{humanize(detection.class_label)}</td><td>{detection.stage ? humanize(detection.stage) : 'Not assessed'}</td><td>{modelScore(detection.score)}</td></tr>)}</tbody></table></div>}
        {detections.some(detection => !validBox(detection.box)) && <p className="notice warning">Some detection coordinates are unavailable; those observations could not be drawn on the photograph.</p>}
      </>}
      {Array.isArray(result.warnings) && result.warnings.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}
      <button className="btn" type="button" onClick={() => exportEvidence({schema_version: 1, ...observation.input, screened_at_utc: observation.screened_at_utc, ...result})}>Export fruit evidence JSON</button>
      {result.provenance && <details className="fruit-provenance"><summary>Observation provenance</summary><pre>{JSON.stringify(result.provenance, null, 2)}</pre></details>}
    </section>}
    <p className="fruit-boundaries">Visual maturity does not establish bacterial identity, disease, or food safety. Counts cover only produce visible in this photograph; occluded fruit and total yield are unmeasured. Observations do not credit food inventory or trigger automatic actions.</p>
  </div>;
}
