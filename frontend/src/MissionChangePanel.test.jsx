import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import MissionChangePanel, {missionChangeProfiles} from './MissionChangePanel.jsx';

const config = {days: 90, crew: 4, area_m2: 12.5, water_budget_l_per_day: 50,
  power_budget_kwh_per_day: 8, targets_per_crew: {energy: 2200, protein: 90, vitamin_c: 100},
  foods: [{id: 'oats', name: 'Dry oats', initial_kg: 50}, {id: 'lentils', name: 'Dry lentils', initial_kg: 40}]};
const sampleProfiles = [
  {profile_id: 'crew-1', name: 'Shree Ram Vishal', age: 22, sex: 'male', targets: {energy: 2400, protein: 100, vitamin_c: 100}},
  {profile_id: 'crew-2', name: 'Shamyuktha', age: 21, sex: 'female', targets: {energy: 2000, protein: 75, vitamin_c: 90}},
  {profile_id: 'crew-3', name: 'Sanjay', age: 22, sex: 'male', targets: {energy: 2300, protein: 90, vitamin_c: 100}},
  {profile_id: 'crew-4', name: 'Vamshika', age: 22, sex: 'female', ferritin_ug_l: 8, targets: {energy: 2100, protein: 85, vitamin_c: 100}},
];
const daily = day => ({day, crew: 4, energy_target: 8800, protein_target: 360, vitamin_c_target: 400,
  water_available_l: 30, power_available_kwh: 7, shortfall_normalized: 0});
const run = {history_id: 'saved-mission', metadata: {config, scenario: {event_day: 30}, adaptive: {
  daily: [daily(29), daily(30), daily(31), daily(90)], inventories: {30: {oats: 12, lentils: 4}},
  planting: [{day: 1, harvest_day: 38, crop: 'Lettuce'}, {day: 1, harvest_day: 23, crop: 'Radish'}],
}}};
const response = () => ({history_id: 'continued-mission', metadata: {config, continuation: {
  through_day: 30, next_day: 31, mission_change: {crew: 5}, opening_stocks_kg: {oats: 12, lentils: 4}},
  adaptive: {daily: [daily(30), {...daily(31), crew: 5}, {...daily(41), crew: 5, shortfall_normalized: .12}],
    planting: [{day: 31, harvest_day: 60, crop: 'Arugula'}]}}});
const setup = props => render(<MissionChangePanel run={run} config={config} sampleProfiles={sampleProfiles}
  missionDay={30} setMissionDay={vi.fn()} setRun={vi.fn()} request={vi.fn(async () => response())} notify={vi.fn()} {...props}/>);
const submit = () => fireEvent.click(screen.getByRole('button', {name: 'Apply change & replan from Day 31'}));
const review = () => fireEvent.click(screen.getByLabelText('Reviewed planning targets for this change'));
afterEach(cleanup);

