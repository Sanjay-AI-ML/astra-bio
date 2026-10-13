import React from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import FruitMonitoring from './FruitMonitoring.jsx';
import {App} from './main.jsx';
import fixture from './test-fixture.json';

vi.mock('recharts', () => ({ResponsiveContainer: ({children}) => <div>{children}</div>, LineChart: ({children}) => <div>{children}</div>,
  Line: () => null, CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null, Legend: () => null, ReferenceLine: () => null}));

const NativeURL = URL;
const models = [
  {id: 'tomato-ripeness-3', name: 'Tomato three stages', ready: true, task: 'ripeness', species: ['tomato'], labels: ['unripe', 'semi_ripe', 'ripe'], source_url: 'https://example.com/tomato'},
  {id: 'tomato-ripeness-6', name: 'Tomato six stages', ready: true, task: 'ripeness', species: ['tomato'], labels: ['green', 'breaker', 'turning', 'pink', 'light_red', 'red']},
  {id: 'tomato-detection', name: 'Tomato detection', ready: false, task: 'detection', species: ['tomato'], labels: ['tomato'], reason: 'Checkpoint not installed.'},
  {id: 'produce-detection', name: 'Generic produce', ready: true, task: 'detection', species: ['tomato', 'bell_pepper', 'potato'], labels: ['Tomato', 'Capsicum', 'Potato']},
];
const catalog = {default_model_id: 'tomato-ripeness-3', models};
const result = {status: 'observed', reason: 'Visible tomato observations.', image_width: 800, image_height: 600,
  detections: [{id: 'fruit-1', class_label: 'ripe', stage: 'ripe', score: .92, box: [.1, .2, .4, .7]},
    {id: 'fruit-2', class_label: 'unripe', stage: 'unripe', score: .73, box: [.6, .15, .85, .5]}],
  counts_by_stage: {ripe: 1, unripe: 1}, visible_count: 2, warnings: ['Occluded produce is not counted.'],
  local_only: true, automatic_action: false, inventory_updated: false, provenance: {model_id: 'tomato-ripeness-3', checkpoint_sha256: 'verified-hash'}};
const photograph = name => new File(['image bytes'], name || 'tomatoes.jpg', {type: 'image/jpeg'});
const upload = file => fireEvent.change(screen.getByLabelText(/Fruit photograph · JPG/), {target: {files: [file || photograph()]}});
const ready = () => screen.findByText(/Model labels for this crop: unripe, semi ripe, ripe/);
const requestFor = (observation = result, available = catalog) => vi.fn(async (path) => path === '/fruit-models' ? available : observation);

beforeEach(() => {
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = vi.fn(() => 'blob:local-fruit');
    static revokeObjectURL = vi.fn();
  });
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); location.hash = '';});

