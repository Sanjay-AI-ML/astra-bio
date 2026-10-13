import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import AstronautGuidance from './AstronautGuidance.jsx';

const config = {days: 90, crew: 4, targets_per_crew: {energy: 2400, protein: 80, vitamin_c: 90}};
const run = {metadata: {config, adaptive: {daily: [{day: 1}]}}};
const crewState = {profiles: [{profile_id: 'one', name: 'Sanjay'}], entries: [], complete_days: {}, sample_only: true};
const nutrientRows = [
  {nutrient: 'energy', label: 'Energy', unit: 'kcal', target: 2400, intake: 1850, gap: 550, log_complete: true},
  {nutrient: 'protein', label: 'Protein', unit: 'g', target: 80, intake: 55, gap: 25, log_complete: true},
  {nutrient: 'vitamin_c', label: 'Vitamin C', unit: 'mg', target: 90, intake: 110, gap: 0, log_complete: true},
];
const member = {profile_id: 'one', name: 'Sanjay', targets_reviewed: true, target_source: 'accepted_mission', log_status: 'complete', focus_nutrient: 'protein', nutrients: nutrientRows,
  actions: [{id: 'protein', kind: 'intake_review', title: 'Review protein intake', message: 'The complete log is 25 g below the recorded target.'}],
  health_alerts: [{kind: 'sample_observation', sample_only: true, day: 1, message: 'Sample observation requires review.'}],
  food_options: [{food_key: 'spinach', name: 'Spinach', food_form: 'Raw spinach', reference_grams: 100, nutrients: {energy: 23, protein: 2.86, vitamin_c: 28.1}, available_grams: null, availability: 'reference_only', source_url: 'https://fdc.nal.usda.gov/food-details/168462/nutrients', reason: 'Reference composition for a food comparison.'}], facts: []};
const report = {schema_version: 1, evidence_id: 'evidence-one', day: 1, focus_nutrient: 'auto', sample_only: true, members: [member, {...member, profile_id: 'two', name: 'Vamshika'}], scope: {limitations: ['Only tracked nutrients are compared.']}, ai: {available: false}};
const clone = value => structuredClone(value);
const renderGuidance = props => render(<AstronautGuidance config={config} run={run} crewState={crewState} missionDay={1} setMissionDay={vi.fn()} request={vi.fn(async () => clone(report))} {...props}/>);
const ready = () => screen.findByRole('heading', {name: 'Daily nutrient picture'});
afterEach(cleanup);

