import React, {useEffect, useState} from 'react';

const SOURCE_LABELS = {hardware: 'Physical camera', synthetic: 'Synthetic test image'};
const TRANSPORT_LABELS = {wifi_https: 'Wi-Fi → HTTPS gateway', serial_bridge: 'USB serial → laptop gateway'};
const localTime = value => {
  const timestamp = Date.parse(value || '');
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : 'Not reported';
};
const contentPath = image => {
  if (typeof image?.id !== 'string' || !/^[a-f0-9]{24}$/i.test(image.id)) return null;
  const expected = '/api/camera-images/' + encodeURIComponent(image.id) + '/content';
  return image.content_url === expected ? expected : null;
};

function receiptAge(image, checkedAt) {
  const received = Date.parse(image?.received_at_utc || '');
  if (!Number.isFinite(received) || !checkedAt) return 'Receipt age unavailable';
  const seconds = (checkedAt - received) / 1000;
  if (seconds < -5) return 'Receipt timestamp is in the future; check the server clock';
  if (seconds <= 120) return 'Received recently · ' + Math.max(0, Math.round(seconds)) + ' seconds before this refresh';
  if (seconds < 3600) return 'Older stored image · ' + Math.floor(seconds / 60) + ' minutes before this refresh';
  if (seconds < 86400) return 'Older stored image · ' + Math.floor(seconds / 3600) + ' hours before this refresh';
  return 'Older stored image · ' + Math.floor(seconds / 86400) + ' days before this refresh';
}