describe('Fruit monitoring', () => {
  it('screens only on demand and sends the chosen model, crop and original file', async () => {
    const request = requestFor();
    render(<FruitMonitoring request={request}/>);
    await ready();
    const file = photograph();
    upload(file);
    fireEvent.change(screen.getByLabelText('Fruit model'), {target: {value: 'tomato-ripeness-6'}});
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Model labels for this crop: green, breaker, turning, pink, light red, red/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByRole('heading', {name: 'Fruit observation'});
    expect(request).toHaveBeenLastCalledWith('/fruit-image?crop_species=tomato&model_id=tomato-ripeness-6', expect.any(FormData));
    expect(request.mock.calls[1][1].get('file')).toBe(file);
  });

  it('draws normalized boxes, exposes counts and scores as text, and exports provenance', async () => {
    const exportEvidence = vi.fn();
    render(<FruitMonitoring request={requestFor()} exportEvidence={exportEvidence}/>);
    await ready(); upload();
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByRole('heading', {name: 'Fruit observation'});
    expect(screen.getByRole('img', {name: /Detection boxes and model scores/})).toBeTruthy();
    const boxes = screen.getAllByTestId('fruit-detection-box');
    expect(boxes).toHaveLength(2);
    expect(boxes[0].getAttribute('x')).toBe('80');
    expect(boxes[0].getAttribute('y')).toBe('120');
    expect(Number(boxes[0].getAttribute('width'))).toBeCloseTo(240);
    expect(Number(boxes[0].getAttribute('height'))).toBeCloseTo(300);
    const counts = screen.getByLabelText('Visible produce counts');
    expect(within(counts).getByText('Visible produce').nextElementSibling.textContent).toBe('2');
    expect(within(counts).getByText('ripe').nextElementSibling.textContent).toBe('1');
    const rows = within(screen.getByRole('table', {name: 'Visible produce observations'})).getAllByRole('row');
    expect(rows[1].textContent).toContain('92%');
    expect(rows[2].textContent).toContain('73%');
    expect(screen.getByText(/Visual maturity does not establish bacterial identity/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Export fruit evidence JSON'}));
    expect(exportEvidence).toHaveBeenCalledWith(expect.objectContaining({schema_version: 1, file_name: 'tomatoes.jpg', crop_species: 'tomato', model_id: 'tomato-ripeness-3',
      visible_count: 2, local_only: true, automatic_action: false, inventory_updated: false, provenance: result.provenance}));
  });

  it('uses the generic model for bell peppers and harvested potatoes without ripeness claims', async () => {
    const request = requestFor();
    render(<FruitMonitoring request={request}/>); await ready(); upload();
    fireEvent.change(screen.getByLabelText('Fruit crop'), {target: {value: 'bell pepper'}});
    expect(screen.getByLabelText('Fruit model').value).toBe('produce-detection');
    expect(screen.getByRole('option', {name: 'Tomato three stages'}).disabled).toBe(true);
    expect(screen.getByText(/without assessing ripeness/)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByRole('heading', {name: 'Fruit observation'});
    expect(request.mock.calls[1][0]).toBe('/fruit-image?crop_species=bell%20pepper&model_id=produce-detection');
    fireEvent.change(screen.getByLabelText('Fruit crop'), {target: {value: 'potato'}});
    expect(screen.queryByRole('heading', {name: 'Fruit observation'})).toBeNull();
    expect(screen.getByText(/Photograph harvested, exposed potato tubers/)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('shows zero visible detections without equating that result with absence of fruit', async () => {
    render(<FruitMonitoring request={requestFor({...result, status: 'no_detections', reason: 'No detections passed the threshold.', detections: [], counts_by_stage: {}, visible_count: 0})}/>);
    await ready(); upload(); fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByText('No detections passed the threshold.');
    expect(within(screen.getByLabelText('Visible produce counts')).getByText('0')).toBeTruthy();
    expect(screen.queryByTestId('fruit-detection-box')).toBeNull();
    expect(screen.getByText(/This does not establish that the photograph/)).toBeTruthy();
  });

  it.each([
    [{default_model_id: '', models: []}, 'No fruit models are registered.'],
    [{default_model_id: 'missing-model', models}, 'No model is available for this selection.'],
    [{default_model_id: 'tomato-detection', models}, 'Checkpoint not installed.'],
    [{default_model_id: models[0].id, models: [{...models[0], ready: undefined}]}, 'The selected model is not installed or its availability is unverified.'],
    [{default_model_id: models[0].id, models: [{...models[0], labels: []}]}, 'Model labels are unavailable. Reload model availability before screening.'],
  ])('withholds screening when model readiness or labels are unavailable (%j)', async (available, message) => {
    const request = requestFor(result, available);
    render(<FruitMonitoring request={request}/>);
    await screen.findByText(message); upload();
    expect(screen.getByRole('button', {name: 'Screen fruit image'}).disabled).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText('Visible produce counts')).toBeNull();
  });

  it('shows catalog errors and retries availability without screening', async () => {
    const request = vi.fn().mockRejectedValueOnce(new Error('Model service offline')).mockResolvedValueOnce(catalog);
    render(<FruitMonitoring request={request}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Model service offline');
    upload();
    expect(screen.getByRole('button', {name: 'Screen fruit image'}).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', {name: 'Reload fruit models'}));
    await ready();
    expect(request.mock.calls.map(call => call[0])).toEqual(['/fruit-models', '/fruit-models']);
  });

  it('clears an old observation and rejects oversized or unsupported uploads locally', async () => {
    const request = requestFor();
    render(<FruitMonitoring request={request}/>); await ready(); upload();
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByRole('heading', {name: 'Fruit observation'});
    const large = photograph('large.jpg'); Object.defineProperty(large, 'size', {value: 10 * 1024 * 1024 + 1}); upload(large);
    expect(screen.getByRole('alert').textContent).toContain('exceeds 10 MiB');
    expect(screen.queryByRole('heading', {name: 'Fruit observation'})).toBeNull();
    expect(screen.queryByRole('img', {name: /Selected produce photograph/})).toBeNull();
    expect(screen.getByRole('button', {name: 'Screen fruit image'}).disabled).toBe(true);
    upload(new File(['text'], 'notes.txt', {type: 'text/plain'}));
    expect(screen.getByRole('alert').textContent).toContain('Choose a JPG, PNG or WebP');
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('clears results on model changes and ignores a late response for an obsolete image', async () => {
    let resolveOld;
    const pending = new Promise(resolve => {resolveOld = resolve;});
    const request = vi.fn().mockResolvedValueOnce(catalog).mockReturnValueOnce(pending).mockResolvedValueOnce({...result, reason: 'New image observations.'});
    render(<FruitMonitoring request={request}/>); await ready(); upload(photograph('old.jpg'));
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    expect(screen.getByRole('button', {name: 'Screening fruit photograph…'}).disabled).toBe(true);
    upload(photograph('new.jpg'));
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByText('New image observations.');
    await act(async () => {resolveOld({...result, reason: 'Obsolete image observations.'}); await pending;});
    expect(screen.queryByText('Obsolete image observations.')).toBeNull();
    expect(screen.getByText('New image observations.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Fruit model'), {target: {value: 'tomato-ripeness-6'}});
    expect(screen.queryByRole('heading', {name: 'Fruit observation'})).toBeNull();
    expect(screen.queryByTestId('fruit-detection-box')).toBeNull();
    expect(request).toHaveBeenCalledTimes(3);
  });

  it.each(['rejected', 'unavailable'])('shows a withheld %s response without false counts', async status => {
    render(<FruitMonitoring request={requestFor({...result, status, reason: 'Observation withheld.', detections: [], visible_count: null})}/>);
    await ready(); upload(); fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    await screen.findByText('Observation withheld.');
    expect(screen.queryByLabelText('Visible produce counts')).toBeNull();
    expect(screen.getByRole('button', {name: 'Export fruit evidence JSON'})).toBeTruthy();
  });

  it('reports screening failures without rendering fabricated results', async () => {
    const request = vi.fn().mockResolvedValueOnce(catalog).mockRejectedValueOnce(new Error('Image decoder failed'));
    render(<FruitMonitoring request={request}/>); await ready(); upload();
    fireEvent.click(screen.getByRole('button', {name: 'Screen fruit image'}));
    expect((await screen.findByRole('alert')).textContent).toContain('Image decoder failed');
    expect(screen.queryByRole('heading', {name: 'Fruit observation'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Screen fruit image'}).disabled).toBe(false);
  });

  it('uses one plant photograph and runs only fruit checking on explicit submission', async () => {
    const fetch = vi.fn(async url => {
      const data = url === '/api/bootstrap' ? fixture : url === '/api/fruit-models' ? catalog : url === '/api/plant-overview/status' ? {ai:{configured:false}} : url === '/api/plant-overview' ?
        {plant_id:'Plant 01',screening_mode:'fruit',input_mode:'single_photo',leaf:{status:'not_requested'},fruit:result,ai:{configured:false}} : [];
      return {ok: true, json: async () => data};
    });
    vi.stubGlobal('fetch', fetch);
    location.hash = 'fruit';
    render(<App/>);
    await screen.findByRole('heading', {name: 'Fruit checking'});
    expect(document.querySelectorAll('input[type=file]')).toHaveLength(1);
    const file=photograph('whole-plant.jpg');
    fireEvent.change(screen.getByLabelText('Plant photograph'), {target: {files:[file]}});
    expect(screen.getByRole('img', {name: 'Selected plant photograph'})).toBeTruthy();
    expect(fetch.mock.calls.filter(([url]) => url === '/api/plant-overview')).toHaveLength(0);
    await waitFor(() => expect(fetch.mock.calls.filter(([url]) => /\/api\/(fruit|plant)-image/.test(url))).toHaveLength(0));
    await waitFor(() => expect(screen.getByRole('button', {name:'Check fruit'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', {name:'Check fruit'}));
    await screen.findByRole('region', {name:'Fruit checking result'});
    const form=fetch.mock.calls.find(([url])=>url==='/api/plant-overview')[1].body;
    expect(form.get('file')).toBe(file);
    expect(form.get('screening_mode')).toBe('fruit');
    expect([...form.values()].filter(value=>value instanceof File)).toHaveLength(1);
    expect(screen.getByText('Visible tomato observations.')).toBeTruthy();
  });
});