describe('Mid-mission crew and resource changes', () => {
  it('shows saved remaining state and sums the individual draft targets without running a solver', () => {
    const request = vi.fn(); setup({request});
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByText('16 kg')).toBeTruthy();
    expect(screen.getByText('60 remaining days · Days 1–30 stay unchanged')).toBeTruthy();
    const state = within(screen.getByLabelText('Saved state at end of Day 30'));
    expect(state.getByText('1')).toBeTruthy();
    expect(state.getAllByText('Not configured')).toHaveLength(2);
    const plots = within(screen.getByLabelText('Future crew nutrient target comparison'));
    expect(plots.getAllByText('360')).toHaveLength(2);
    expect(plots.getAllByText('400')).toHaveLength(2);
    expect(plots.getByText('g/day')).toBeTruthy();
    expect(plots.getByText('mg/day')).toBeTruthy();
    expect(screen.getByLabelText('Protein target for Vamshika').value).toBe('90');
  });

  it('adds a fifth crew member, carries the saved run and submits reviewed future-only targets', async () => {
    const request = vi.fn(async () => response()), setRun = vi.fn(), notify = vi.fn(), setMissionDay = vi.fn();
    const original = structuredClone(run); setup({request, setRun, notify, setMissionDay});
    fireEvent.click(screen.getByRole('button', {name: 'Add crew member'}));
    const addedProtein = screen.getAllByLabelText(/^Protein target for /).at(-1);
    const addedName = addedProtein.getAttribute('aria-label').replace('Protein target for ', '');
    fireEvent.change(addedProtein, {target: {value: '110'}});
    expect(request).not.toHaveBeenCalled();
    review(); submit();
    await screen.findByRole('region', {name: 'Accepted mission change'});
    expect(request).toHaveBeenCalledTimes(1);
    const [path, payload] = request.mock.calls[0];
    expect(path).toBe('/plans/continue');
    expect(payload.run_id).toBe('saved-mission');
    expect(payload.through_day).toBe(30);
    expect(payload.metadata).toBeUndefined();
    expect(payload.mission_change.crew_profiles).toHaveLength(5);
    expect(payload.mission_change.crew_profiles[4]).toMatchObject({name: addedName, targets: {energy: 2200, protein: 110, vitamin_c: 100}, targets_reviewed: true});
    expect(payload.mission_change.crew_profiles.every(profile => profile.targets_reviewed)).toBe(true);
    expect(payload.mission_change.crew_profiles[3].ferritin_ug_l).toBeUndefined();
    expect(payload.mission_change.initial_water_l).toBeUndefined();
    expect(payload.mission_change.replace_future_crew_changes).toBe(true);
    expect(payload.mission_change.foods).toBeUndefined();
    expect(setRun).toHaveBeenCalledWith(response());
    expect(setMissionDay).toHaveBeenCalledWith(31);
    expect(notify.mock.calls[0][0]).toContain('Updated 5 crew from Day 31');
    expect(run).toEqual(original);
    expect(screen.getByText('Day 41')).toBeTruthy();
    expect(screen.getByText('Day 60 · Arugula')).toBeTruthy();
  });

  it('uses full continuation metadata when no history identifier was saved', async () => {
    const request = vi.fn(async () => response()); setup({request, run: {...run, history_id: null}});
    review(); submit(); await screen.findByRole('region', {name: 'Accepted mission change'});
    expect(request.mock.calls[0][1].metadata).toEqual(run.metadata);
    expect(request.mock.calls[0][1].run_id).toBeNull();
  });

  it('requires target review again after editing and catches an empty target before sending', async () => {
    const request = vi.fn(); setup({request});
    review();
    fireEvent.change(screen.getByLabelText('Protein target for Sanjay'), {target: {value: ''}});
    expect(screen.getByLabelText('Reviewed planning targets for this change').checked).toBe(false);
    submit();
    expect(screen.getByRole('alert').textContent).toContain('Review the future crew targets');
    review();
    fireEvent.submit(screen.getByRole('button', {name: 'Apply change & replan from Day 31'}).closest('form'));
    expect(screen.getByRole('alert').textContent).toContain('positive energy, protein and vitamin C');
    expect(request).not.toHaveBeenCalled();
  });

  it('submits only explicitly selected daily allowances, never replenishing the reservoir', async () => {
    const request = vi.fn(async () => response()); setup({request});
    expect(screen.getByLabelText('Daily water allowance (L/day)').value).toBe('30');
    expect(screen.getByLabelText('Daily electricity allowance (kWh/day)').value).toBe('7');
    fireEvent.click(screen.getByLabelText('Change daily water allowance'));
    fireEvent.change(screen.getByLabelText('Daily water allowance (L/day)'), {target: {value: '20'}});
    fireEvent.change(screen.getByLabelText('Reason for the change (optional)'), {target: {value: ' Crew arrival and water rationing '}});
    review(); submit(); await screen.findByRole('region', {name: 'Accepted mission change'});
    expect(request.mock.calls[0][1].mission_change).toMatchObject({water_budget_l_per_day: 20, reason: 'Crew arrival and water rationing'});
    expect(request.mock.calls[0][1].mission_change.power_budget_kwh_per_day).toBeUndefined();
    expect(request.mock.calls[0][1].mission_change.area_m2).toBeUndefined();
    expect(request.mock.calls[0][1].mission_change.initial_water_l).toBeUndefined();
  });

  it('uses the selected day’s actual crew count and gives added profiles unique stable identifiers', () => {
    const moreCrew = {...run, metadata: {...run.metadata, adaptive: {...run.metadata.adaptive, daily: [{...daily(30), crew: 7}, {...daily(31), crew: 7}]}}};
    setup({run: moreCrew});
    const initialAddedName = screen.getAllByLabelText(/^Protein target for /).at(-1).getAttribute('aria-label').replace('Protein target for ', '');
    expect(screen.getByLabelText(`Protein target for ${initialAddedName}`)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: `Remove ${initialAddedName} from future crew`}));
    fireEvent.click(screen.getByRole('button', {name: 'Add crew member'}));
    const nameFields = screen.getAllByRole('textbox').filter(field => field.getAttribute('aria-label')?.startsWith('Name for'));
    expect(new Set(nameFields.map(field => field.getAttribute('aria-label'))).size).toBe(nameFields.length);
    expect(screen.getAllByLabelText(/^Protein target for /)).toHaveLength(7);
  });

  it('does not replace a newer mission with a late continuation result', async () => {
    let finish; const request = vi.fn(() => new Promise(resolve => {finish = resolve;})), setRun = vi.fn();
    const view = setup({request, setRun}); review(); submit();
    view.rerender(<MissionChangePanel run={{...run, history_id: 'newer-mission'}} config={config} sampleProfiles={sampleProfiles}
      missionDay={30} request={request} setRun={setRun}/>);
    await act(async () => {finish(response());});
    expect(setRun).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', {name: 'Accepted mission change'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Apply change & replan from Day 31'}).disabled).toBe(false);
  });

  it('does not apply a result to a different selected mission day', async () => {
    let finish; const request = vi.fn(() => new Promise(resolve => {finish = resolve;})), setRun = vi.fn();
    const view = setup({request, setRun}); review(); submit();
    view.rerender(<MissionChangePanel run={run} config={config} sampleProfiles={sampleProfiles}
      missionDay={29} request={request} setRun={setRun}/>);
    await act(async () => {finish(response());});
    expect(setRun).not.toHaveBeenCalled();
  });

  it('disables continuation before an accepted boundary, at the final day and while another solver is running', () => {
    const request = vi.fn();
    const view = setup({request, run: {...run, metadata: {...run.metadata, continuation: {through_day: 40, next_day: 41}}}});
    expect(screen.getByRole('button', {name: 'Apply change & replan from Day 31'}).disabled).toBe(true);
    expect(screen.getByText(/Choose Day 40 or later/)).toBeTruthy();
    view.rerender(<MissionChangePanel run={run} config={config} missionDay={90} request={request} setRun={vi.fn()}/>);
    expect(screen.getByRole('button', {name: 'Apply change & replan from Day 91'}).disabled).toBe(true);
    view.rerender(<MissionChangePanel run={run} config={config} missionDay={30} request={request} setRun={vi.fn()} planningBusy/>);
    expect(screen.getByRole('button', {name: 'Apply change & replan from Day 31'}).disabled).toBe(true);
    expect(request).not.toHaveBeenCalled();
  });

  it('shows real finite closing ledgers including zero and never substitutes initial food', () => {
    const finiteRun = {...run, metadata: {...run.metadata, config: {...config, initial_water_l: 600, initial_energy_kwh: 180},
      adaptive: {...run.metadata.adaptive, daily: [{...daily(30), water_remaining_l: 0, energy_remaining_kwh: 23}], inventories: {}}}};
    setup({run: finiteRun});
    const state = within(screen.getByLabelText('Saved state at end of Day 30'));
    expect(state.getByText('0 L')).toBeTruthy();
    expect(state.getByText('23 kWh')).toBeTruthy();
    expect(state.getByText('Unknown')).toBeTruthy();
    expect(state.queryByText('90 kg')).toBeNull();
  });

  it('retains saved state when the server rejects the future plan', async () => {
    const setRun = vi.fn(); setup({setRun, request: async () => {throw new Error('Finite water cannot support the revised crew.');}});
    review(); submit();
    expect((await screen.findByRole('alert')).textContent).toContain('Finite water cannot support');
    expect(setRun).not.toHaveBeenCalled();
    expect(screen.getByText('16 kg')).toBeTruthy();
  });

  it('uses chronology to seed the accepted roster rather than an upcoming saved change', () => {
    const first = [{...sampleProfiles[0], name: 'Earlier crew A'}, {...sampleProfiles[1], name: 'Earlier crew B'}];
    const later = [...first, {...sampleProfiles[2], name: 'Arriving crew C'}];
    const saved = {metadata: {config: {...config, planning_events: [{day: 15, crew: 2, crew_profiles: first}, {day: 35, crew: 3, crew_profiles: later}]},
      continuation: {next_day: 35, crew_profiles: later}, crew_profiles: later,
      adaptive: {daily: [{day: 30, crew: 2}, {day: 40, crew: 3}]}}};
    expect(missionChangeProfiles(saved, saved.metadata.config, sampleProfiles, 30).map(profile => profile.name)).toEqual(['Earlier crew A', 'Earlier crew B']);
    expect(missionChangeProfiles(saved, saved.metadata.config, sampleProfiles, 40).map(profile => profile.name)).toEqual(['Earlier crew A', 'Earlier crew B', 'Arriving crew C']);
  });

  it('shows scheduled future arrivals and replaces them unless the operator explicitly keeps them', async () => {
    const request = vi.fn(async () => response());
    setup({request, run: {...run, metadata: {...run.metadata, config: {...config,
      planning_events: [{day: 45, crew: 6}]}, scenario: {event_day: 50, extra_crew: 2}}}});
    expect(screen.getByText('Day 45: 6 crew')).toBeTruthy();
    expect(screen.getByText('Day 50: +2 crew')).toBeTruthy();
    expect(screen.getByLabelText('Replace scheduled future crew changes').checked).toBe(true);
    fireEvent.click(screen.getByLabelText('Replace scheduled future crew changes'));
    review(); submit(); await screen.findByRole('region', {name: 'Accepted mission change'});
    expect(request.mock.calls[0][1].mission_change.replace_future_crew_changes).toBe(false);
  });

  it('retains the saved current planning demand rather than unrelated sample nutrient targets', () => {
    const current = {...run, metadata: {...run.metadata, adaptive: {...run.metadata.adaptive,
      daily: [{...daily(30), protein_target: 504, vitamin_c_target: 440}]}}};
    const profiles = missionChangeProfiles(current, config, sampleProfiles, 30);
    expect(profiles.map(profile => profile.name)).toEqual(sampleProfiles.map(profile => profile.name));
    expect(profiles.every(profile => profile.targets.protein === 126 && profile.targets.vitamin_c === 110)).toBe(true);
    const savedProfiles = sampleProfiles.map(profile => ({...profile, targets_reviewed: true}));
    const reviewed = {...current, metadata: {...current.metadata, crew_profiles: savedProfiles}};
    const retained = missionChangeProfiles(reviewed, config, [], 30);
    expect(retained.reduce((sum, profile) => sum + profile.targets.protein, 0)).toBeCloseTo(504);
    expect(retained[3].targets.protein / retained[0].targets.protein).toBeCloseTo(85 / 100);
  });

  it('gives a new crew member the current effective per-person target before review', () => {
    setup({run: {...run, metadata: {...run.metadata, adaptive: {...run.metadata.adaptive,
      daily: [{...daily(30), protein_target: 504}]}}}});
    fireEvent.click(screen.getByRole('button', {name: 'Add crew member'}));
    expect(screen.getAllByLabelText(/^Protein target for /).at(-1).value).toBe('126');
  });

  it('does not advertise an already canceled scenario crew arrival as pending', () => {
    setup({run: {...run, metadata: {...run.metadata, config: {...config,
      planning_events: [{day: 20, crew: 4, cancel_scenario_crew: true}]}, scenario: {event_day: 50, extra_crew: 2}}}});
    expect(screen.queryByText('Day 50: +2 crew')).toBeNull();
    expect(screen.queryByLabelText('Replace scheduled future crew changes')).toBeNull();
  });

  it('limits the sample roster to twelve and allows the name of an added crew member to be changed', () => {
    setup({run: {...run, metadata: {...run.metadata, adaptive: {...run.metadata.adaptive, daily: [{...daily(30), crew: 12}]}}}});
    expect(screen.getByRole('button', {name: 'Add crew member'}).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Name for crew-12'), {target: {value: 'New researcher'}});
    expect(screen.getByLabelText('Protein target for New researcher')).toBeTruthy();
  });
});