export default function CameraImages({request}) {
  const [source, setSource] = useState('hardware');
  const [deviceDraft, setDeviceDraft] = useState(''), [device, setDevice] = useState('');
  const [refresh, setRefresh] = useState(0), [collection, setCollection] = useState(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState(''), [checkedAt, setCheckedAt] = useState(0);
  const [imageErrorId, setImageErrorId] = useState('');
  const items = (collection?.items || []).filter(image => image.source === source && (!device || image.device_id === device));
  const selected = items.find(image => image.id === selectedId) || null;
  const imageUrl = contentPath(selected);
  const photoError = Boolean(selected && imageErrorId === selected.id);

  useEffect(() => {
    let active = true;
    setCollection(null); setSelectedId(''); setError(''); setImageErrorId(''); setLoading(true);
    const path = '/camera-images?source=' + encodeURIComponent(source) + '&limit=24' +
      (device ? '&device_id=' + encodeURIComponent(device) : '');
    request(path).then(result => {
      if (!active) return;
      if (!Array.isArray(result?.items)) throw new Error('Camera image list was not returned. Refresh to try again.');
      // Keep hardware/test channels and explicitly selected devices separate even if a service returns a mixed list.
      const matching = result.items.filter(image => image?.source === source &&
        (!device || image.device_id === device) && contentPath(image)).slice(0, 24);
      setCollection({...result, items: matching});
      setSelectedId(matching[0]?.id || ''); setCheckedAt(Date.now());
    }).catch(reason => {
      if (active) setError(reason.message || 'Stored camera images could not be loaded.');
    }).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [request, source, device, refresh]);

  function applyDevice(event) {
    event.preventDefault();
    const value = deviceDraft.trim();
    if (value === device) setRefresh(value => value + 1);
    else setDevice(value);
  }

  return <section className="camera-images" aria-labelledby="camera-images-heading">
    <div className="camera-images-heading"><div><span className="eyebrow">VISUAL OBSERVATIONS</span>
      <h2 id="camera-images-heading">Camera images</h2>
      <p>Browse the original JPEGs received from a device and stored in MongoDB Atlas.</p></div>
      <button className="btn" type="button" disabled={loading} onClick={() => setRefresh(value => value + 1)}>
        {loading ? 'Loading camera images…' : 'Refresh camera images'}
      </button>
    </div>
    <form className="camera-filters" onSubmit={applyDevice}>
      <label className="field"><span>Camera source</span><select value={source} onChange={event => setSource(event.target.value)}>
        <option value="hardware">Physical hardware</option><option value="synthetic">Synthetic test / replay</option>
      </select></label>
      <label className="field"><span>Camera device ID</span><input type="text" value={deviceDraft} maxLength={80}
        placeholder="All camera devices" onChange={event => setDeviceDraft(event.target.value)}/></label>
      <button className="btn" type="submit" disabled={loading}>Apply camera filter</button>
    </form>
    <p className="camera-channel muted">{SOURCE_LABELS[source]} channel · {device ? 'Device ' + device : 'All camera devices'} · Latest 24 stored images</p>
    {source === 'synthetic' && <p className="notice warning">SYNTHETIC IMAGE — this channel contains test or replay uploads. It is not evidence of a live camera capture.</p>}
    {loading && <p role="status" className="muted">Checking stored camera images…</p>}
    {error && <p role="alert" className="notice warning">{error}</p>}
    {!loading && !error && collection?.storage?.configured === false &&
      <p className="notice warning">Camera image storage is not configured. Configure MongoDB on the backend to receive device photographs.</p>}
    {!loading && !error && !selected && <div className="camera-empty"><h3>No stored images for this selection</h3>
      <p>Send a camera JPEG through the Wi-Fi gateway, then refresh this view.</p></div>}
    {!loading && !error && selected && <>
      <div className="camera-viewer">
        <figure className="camera-photograph">
          {photoError ? <div role="alert" className="camera-photo-error"><h3>Stored photo could not be displayed</h3>
            <p>Refresh camera images to retry. The metadata below does not confirm that the image bytes were retrieved.</p></div> :
            <img key={selected.id} src={imageUrl} width={selected.width} height={selected.height}
              alt={'Stored camera photograph from ' + selected.device_id}
              onError={() => setImageErrorId(selected.id)}/>}
          <figcaption>{SOURCE_LABELS[selected.source]} · {selected.width} × {selected.height} px · Original JPEG</figcaption>
        </figure>
        <div className="camera-image-evidence">
          <span className={'status-chip ' + (selected.source === 'synthetic' ? 'demo' : '')}>{SOURCE_LABELS[selected.source]}</span>
          <h3>{selected.device_id}</h3>
          <p className="camera-receipt">{receiptAge(selected, checkedAt)}</p>
          <dl>
            <div><dt>Received by gateway</dt><dd>{localTime(selected.received_at_utc)}</dd></div>
            <div><dt>Device capture time</dt><dd>{localTime(selected.captured_at_utc)}</dd></div>
            <div><dt>Delivery transport</dt><dd>{TRANSPORT_LABELS[selected.transport] || 'Not reported'}</dd></div>
            <div><dt>Image size</dt><dd>{Number.isFinite(selected.bytes) ? selected.bytes.toLocaleString() + ' bytes' : 'Unavailable'}</dd></div>
            <div><dt>Sample ID</dt><dd>{selected.sample_id || 'Not reported'}</dd></div>
          </dl>
          <a className="text-button" href={imageUrl} target="_blank" rel="noreferrer">Open original JPEG</a>
          <details className="camera-integrity"><summary>Stored image integrity</summary>
            <dl><div><dt>SHA-256</dt><dd>{selected.sha256 || 'Unavailable'}</dd></div><div><dt>Record ID</dt><dd>{selected.id}</dd></div></dl>
          </details>
        </div>
      </div>
      {items.length > 1 && <nav className="camera-history" aria-label="Stored camera image history">
        {items.map((image, index) => <button className={image.id === selectedId ? 'active' : ''} type="button" key={image.id}
          aria-pressed={image.id === selectedId} aria-label={'View stored photo ' + (index + 1) + ' from ' + image.device_id}
          onClick={() => {setSelectedId(image.id); setImageErrorId('');}}>
          <span>{index === 0 ? 'Latest' : 'Earlier'} · {image.device_id}</span><strong>{localTime(image.received_at_utc)}</strong>
        </button>)}
      </nav>}
    </>}
    <p className="muted camera-scope">Receipt age describes the stored image; it does not establish that the camera is online.
      Images are displayed only. Leaf and fruit screening remain manual, and photographs do not change the crop plan.</p>
  </section>;
}
