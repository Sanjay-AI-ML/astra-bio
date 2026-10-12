import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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
afterEach(cleanup);

describe('Nutrient crop advisor', () => {
  it('shows saved solver crop choices and distinguishes a missed deadline from no growing capacity',async()=>{
    const timed={...clone(report),top_choice_crop_id:null,selection_reason:{type:'no_timely_gap_help',text:'Capacity exists but harvest misses the selected gaps.'},
      planned_crop_actions:[{crop_id:'spinach',name:'Spinach',day:5,harvest_day:25,area_m2:1,predicted_harvest_kg:3,nutrients_at_harvest:{protein:85.8,vitamin_c:843}}]};
    renderAdvisor({request:vi.fn(async()=>timed),showContinuation:false});
    fireEvent.click(screen.getByRole('button',{name:'Suggest crops'}));
    expect(await screen.findByRole('heading',{name:'Crops for the remaining mission'})).toBeTruthy();
    expect(screen.getByRole('table',{name:'Selected crops for the remaining mission'}).textContent).toContain('Day 5 → 25');
    expect(screen.getByRole('heading',{name:'Extra batches cannot help these gaps in time'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Continue from Day/})).toBeNull();
  });
  it('opens the returned continuation advice without starting another solver or recommendation request',async()=>{
    const request=vi.fn(),saved={...clone(report),area_m2:.25};
    renderAdvisor({request,run:{...run,metadata:{...run.metadata,planning_advice:saved}}});
    expect(await screen.findByRole('table',{name:'Crop recommendation comparison'})).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Assumed planting area (m²)').value).toBe('0.25');
  });
  it('cannot continue before a previous completed boundary',()=>{
    const request=vi.fn();
    renderAdvisor({request,missionDay:3,run:{...run,metadata:{...run.metadata,continuation:{through_day:8,next_day:9}}}});
    expect(screen.getByRole('button',{name:'Continue from Day 3'}).disabled).toBe(true);
    expect(screen.getByText(/Choose Day 8 or later/)).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });
  it('sends selected nutrient priority, area and simulated day to the advisor', async () => {
    const request = vi.fn(async () => clone(report));
    renderAdvisor({request, missionDay: 5});
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient priority'}), {target: {value: 'protein'}});
    fireEvent.change(screen.getByLabelText('Assumed planting area (m²)'), {target: {value: '2.5'}});
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    await screen.findByRole('table', {name: 'Crop recommendation comparison'});
    expect(request).toHaveBeenCalledWith('/crop-advisor', {metadata: run.metadata, config, day: 5, priority: 'protein', area_m2: 2.5});
    expect(screen.getByRole('table', {name: 'Predicted nutrient gaps'}).textContent).toContain('Day 3');
    expect(screen.getByRole('region', {name: 'Crop details for Spinach'}).textContent).toContain('85.8 g');
    expect(screen.getByRole('table', {name: 'Crop recommendation comparison'}).textContent).toContain('2.86 g');
  });

  it('continues after the selected day with a future protein target factor', async () => {
    const continued = {history_id: 'continued', metadata: {config, adaptive: {daily: [{day: 1}, {day: 30}]}}};
    const request = vi.fn(async () => continued), setRun = vi.fn(), notify = vi.fn();
    renderAdvisor({request, setRun, notify, missionDay: 8});
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient priority'}), {target: {value: 'protein'}});
    fireEvent.change(screen.getByLabelText('Protein target change from next day (%)'), {target: {value: '20'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 8'}));
    await act(async () => {});
    expect(request).toHaveBeenCalledWith('/plans/continue', {metadata: run.metadata, through_day: 8, target_factors: {protein: 1.2}});
    expect(setRun).toHaveBeenCalledWith(continued);
    expect(screen.getByLabelText('Protein target change from next day (%)').value).toBe('0');
    expect(notify).toHaveBeenCalledWith('Plan continued from Day 8. Earlier mission days are preserved.', false);
  });

  it('balanced continuation preserves nutrient targets', async () => {
    const request = vi.fn(async () => ({metadata: {adaptive: {daily: [{day: 1}]}}}));
    renderAdvisor({request});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    await act(async () => {});
    expect(request).toHaveBeenCalledWith('/plans/continue', {metadata: run.metadata, through_day: 1, target_factors: {}});
  });

  it('disables continuation at the mission horizon and before a simulation exists', () => {
    const request = vi.fn();
    const {rerender} = renderAdvisor({request, missionDay: 30});
    expect(screen.getByRole('button', {name: 'Continue from Day 30'}).disabled).toBe(true);
    expect(screen.getByText(/Mission horizon reached/)).toBeTruthy();
    rerender(<CropAdvisor config={config} run={null} request={request}/>);
    expect(screen.getByRole('button', {name: 'Continue from Day 1'}).disabled).toBe(true);
    expect(request).not.toHaveBeenCalled();
  });

  it('keeps blocked candidates visible and explains their limits', async () => {
    const response = clone(report);
    response.top_choice_crop_id = null;
    response.recommendations[0].actionable = false;
    response.recommendations[0].blocked_reasons = ['Harvest falls after the remaining mission.'];
    renderAdvisor({request: async () => response});
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    await screen.findByRole('heading', {name: 'No additional batch fits the modeled limits'});
    expect(within(screen.getByRole('table', {name: 'Crop recommendation comparison'})).getByText('Blocked')).toBeTruthy();
    expect(screen.getByText('Harvest falls after the remaining mission.')).toBeTruthy();
  });

  it('drops a pending recommendation after the mission day changes', async () => {
    let resolve;
    const request = vi.fn(() => new Promise(done => {resolve = done;}));
    const {rerender} = renderAdvisor({request});
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    rerender(<CropAdvisor config={config} run={run} missionDay={6} request={request} setMissionDay={vi.fn()} setRun={vi.fn()}/>);
    await act(async () => resolve(clone(report)));
    expect(screen.queryByRole('table', {name: 'Crop recommendation comparison'})).toBeNull();
  });

  it('drops pending continuation when a newer run arrives', async () => {
    let resolve;
    const request = vi.fn(() => new Promise(done => {resolve = done;})), setRun = vi.fn();
    const {rerender} = renderAdvisor({request, setRun});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    rerender(<CropAdvisor config={config} run={{...run, history_id: 'newer'}} missionDay={1} request={request} setRun={setRun}/>);
    await act(async () => resolve({metadata: {adaptive: {daily: [{day: 1}]}}}));
    expect(setRun).not.toHaveBeenCalled();
  });

  it('retains the saved plan when continuation fails', async () => {
    const setRun = vi.fn();
    renderAdvisor({setRun, request: async () => {throw new Error('No feasible future plan.');}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    expect((await screen.findByRole('alert')).textContent).toBe('No feasible future plan.');
    expect(setRun).not.toHaveBeenCalled();
  });

  it('labels user composition as an assumption and does not borrow an unmatched USDA citation', async () => {
    const response = clone(report);
    response.recommendations[0].provenance.composition = {status: 'configured_assumption', source_url: null, fdc_id: null, detail: 'Current configuration coefficients.', comparison_reference: {fdc_id: 168462, source_url: 'https://fdc.nal.usda.gov/food-details/168462/nutrients'}};
    renderAdvisor({request: async () => response});
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    const detail = within(await screen.findByRole('region', {name: 'Crop details for Spinach'}));
    expect(detail.getByText('Configured composition')).toBeTruthy();
    expect(detail.queryByRole('link', {name: /USDA/})).toBeNull();
  });

  it('invalidates a result when the assumed planting area changes', async () => {
    renderAdvisor();
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    await screen.findByRole('table', {name: 'Crop recommendation comparison'});
    fireEvent.change(screen.getByLabelText('Assumed planting area (m²)'), {target: {value: '3'}});
    expect(screen.queryByRole('table', {name: 'Crop recommendation comparison'})).toBeNull();
  });

  it('rejects an invalid continuation target change before sending a request', async () => {
    const request = vi.fn();
    renderAdvisor({request});
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient priority'}), {target: {value: 'protein'}});
    fireEvent.change(screen.getByLabelText('Protein target change from next day (%)'), {target: {value: '1000'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue from Day 1'}));
    expect(screen.getByRole('alert').textContent).toContain('Enter a target change');
    expect(request).not.toHaveBeenCalled();
  });

  it('loads matched USDA crop composition with config only and resets the comparison', async () => {
    const nextConfig = {...config, crops: [{id: 'spinach', nutrients_per_kg: {protein: 28.6}}]};
    const request = vi.fn(async path => path === '/crop-advisor' ? clone(report) : {config: nextConfig, matched_crop_ids: ['spinach'], unmatched_crop_ids: ['soy']});
    const setConfig = vi.fn(), notify = vi.fn();
    renderAdvisor({request, setConfig, notify});
    fireEvent.click(screen.getByRole('button', {name: 'Suggest crops'}));
    await screen.findByRole('table', {name: 'Crop recommendation comparison'});
    fireEvent.click(screen.getByRole('button', {name: 'Use USDA crop nutrition'}));
    await act(async () => {});
    expect(request).toHaveBeenCalledWith('/config/crop-nutrition', {config});
    expect(setConfig).toHaveBeenCalledWith(nextConfig);
    expect(screen.queryByRole('table', {name: 'Crop recommendation comparison'})).toBeNull();
    expect(notify.mock.calls.at(-1)[0]).toContain('1 crop profiles. 1 unmatched profiles');
  });

  it('does not overwrite newer inputs with a pending USDA crop response', async () => {
    let resolve;
    const request = vi.fn(() => new Promise(done => {resolve = done;})), setConfig = vi.fn();
    const {rerender} = renderAdvisor({request, setConfig});
    fireEvent.click(screen.getByRole('button', {name: 'Use USDA crop nutrition'}));
    rerender(<CropAdvisor config={{...config, crew: 6}} setConfig={setConfig} run={null} request={request}/>);
    await act(async () => resolve({config, matched_crop_ids: ['spinach'], unmatched_crop_ids: []}));
    expect(setConfig).not.toHaveBeenCalled();
  });
});
