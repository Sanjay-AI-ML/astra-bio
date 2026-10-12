import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import RecoveryPanel from './RecoveryPanel.jsx';

const run = {history_id: 'saved-1', metadata: {created_at_utc: '2026-10-12T00:00:00Z',
  config: {days: 5, foods: [{id: 'food', name: 'Stored ration'}], targets_per_crew: {energy: 1}},
  scenario: {event_day: 3, name: 'Crew increase'}}};
const summary = {available: true, meets_targets: true, target_gap_days: 0, resource_gap_days: 0,
  reserve_gap_days: 1, minimum_coverage_pct: 100, first_target_gap_day: null, total_shortfall_normalized: 0};
const candidate = {id: 'food', title: 'Add stored food', rank: 1, status: 'optimal', summary,
  resources: {mode: 'food', arrival_day: 3, primary_minimum: 3, minimum_proven: true, food_kg: {food: 3}},
  cases_passed: 2, cases_tested: 4, worst_case_target_gap_days: 1,
  stress_tests: [{id: 'submitted', name: 'Submitted assumptions', summary},
    {id: 'combined', name: 'Lower yields and delayed harvests', summary: {...summary, meets_targets: false, target_gap_days: 1, first_target_gap_day: 5}}],
  plan: {planting: [{crop: 'Lettuce', day: 3, harvest_day: 5, area_m2: 1, predicted_harvest_kg: 2}]}, warnings: []};
const report = {status: 'calculated', event_day: 3, remaining_days: 3, candidates: [candidate,
  {id: 'water', title: 'Add daily water', status: 'infeasible', resources: {}, summary: {available: false, meets_targets: false}, warnings: ['Within limit'], plan: null, stress_tests: []}],
  recommended_candidate_id: 'food', limitations: ['These are proposed plans. Inventory is not changed.'], inputs: {}, input_sha256: 'abc'};
const clone = value => JSON.parse(JSON.stringify(value));
afterEach(cleanup);

describe('Recovery workflow', () => {
  it('preserves continuation metadata when a history save was unavailable', async()=>{
    const continued={...run,history_id:null,metadata:{...run.metadata,continuation:{through_day:3,next_day:4}}};
    const request=vi.fn(async()=>clone(report));
    render(<RecoveryPanel run={continued} request={request}/>);
    expect(screen.getByText('Day 4 onward')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Calculate recovery options'}));
    await screen.findByRole('region',{name:'Selected recovery plan'});
    expect(request.mock.calls[0][1].metadata).toEqual(continued.metadata);
  });
  it('never calculates on mount and sends saved inputs only on explicit submission', async () => {
    const request = vi.fn(async () => clone(report));
    render(<RecoveryPanel run={run} request={request}/>);
    expect(request).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Harvest yield in stress tests (%)'), {target: {value: '70'}});
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    await screen.findByRole('region', {name: 'Selected recovery plan'});
    expect(request).toHaveBeenCalledWith('/recovery', expect.objectContaining({run_id: 'saved-1', config: run.metadata.config,
      scenario: run.metadata.scenario, options: expect.objectContaining({lower_yield_factor: .7})}));
    expect(screen.getByText(/3 kg Stored ration/)).toBeTruthy();
    expect(within(screen.getByRole('table', {name: 'Recovery option comparison'})).getByText(/3 kg · minimum proven/)).toBeTruthy();
    expect(within(screen.getByRole('table', {name: 'Selected plan stress tests'})).getByText('Day 5')).toBeTruthy();
  });

  it('keeps infeasible interventions explicit and exports exactly the calculated report', async () => {
    const exportReport = vi.fn();
    render(<RecoveryPanel run={run} request={async () => clone(report)} exportReport={exportReport}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    await screen.findByRole('region', {name: 'Selected recovery plan'});
    expect(within(screen.getByRole('table', {name: 'Recovery option comparison'})).getByText('No feasible result within limit')).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Review add daily water'}).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', {name: 'Export recovery report JSON'}));
    expect(exportReport).toHaveBeenCalledWith(report);
    expect(run.metadata.config.foods[0]).toEqual({id: 'food', name: 'Stored ration'});
  });

  it('clears calculated recommendations when a stress assumption changes', async () => {
    const request = vi.fn(async () => clone(report));
    render(<RecoveryPanel run={run} request={request}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    await screen.findByRole('region', {name: 'Selected recovery plan'});
    fireEvent.change(screen.getByLabelText('Additional harvest delay (days)'), {target: {value: '5'}});
    expect(screen.queryByRole('region', {name: 'Selected recovery plan'})).toBeNull();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('ignores a late result when the saved mission comparison changes', async () => {
    let finish;
    const request = vi.fn(() => new Promise(resolve => {finish = resolve;}));
    const view = render(<RecoveryPanel run={run} request={request}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    view.rerender(<RecoveryPanel run={{...run, history_id: 'saved-2'}} request={request}/>);
    await act(async () => {finish(clone(report));});
    expect(screen.queryByRole('region', {name: 'Selected recovery plan'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Calculate recovery options'}).disabled).toBe(false);
  });

  it('shows calculation failures without fabricated recommendations', async () => {
    render(<RecoveryPanel run={run} request={async () => {throw new Error('Solver busy');}}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    expect((await screen.findByRole('alert')).textContent).toBe('Solver busy');
    expect(screen.queryByRole('table', {name: 'Recovery option comparison'})).toBeNull();
  });

  it('does not call a feasible time-limited solution a proven minimum', async () => {
    const response = clone(report);
    response.candidates[0].resources.minimum_proven = false;
    response.candidates[0].resources.primary_minimum = null;
    response.candidates[0].resources.feasible_resource_amount = 3;
    render(<RecoveryPanel run={run} request={async () => response}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    await screen.findByRole('region', {name: 'Selected recovery plan'});
    expect(within(screen.getByRole('table', {name: 'Recovery option comparison'})).getByText(/feasible, minimum unproven/)).toBeTruthy();
    expect(screen.queryByText(/minimum proven/)).toBeNull();
  });

  it('blocks another calculation while the existing mission solver is busy', () => {
    const request = vi.fn();
    render(<RecoveryPanel run={run} request={request} planningBusy/>);
    expect(screen.getByRole('button', {name: 'Calculate recovery options'}).disabled).toBe(true);
    expect(request).not.toHaveBeenCalled();
  });

  it('distinguishes a solver failure from a proven infeasible resource option', async () => {
    const response = clone(report);
    response.candidates[1].status = 'solver_error';
    render(<RecoveryPanel run={run} request={async () => response}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Calculate recovery options'}));
    await screen.findByRole('region', {name: 'Selected recovery plan'});
    const table = within(screen.getByRole('table', {name: 'Recovery option comparison'}));
    expect(table.getByText('Calculation unavailable')).toBeTruthy();
    expect(table.queryByText('No feasible result within limit')).toBeNull();
  });
});
