import React, {useEffect, useMemo, useState} from 'react';
import './crew-health.css';

const nutritionMetrics = {
  protein: {label: 'Protein', unit: 'g'},
  energy: {label: 'Energy', unit: 'kcal'},
  vitamin_c: {label: 'Vitamin C', unit: 'mg'},
};
const bloodMetrics = {
  hemoglobin_g_dl: {label: 'Hemoglobin', unit: 'g/dL'},
  ferritin_ug_l: {label: 'Ferritin', unit: 'µg/L'},
};
const colours = ['#24704f', '#3467a4', '#765997', '#aa6532', '#437984', '#706438'];
const finite = value => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value);
const format = value => finite(value) == null ? 'Unknown' : Number(value).toLocaleString(undefined, {maximumFractionDigits: 1});
const flatRows = value => Array.isArray(value) ? value : value?.rows || [];
const cutoff = (metric, profile) => {
  const age = finite(profile.age);
  if (age == null) return null;
  if (metric === 'ferritin_ug_l') return age >= 20 ? 15 : null;
  if (age < 15 || age > 65) return null;
  return profile.sex === 'male' ? 13 : profile.sex === 'female' ? 12 : null;
};

function niceMaximum(values, preferred = 0) {
  const highest = Math.max(preferred, ...values.filter(value => finite(value) != null), 1) * 1.12;
  const magnitude = 10 ** Math.floor(Math.log10(highest));
  const step = magnitude / 2;
  return Math.ceil(highest / step) * step;
}

function Axis({maximum, unit}) {
  return <div className="crew-health-axis" aria-hidden="true">
    {[0, 1, 2, 3, 4].map(tick => <span key={tick} style={{left: `${tick * 25}%`}}>{format(maximum * tick / 4)}</span>)}
    <small>{unit}</small>
  </div>;
}

