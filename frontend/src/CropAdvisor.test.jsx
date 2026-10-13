import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within, waitFor} from '@testing-library/react';
import CropAdvisor from './CropAdvisor.jsx';

const config = {days: 30, area_m2: 12.5, crew: 4, targets_per_crew: {protein: 80, energy: 2400, vitamin_c: 90}, crops: []};
const run = {history_id: 'run-one', metadata: {config, scenario: {event_day: 10}, adaptive: {daily: [{day: 1}, {day: 30}]}}};
const candidate = {crop_id: 'spinach', name: 'Spinach', rank: 1, actionable: true, blocked_reasons: [],
  nutrients_per_100g: {protein: 2.86, vitamin_c: 28.1, energy: 23}, nutrients_at_harvest: {protein: 85.8, vitamin_c: 843, energy: 690},
  grow_days: 20, harvest_day: 21, estimated_harvest_kg: 3,
  resources: {required_daily_water_l: 2, required_daily_power_kwh: 1, cycle_water_l: 40, cycle_power_kwh: 20},
  provenance: {composition: {status: 'usda_reference_proxy', fdc_id: 168462, food_form: 'Raw spinach', source_url: 'https://fdc.nal.usda.gov/food-details/168462/nutrients'}, growth: {detail: 'Published terrestrial cycle estimate'}, resources: {detail: 'Configured resource assumptions'}}, warnings: []};
const report = {day: 1, priority: 'balanced', area_m2: 1, recommendations: [candidate], top_choice_crop_id: 'spinach',
  scoring_basis: 'Ranked against remaining tracked nutrient shortfalls.',
  forecast: {available: true, nutrients: [{nutrient: 'protein', unit: 'g', current_supply: 300, current_target: 320, earliest_gap_day: 3, gap_days: 5}]},
  bridge_foods: [{food_id: 'lentils', name: 'Dry lentils', stock_kg: 2, available: true, expired: false, is_reserve: false, current_nutrients_per_100g: {protein: 24.63, vitamin_c: 4.5}, provenance: {food_form: 'Dry raw lentils'}}],
  limitations: ['Local growing cycles remain unvalidated.']};
const clone = value => structuredClone(value);
const renderAdvisor = props => render(<CropAdvisor config={config} run={run} missionDay={1} setMissionDay={vi.fn()} setRun={vi.fn()} request={vi.fn(async () => clone(report))} notify={vi.fn()} {...props}/>);
const ready = () => screen.findByRole('table', {name: 'Crop recommendation comparison'});
const custom = () => fireEvent.click(screen.getByRole('checkbox', {name: 'Use custom nutrient priority, area and deadline'}));
afterEach(cleanup);