describe('Individual astronaut guidance', () => {
  it('automatically compares the shared crew data at the mission day without editing the plan', async () => {
    const request = vi.fn(async () => clone(report));
    renderGuidance({request, missionDay: 12});
    await ready();
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith('/astronaut-guidance', {metadata: run.metadata, config, crew_state: crewState, day: 12, focus_nutrient: 'auto', demo_intake: true});
    expect(screen.getByText('Sample crew data')).toBeTruthy();
    expect(screen.getByRole('img', {name: 'Protein: daily target 80 g, recorded intake 55 g, remaining to target'})).toBeTruthy();
    const table = screen.getByRole('table', {name: 'Individual food options'});
    expect(table.textContent).toContain('100 g · Raw spinach');
    expect(table.textContent).toContain('Stock unconfirmed');
    expect(within(table).getByRole('link', {name: 'Composition reference ↗'}).getAttribute('href')).toContain('168462');
    expect(screen.queryByRole('button', {name: 'Explain with Gemini'})).toBeNull();
  });

  it('selects a person locally and sends focus changes as a new comparison', async () => {
    const request = vi.fn(async () => clone(report));
    renderGuidance({request});
    await ready();
    fireEvent.change(screen.getByRole('combobox', {name: 'Astronaut'}), {target: {value: 'two'}});
    expect(screen.getByRole('heading', {name: 'Vamshika'})).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole('combobox', {name: 'Nutrient focus'}), {target: {value: 'energy'}});
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await ready();
    expect(request.mock.calls.at(-1)[1].focus_nutrient).toBe('energy');
    expect(screen.getByRole('heading', {name: 'Vamshika'})).toBeTruthy();
  });

  it('keeps absent intake unknown and suppresses gaps for partial logs even if a server supplies them', async () => {
    const partial = {...clone(member), log_status: 'missing', nutrients: nutrientRows.map(row => ({...row, intake: null, log_complete: false}))};
    renderGuidance({request: async () => ({...clone(report), members: [partial]})});
    await ready();
    expect(screen.getByText(/No intake was recorded for this day/)).toBeTruthy();
    expect(screen.queryByText('25 g')).toBeNull();
    expect(screen.queryByText('550 kcal')).toBeNull();
    expect(screen.getByRole('img', {name: 'Protein: daily target 80 g, recorded intake Unknown, intake log incomplete'})).toBeTruthy();
    expect(screen.getAllByText('Unknown')).toHaveLength(3);
  });

  it('labels draft targets and keeps proposed intake separate from a reviewed target gap', async () => {
    const draft = {...clone(member), targets_reviewed: false, target_source: 'draft_profile', pending_target_change: true};
    renderGuidance({request: async () => ({...clone(report), members: [draft]})});
    await ready();
    expect(screen.getByText('Unreviewed targets')).toBeTruthy();
    expect(screen.getByText(/Target edits are pending/)).toBeTruthy();
    expect(screen.getAllByText('Target needs review')).toHaveLength(3);
    expect(screen.queryByText('25 g')).toBeNull();
    expect(screen.getByText('80 g')).toBeTruthy();
  });

  it('discards an old request when mission day or health records change', async () => {
    const pending = [], request = vi.fn(() => new Promise(resolve => pending.push(resolve)));
    const {rerender} = renderGuidance({request});
    const changed = {...crewState, blood_samples: [{crew_id: 'one', day: 7, hemoglobin_g_dl: 12}]};
    rerender(<AstronautGuidance config={config} run={run} crewState={changed} missionDay={7} request={request}/>);
    await act(async () => pending[0](clone(report)));
    expect(screen.queryByRole('heading', {name: 'Daily nutrient picture'})).toBeNull();
    await act(async () => pending[1]({...clone(report), day: 7}));
    await ready();
    expect(request.mock.calls.at(-1)[1].crew_state).toEqual(changed);
    expect(request.mock.calls.at(-1)[1].day).toBe(7);
    expect(screen.getByText('DAY 7 · INDIVIDUAL REVIEW')).toBeTruthy();
  });

  it('requests a configured AI explanation only on click using evidence ID and selected profile', async () => {
    const request = vi.fn(async path => path === '/astronaut-guidance' ? {...clone(report), ai: {available: true}} : {mode: 'local_evidence', summary: ['The recorded protein target is 80 g.'], reason: 'Provider unavailable; local computed evidence is shown.'});
    renderGuidance({request});
    await ready();
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Explain with Gemini'}));
    expect(await screen.findByText('Local evidence explanation')).toBeTruthy();
    expect(request.mock.calls[1]).toEqual(['/astronaut-guidance/ai', {evidence_id: 'evidence-one', profile_id: 'one'}]);
    expect(screen.getByText('The recorded protein target is 80 g.')).toBeTruthy();
    expect(screen.getByRole('img', {name: /Protein: daily target 80 g/})).toBeTruthy();
  });

  it('does not attach a late AI explanation to another astronaut', async () => {
    let resolve;
    const request = vi.fn(path => path === '/astronaut-guidance' ? Promise.resolve({...clone(report), ai: {available: true}}) : new Promise(done => {resolve = done;}));
    renderGuidance({request});
    await ready();
    fireEvent.click(screen.getByRole('button', {name: 'Explain with Gemini'}));
    fireEvent.change(screen.getByRole('combobox', {name: 'Astronaut'}), {target: {value: 'two'}});
    await act(async () => resolve({mode: 'gemini_fact_selection', summary: ['Old person explanation.']}));
    expect(screen.queryByText('Old person explanation.')).toBeNull();
    expect(screen.getByRole('heading', {name: 'Vamshika'})).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Explain with Gemini'}).disabled).toBe(false);
  });

  it('keeps computed guidance visible if the explanation fails', async () => {
    const request = vi.fn(async path => {
      if (path === '/astronaut-guidance') return {...clone(report), ai: {available: true}};
      throw new Error('AI explanation unavailable. Computed guidance remains available.');
    });
    renderGuidance({request});
    await ready();
    fireEvent.click(screen.getByRole('button', {name: 'Explain with Gemini'}));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('heading', {name: 'Daily nutrient picture'})).toBeTruthy();
    expect(screen.getByRole('table', {name: 'Individual food options'})).toBeTruthy();
  });

  it('links editing back to crew data and never creates missing crew nutrient measurements', async () => {
    const navigate = vi.fn();
    renderGuidance({navigate, request: async () => ({...clone(report), members: []})});
    await screen.findByRole('heading', {name: 'No named crew profile available'});
    fireEvent.click(screen.getByRole('link', {name: 'Review crew data'}));
    expect(navigate).toHaveBeenCalledWith('crew');
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('shows missing vital readings as unknown and distinguishes unmatched personal profiles', async () => {
    const unmatched = {...clone(member), mission_membership: 'not_matched', target_source: 'provided_profile', missing_metrics: ['Blood pressure', 'Heart rate for one or more crew members']};
    renderGuidance({request: async () => ({...clone(report), members: [unmatched]})});
    await ready();
    expect(screen.getByText(/not matched to the saved mission roster/)).toBeTruthy();
    expect(screen.getByText('Current personal profile targets')).toBeTruthy();
    const health = screen.getByRole('heading', {name: 'Health observations'}).closest('section');
    expect(within(health).getByText('Blood pressure')).toBeTruthy();
    expect(within(health).getByText('Heart rate')).toBeTruthy();
    expect(within(health).getAllByText('Unknown')).toHaveLength(2);
  });
});