function NumericTable({label, headers, rows}) {
  return <details className="crew-health-data">
    <summary>View exact values · {label}</summary>
    <div className="table-wrap"><table aria-label={label}>
      <thead><tr>{headers.map(header => <th key={header}>{header}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
    </table></div>
  </details>;
}

function BloodTrend({profiles, samples, metric}) {
  const [selected, setSelected] = useState(profiles[0]?.profile_id || '');
  useEffect(() => {
    if (!profiles.some(profile => profile.profile_id === selected)) setSelected(profiles[0]?.profile_id || '');
  }, [profiles, selected]);
  const profile = profiles.find(row => row.profile_id === selected);
  const readings = samples.filter(row => row.profile_id === selected).sort((a, b) => a.day - b.day);
  const knownReadings = readings.filter(row => finite(row[metric]) != null);
  const measurement = bloodMetrics[metric];
  const reference = profile ? cutoff(metric, profile) : null;
  const maximum = niceMaximum([...knownReadings.map(row => row[metric]), reference], metric === 'hemoglobin_g_dl' ? 16 : 40);
  const finalDay = Math.max(...readings.map(row => row.day), 30);
  const left = 60, right = 725, top = 35, bottom = 205;
  const x = day => left + (day - 1) / Math.max(1, finalDay - 1) * (right - left);
  const y = value => bottom - value / maximum * (bottom - top);
  const colour = colours[Math.max(0, profiles.findIndex(row => row.profile_id === selected)) % colours.length];
  const summary = knownReadings.map(row => `Day ${row.day}: ${format(row[metric])} ${measurement.unit}`).join('; ');
  return <div className="crew-health-trend">
    <div className="crew-health-subheading">
      <div><h3>Blood sample history</h3><p>Scheduled fictional test points. No daily measurements or interpolation.</p></div>
      <label className="field"><span>Crew member for blood history</span><select value={selected} onChange={event => setSelected(event.target.value)}>
        {profiles.map(row => <option value={row.profile_id} key={row.profile_id}>{row.name}</option>)}
      </select></label>
    </div>
    {knownReadings.length ? <>
      <svg className="crew-health-trend-svg" viewBox="0 0 770 260" role="img" aria-label={`${profile?.name} fictional ${measurement.label.toLowerCase()} history. ${summary}. Points are sample test results, not continuous measurements.`}>
        {[0, 1, 2, 3, 4].map(tick => <g key={tick}>
          <line className="crew-health-svg-grid" x1={left} x2={right} y1={y(maximum * tick / 4)} y2={y(maximum * tick / 4)}/>
          <text className="crew-health-svg-axis" x={left - 12} y={y(maximum * tick / 4) + 5} textAnchor="end">{format(maximum * tick / 4)}</text>
        </g>)}
        <text className="crew-health-svg-unit" x={left} y={18}>{measurement.unit}</text>
        {reference != null && <line className="crew-health-svg-reference" x1={left} x2={right} y1={y(reference)} y2={y(reference)}/>}
        {knownReadings.map(row => <g key={row.day}>
          <line className="crew-health-svg-stem" x1={x(row.day)} x2={x(row.day)} y1={y(row[metric]) + 8} y2={bottom}/>
          <circle cx={x(row.day)} cy={y(row[metric])} r={6} fill={colour}/>
          <text className="crew-health-svg-value" x={x(row.day)} y={y(row[metric]) - 14} textAnchor="middle">{format(row[metric])}</text>
          <text className="crew-health-svg-axis" x={x(row.day)} y={bottom + 29} textAnchor="middle">Day {row.day}</text>
        </g>)}
      </svg>
      <NumericTable label={`${profile?.name} fictional blood sample history`} headers={['Sample day', `${measurement.label} (${measurement.unit})`]} rows={readings.map(row => [`Day ${row.day}`, `${format(row[metric])}${finite(row[metric]) == null ? '' : ` ${measurement.unit}`}`])}/>
    </> : <p className="crew-health-empty">No fictional blood samples available for {profile?.name || 'this crew member'}.</p>}
  </div>;
}

/** Graphs display food-log estimates separately from explicitly fictional blood samples. */
export default function CrewHealthGraphs({sample, profiles: editedProfiles, assessments, day = 1, onDayChange}) {
  const [nutrient, setNutrient] = useState('protein');
  const [bloodMetric, setBloodMetric] = useState('hemoglobin_g_dl');
  const profiles = editedProfiles || sample?.profiles || [];
  const sampleRows = flatRows(sample?.assessments);
  const suppliedRows = flatRows(assessments);
  const samples = sample?.sample_only === true ? sample.blood_samples || [] : [];
  const selectedDay = finite(day) == null ? 1 : Number(day);
  const nutrition = nutritionMetrics[nutrient];
  const blood = bloodMetrics[bloodMetric];
  const availableDays = Array.from(new Set(sampleRows.map(row => Number(row.day)).filter(Number.isFinite))).sort((a, b) => a - b);
  if (!availableDays.includes(selectedDay)) availableDays.push(selectedDay);

  const intakeRows = profiles.map(profile => {
    const matches = row => row.profile_id === profile.profile_id && Number(row.day) === selectedDay && row.nutrient === nutrient;
    // An explicit empty assessment means edited logs are pending review.
    // Never resurrect old fixture values when a caller invalidates a result.
    const assessment = assessments !== undefined ? suppliedRows.find(matches) : sampleRows.find(matches);
    const intake = finite(assessment?.intake);
    const target = finite(profile.targets?.[nutrient]);
    return {...profile, intake, target, coverage: intake != null && target > 0 ? intake / target * 100 : null, complete: assessment?.log_complete === true};
  });
  const nutritionMaximum = niceMaximum(intakeRows.flatMap(row => [row.intake, row.target]));
  const latestBlood = useMemo(() => profiles.map(profile => {
    const readings = samples.filter(row => row.profile_id === profile.profile_id).sort((a, b) => b.day - a.day);
    const latest = readings[0];
    return {...profile, value: finite(latest?.[bloodMetric]), sampleDay: latest?.day, reference: cutoff(bloodMetric, profile)};
  }), [profiles, samples, bloodMetric]);
  const bloodMaximum = niceMaximum(latestBlood.flatMap(row => [row.value, row.reference]), bloodMetric === 'hemoglobin_g_dl' ? 16 : 40);
  const intakeSummary = intakeRows.map(row => `${row.name}: ${format(row.intake)} ${nutrition.unit} logged; target ${format(row.target)} ${nutrition.unit}; ${format(row.coverage)}${row.coverage == null ? '' : '%'} coverage`).join('; ');
  const bloodSummary = latestBlood.map(row => `${row.name}: ${format(row.value)}${row.value == null ? '' : ` ${blood.unit}, sample Day ${row.sampleDay}`}; example cutoff ${format(row.reference)}${row.reference == null ? '' : ` ${blood.unit}`}`).join('; ');

  if (!sample) return null;
  return <section className="crew-health" aria-labelledby="crew-health-heading">
    <div className="crew-health-heading"><div><span className="eyebrow">INDIVIDUAL CREW · SAMPLE HEALTH DATA</span><h2 id="crew-health-heading">Crew nutrition, clearly compared</h2><p>{profiles.length} crew profiles. Compare recorded food intake and separate blood test examples.</p></div><span className="crew-health-demo">Fictional sample</span></div>
    <div className="crew-health-notice"><strong>Demo data, not these people’s health records.</strong> Names are labels; all blood results and health scenarios are invented. Food logs estimate nutrient intake from reference composition. They do not measure nutrients in the blood.</div>

    <div className="crew-health-chart-section">
      <div className="crew-health-subheading"><div><span className="eyebrow">FOOD LOGS · DAY {selectedDay}</span><h3>Daily intake versus each person’s target</h3></div>
        <div className="crew-health-controls"><label className="field"><span>Nutrient to compare</span><select value={nutrient} onChange={event => setNutrient(event.target.value)}>{Object.entries(nutritionMetrics).map(([key, metric]) => <option value={key} key={key}>{metric.label} ({metric.unit})</option>)}</select></label>
          <label className="field"><span>Sample food-log day</span><select value={selectedDay} onChange={event => onDayChange?.(Number(event.target.value))} disabled={!onDayChange}>{availableDays.sort((a, b) => a - b).map(value => <option value={value} key={value}>Day {value}</option>)}</select></label>
        </div>
      </div>
      <div className="crew-health-legend"><span><i className="crew-health-bar-key"/>Logged {nutrition.label.toLowerCase()} intake</span><span><i className="crew-health-marker-key"/>Individual daily target</span></div>
      <div className="crew-health-bar-chart" role="img" aria-label={`Day ${selectedDay} ${nutrition.label.toLowerCase()} intake in ${nutrition.unit}. ${intakeSummary}. All comparison bars start at zero.`}>
        <div className="crew-health-axis-row"><span/><Axis maximum={nutritionMaximum} unit={nutrition.unit}/><span/></div>
        {intakeRows.map((row, index) => <div className="crew-health-row" key={row.profile_id}>
          <div className="crew-health-person"><i style={{background: colours[index % colours.length]}}/><span>{row.name}</span></div>
          <div className="crew-health-track">
            {[0, 25, 50, 75, 100].map(tick => <i className="crew-health-grid-line" key={tick} style={{left: `${tick}%`}}/>)}
            {row.intake != null ? <span className="crew-health-intake-bar" style={{width: `${Math.max(0, row.intake) / nutritionMaximum * 100}%`, background: colours[index % colours.length]}}/> : <span className="crew-health-track-unknown">No recorded intake</span>}
            {row.target != null && <span className="crew-health-target-marker" style={{left: `${Math.max(0, row.target) / nutritionMaximum * 100}%`}}/>}
          </div>
          <div className="crew-health-value"><strong>{format(row.intake)}{row.intake == null ? '' : ` ${nutrition.unit}`}</strong><small>Target {format(row.target)} {nutrition.unit} · {row.coverage == null ? 'Coverage unknown' : `${format(row.coverage)}%`}</small><small>{row.intake == null ? 'No log available' : row.complete ? 'Complete sample log' : 'Partial log'}</small></div>
        </div>)}
      </div>
      <p className="crew-health-caption">Bars share a zero-based {nutrition.unit} axis. Target markers follow each profile’s editable targets; values above 100% remain visible. A missing log is unknown, not zero intake.</p>
      <NumericTable label={`Day ${selectedDay} ${nutrition.label.toLowerCase()} comparison`} headers={['Crew member', `Logged intake (${nutrition.unit})`, `Target (${nutrition.unit})`, 'Coverage', 'Log status']} rows={intakeRows.map(row => [row.name, format(row.intake), format(row.target), row.coverage == null ? 'Unknown' : `${format(row.coverage)}%`, row.intake == null ? 'No log available' : row.complete ? 'Complete' : 'Partial log'])}/>
    </div>

    <div className="crew-health-chart-section">
      <div className="crew-health-subheading"><div><span className="eyebrow">FICTIONAL LAB SAMPLES · LATEST TEST PER PERSON</span><h3>Blood results, with explicit units</h3><p>Blood sample days are independent of the food-log day.</p></div>
        <label className="field"><span>Blood metric to compare</span><select value={bloodMetric} onChange={event => setBloodMetric(event.target.value)}>{Object.entries(bloodMetrics).map(([key, metric]) => <option value={key} key={key}>{metric.label} ({metric.unit})</option>)}</select></label>
      </div>
      <div className="crew-health-legend"><span><i className="crew-health-dot-key"/>Fictional blood result</span><span><i className="crew-health-marker-key"/>Example lower cutoff</span></div>
      <div className="crew-health-bar-chart" role="img" aria-label={`Fictional ${blood.label.toLowerCase()} results in ${blood.unit}. ${bloodSummary}. The markers are example lower cutoffs, not a normal range or treatment target.`}>
        <div className="crew-health-axis-row"><span/><Axis maximum={bloodMaximum} unit={blood.unit}/><span/></div>
        {latestBlood.map((row, index) => <div className="crew-health-row crew-health-blood-row" key={row.profile_id}>
          <div className="crew-health-person"><i style={{background: colours[index % colours.length]}}/><span>{row.name}{/iron/i.test(String(sample.conditions?.[row.profile_id] || '')) && <small className="crew-health-scenario">Fictional low-iron scenario</small>}</span></div>
          <div className="crew-health-track">
            {[0, 25, 50, 75, 100].map(tick => <i className="crew-health-grid-line" key={tick} style={{left: `${tick}%`}}/>)}
            {row.value != null ? <><span className="crew-health-blood-stem" style={{width: `${Math.max(0, row.value) / bloodMaximum * 100}%`}}/><span className="crew-health-blood-point" style={{left: `${Math.max(0, row.value) / bloodMaximum * 100}%`, background: colours[index % colours.length]}}/></> : <span className="crew-health-track-unknown">No blood sample</span>}
            {row.reference != null && <span className="crew-health-target-marker" style={{left: `${row.reference / bloodMaximum * 100}%`}}/>}
          </div>
          <div className="crew-health-value"><strong>{format(row.value)}{row.value == null ? '' : ` ${blood.unit}`}</strong><small>{row.value == null ? 'No sample available' : `Sample Day ${row.sampleDay}`}</small><small className={row.value != null && row.reference != null && row.value < row.reference ? 'crew-health-low' : ''}>{row.value == null ? 'Status unknown' : row.reference == null ? 'Cutoff unknown' : row.value < row.reference ? 'Below example cutoff' : 'At / above example cutoff'}</small></div>
        </div>)}
      </div>
      <p className="crew-health-caption">{bloodMetric === 'hemoglobin_g_dl' ? <>WHO example lower hemoglobin cutoffs: 12 g/dL for nonpregnant women and 13 g/dL for men, ages 15–65. Unknown age, out-of-scope age or unspecified sex means no assigned cutoff. These are anemia classification cutoffs, not a normal range or a clinical diagnosis; pregnancy, altitude and other clinical factors change interpretation. <a href="https://www.ncbi.nlm.nih.gov/books/NBK602185/table/ch5.tab2/" target="_blank" rel="noreferrer">WHO 2024 reference</a>.</> : <>WHO uses ferritin below 15 µg/L as a low iron-store cutoff in apparently healthy adults, age 20 and above. Unknown or younger ages have no assigned cutoff here. Inflammation can raise ferritin and changes its interpretation. This sample assumes no inflammation and is a comparison, not a clinical diagnosis. <a href="https://www.who.int/publications/i/item/9789240000124" target="_blank" rel="noreferrer">WHO 2020 reference</a>.</>}</p>
      <NumericTable label={`Fictional ${blood.label.toLowerCase()} results`} headers={['Crew member', 'Sample day', `${blood.label} (${blood.unit})`, `Example cutoff (${blood.unit})`, 'Sample interpretation']} rows={latestBlood.map(row => [row.name, row.sampleDay == null ? 'Unknown' : `Day ${row.sampleDay}`, format(row.value), format(row.reference), row.value == null ? 'Unknown' : row.reference == null ? 'Cutoff unknown' : row.value < row.reference ? 'Below example cutoff' : 'At / above example cutoff'])}/>
      <BloodTrend profiles={profiles} samples={samples} metric={bloodMetric}/>
    </div>
  </section>;
}