describe('Crew-driven food recommendations', () => {
  it('shows immediate review separately from unqualified future microorganism output', async () => {
    const response={...clone(report),response_plan:{health_alerts:[{profile_id:'crew-4',name:'Vamshika',kind:'low_ferritin',severity:'review',sample_only:true,day:1,message:'Fictional example: request crew medical review.'}],immediate_support:[{kind:'supplement_review',title:'Supplement availability unconfirmed',message:'No available approved order is recorded.'}],production_options:[{id:'reactor',name:'Limnospira protein photobioreactor',status:'projected',first_harvest_day:5,first_harvest_protein_g:2.06,protein_g:12.36,reasons:['Food qualification is not established.']}],scope:{sample_only:true,missing_metrics:['Blood pressure']}}};
    renderAdvisor({request:async()=>response});
    expect(await screen.findByRole('heading',{name:'Crew health and food response'})).toBeTruthy();
    expect(screen.getByText('Fictional example: request crew medical review.')).toBeTruthy();
    expect(screen.getByText('Supplement availability unconfirmed')).toBeTruthy();
    expect(screen.getByRole('table',{name:'Biological production recommendations'}).textContent).toContain('Day 5');
    expect(screen.getByText('Sample crew records')).toBeTruthy();
  });
  it('automatically uses crew records and the biological scenario without asking for planning inputs or mutating the plan', async () => {
    const request = vi.fn(async () => clone(report));
    const crewState = {profiles: [{id: 'one', name: 'Vamshika'}], blood_samples: [{crew_id: 'one', ferritin_ug_l: 10}], conditions: []};
    const biologicalScenario = {enabled: true, water_l: 5};
    renderAdvisor({request, crewState, biologicalScenario, missionDay: 5});
    await ready();
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith('/crop-advisor', {metadata: run.metadata, config, day: 5, automatic: true, crew_state: crewState, biological_scenario: biologicalScenario});
    expect(screen.queryByRole('button', {name: 'Suggest crops'})).toBeNull();
    expect(screen.queryByLabelText('Nutrient priority')).toBeNull();
    expect(screen.queryByLabelText('Assumed planting area (m²)')).toBeNull();
    expect(screen.getByRole('table', {name: 'Predicted nutrient gaps'}).textContent).toContain('Day 3');
    expect(screen.getByRole('region', {name: 'Crop details for Spinach'}).textContent).toContain('85.8 g');
  });

  it('recalculates when reviewed blood records change, even when the roster and mission are unchanged', async () => {
    const request = vi.fn(async () => clone(report)), state = {profiles: [{id: 'one', name: 'Vamshika'}], blood_samples: []};
    const {rerender} = renderAdvisor({request, crewState: state});
    await ready();
    const changed = {...state, blood_samples: [{crew_id: 'one', ferritin_ug_l: 10}]};
    rerender(<CropAdvisor config={config} run={run} missionDay={1} request={request} crewState={changed}/>);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(request.mock.calls.at(-1)[1].crew_state).toEqual(changed);
  });

  it('drops stale recommendations after the simulated day changes and requests the new day', async () => {
    const pending = [], request = vi.fn(() => new Promise(resolve => pending.push(resolve)));
    const {rerender} = renderAdvisor({request});
    rerender(<CropAdvisor config={config} run={run} missionDay={6} request={request}/>);
    await act(async () => pending[0](clone(report)));
    expect(screen.queryByRole('table', {name: 'Crop recommendation comparison'})).toBeNull();
    await act(async () => pending[1]({...clone(report), day: 6}));
    await ready();
    expect(request.mock.calls.at(-1)[1].day).toBe(6);
  });

  it('refreshes saved advice with current crew records without starting a solver', async () => {
    const request = vi.fn(async () => clone(report));
    renderAdvisor({request, run: {...run, metadata: {...run.metadata, planning_advice: {...clone(report), area_m2: .25}}}});
    await ready();
    expect(request.mock.calls.map(([path]) => path)).toEqual(['/crop-advisor']);
  });

  it('keeps a custom comparison available only through the advanced option', async () => {
    const request = vi.fn(async () => clone(report));
    renderAdvisor({request, missionDay: 5});
    await ready(); custom();
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient priority'}), {target: {value: 'protein'}});
    fireEvent.change(screen.getByLabelText('Assumed planting area (m²)'), {target: {value: '2.5'}});
    fireEvent.click(screen.getByRole('button', {name: 'Compare custom inputs'}));
    await ready();
    expect(request.mock.calls.at(-1)).toEqual(['/crop-advisor', {metadata: run.metadata, config, day: 5, automatic: false, priority: 'protein', area_m2: 2.5, deadline_day: 30}]);
  });

  it('shows saved solver crop choices and a deadline limitation', async () => {
    const timed = {...clone(report), top_choice_crop_id: null, selection_reason: {type: 'no_timely_gap_help', text: 'Capacity exists but harvest misses the selected gaps.'},
      planned_crop_actions: [{crop_id: 'spinach', name: 'Spinach', day: 5, harvest_day: 25, area_m2: 1, predicted_harvest_kg: 3, nutrients_at_harvest: {protein: 85.8, vitamin_c: 843}}]};
    renderAdvisor({request: vi.fn(async () => timed), showContinuation: false});
    expect(await screen.findByRole('heading', {name: 'Crops for the remaining mission'})).toBeTruthy();
    expect(screen.getByRole('table', {name: 'Selected crops for the remaining mission'}).textContent).toContain('Day 5 → 25');
    expect(screen.getByRole('heading', {name: 'Extra batches cannot help these gaps in time'})).toBeTruthy();
    expect(screen.queryByRole('button', {name: /Continue from Day/})).toBeNull();
  });

  it('continues only on request and preserves balanced targets', async () => {
    const continued = {metadata: {adaptive: {daily: [{day: 1}]}}};
    const request = vi.fn(async path => path === '/crop-advisor' ? clone(report) : continued), setRun = vi.fn();
    renderAdvisor({request, setRun});
    await ready();
    expect(setRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    await waitFor(() => expect(setRun).toHaveBeenCalledWith(continued));
    expect(request).toHaveBeenCalledWith('/plans/continue', {metadata: run.metadata, through_day: 1, target_factors: {}});
  });

  it('keeps manual continuation target adjustments behind the advanced option', async () => {
    const continued = {history_id: 'continued', metadata: {config, adaptive: {daily: [{day: 1}, {day: 30}]}}};
    const request = vi.fn(async path => path === '/crop-advisor' ? clone(report) : continued), setRun = vi.fn();
    renderAdvisor({request, setRun, missionDay: 8});
    await ready(); custom();
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient priority'}), {target: {value: 'protein'}});
    fireEvent.change(screen.getByLabelText('Protein target change from next day (%)'), {target: {value: '20'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 8'}));
    await waitFor(() => expect(setRun).toHaveBeenCalledWith(continued));
    expect(request).toHaveBeenCalledWith('/plans/continue', {metadata: run.metadata, through_day: 8, target_factors: {protein: 1.2}});
  });

  it('cannot continue before completed history, at the horizon, or without a saved simulation', async () => {
    const request = vi.fn(async () => clone(report));
    const {rerender} = renderAdvisor({request, missionDay: 3, run: {...run, metadata: {...run.metadata, continuation: {through_day: 8, next_day: 9}}}});
    await ready();
    expect(screen.getByRole('button', {name: 'Continue from Day 3'}).disabled).toBe(true);
    expect(screen.getByText(/Choose Day 8 or later/)).toBeTruthy();
    rerender(<CropAdvisor config={config} run={run} missionDay={30} request={request}/>);
    await ready();
    expect(screen.getByRole('button', {name: 'Continue from Day 30'}).disabled).toBe(true);
    rerender(<CropAdvisor config={config} run={null} request={request}/>);
    await ready();
    expect(screen.getByRole('button', {name: 'Continue from Day 1'}).disabled).toBe(true);
    expect(screen.getByText('Current configuration · no saved simulation')).toBeTruthy();
    expect(request.mock.calls.every(([path]) => path === '/crop-advisor')).toBe(true);
  });

  it('keeps blocked candidates visible and explains their limits', async () => {
    const response = clone(report);
    response.top_choice_crop_id = null;
    response.recommendations[0].actionable = false;
    response.recommendations[0].blocked_reasons = ['Harvest falls after the remaining mission.'];
    renderAdvisor({request: async () => response});
    await screen.findByRole('heading', {name: 'No additional batch fits the modeled limits'});
    expect(within(screen.getByRole('table', {name: 'Crop recommendation comparison'})).getByText('Blocked')).toBeTruthy();
    expect(screen.getByText('Harvest falls after the remaining mission.')).toBeTruthy();
  });

  it('discards a pending continuation when a newer run arrives', async () => {
    let resolve;
    const request = vi.fn(path => path === '/crop-advisor' ? Promise.resolve(clone(report)) : new Promise(done => {resolve = done;})), setRun = vi.fn();
    const {rerender} = renderAdvisor({request, setRun});
    await ready();
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    rerender(<CropAdvisor config={config} run={{...run, history_id: 'newer'}} missionDay={1} request={request} setRun={setRun}/>);
    await act(async () => resolve({metadata: {adaptive: {daily: [{day: 1}]}}}));
    expect(setRun).not.toHaveBeenCalled();
  });

  it('retains the saved plan when continuation fails', async () => {
    const setRun = vi.fn();
    renderAdvisor({setRun, request: async path => {if (path === '/crop-advisor') return clone(report); throw new Error('No feasible future plan.');}});
    await ready();
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    expect((await screen.findByRole('alert')).textContent).toContain('No feasible future plan.');
    expect(setRun).not.toHaveBeenCalled();
  });

  it('can retry an unavailable automatic report without changing the configuration', async () => {
    const request = vi.fn().mockRejectedValueOnce(new Error('Advisor temporarily unavailable.')).mockResolvedValueOnce(clone(report));
    renderAdvisor({request});
    expect((await screen.findByRole('alert')).textContent).toContain('Advisor temporarily unavailable.');
    fireEvent.click(screen.getByRole('button', {name: 'Retry recommendations'}));
    await ready();
    expect(request.mock.calls.map(([path]) => path)).toEqual(['/crop-advisor', '/crop-advisor']);
  });

  it('labels configured composition as an assumption and does not borrow an unmatched USDA citation', async () => {
    const response = clone(report);
    response.recommendations[0].provenance.composition = {status: 'configured_assumption', source_url: null, fdc_id: null, detail: 'Current configuration coefficients.', comparison_reference: {fdc_id: 168462, source_url: 'https://fdc.nal.usda.gov/food-details/168462/nutrients'}};
    renderAdvisor({request: async () => response});
    const detail = within(await screen.findByRole('region', {name: 'Crop details for Spinach'}));
    expect(detail.getByText('Configured composition')).toBeTruthy();
    expect(detail.queryByRole('link', {name: /USDA/})).toBeNull();
  });

  it('applies crop reference data only after an explicit action and discards stale mutation responses', async () => {
    let resolve;
    const request = vi.fn(path => path === '/crop-advisor' ? Promise.resolve(clone(report)) : new Promise(done => {resolve = done;})), setConfig = vi.fn();
    const {rerender} = renderAdvisor({request, setConfig});
    await ready();
    expect(setConfig).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Use USDA crop nutrition'}));
    expect(request).toHaveBeenCalledWith('/config/crop-nutrition', {config});
    rerender(<CropAdvisor config={{...config, crew: 6}} setConfig={setConfig} run={null} request={request}/>);
    await act(async () => resolve({config, matched_crop_ids: ['spinach'], unmatched_crop_ids: []}));
    expect(setConfig).not.toHaveBeenCalled();
  });
});
