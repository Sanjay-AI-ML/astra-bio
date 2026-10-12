import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import ModelEvidence from './ModelEvidence.jsx';

const candidate={candidate_id:'plantdoc-20261011T130000Z',ready:true,eligible:true,reason:'Hash verified.',tested_classes:['Tomato_healthy'],output_classes:15,temperature:1.8,
  metrics:{accuracy:.7,macro_f1:.65,known_samples:80,abstention:{coverage:.4}},baseline_metrics:{accuracy:.5,macro_f1:.45},limitations:['Source benchmark, not tray validation.']};
const evidence={plant:{active_id:'base',candidates:[candidate]},growth:{status:'experimental_fitted',record_count:540,independent_cycle_count:1,validation:{curve:{mae_g_per_plant:5.719}}},crop_response:{status:'awaiting_measurements'}};
afterEach(cleanup);

describe('Model evidence',()=>{
  it('loads recorded evidence without training and requires explicit model selection',async()=>{
    const request=vi.fn().mockResolvedValueOnce(evidence).mockResolvedValueOnce({plant_model:{kind:'fine_tuned'},registry:{...evidence.plant,active_id:candidate.candidate_id}});
    const setPlantModel=vi.fn(),notify=vi.fn();
    render(<ModelEvidence request={request} notify={notify} setPlantModel={setPlantModel}/>);
    await screen.findByText('Held-out accuracy');
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'Use selected model'}).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Plant model version'),{target:{value:candidate.candidate_id}});
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Use selected model'}));
    await waitFor(()=>expect(setPlantModel).toHaveBeenCalledWith({kind:'fine_tuned'}));
    expect(request).toHaveBeenLastCalledWith('/models/plant/select',{candidate_id:candidate.candidate_id});
    expect(screen.getByText('Source benchmark, not tray validation.')).not.toBeNull();
  });
  it('disables candidates that did not pass evaluation',async()=>{
    const request=vi.fn().mockResolvedValue({...evidence,plant:{active_id:'base',candidates:[{...candidate,eligible:false}]}});
    render(<ModelEvidence request={request} notify={vi.fn()}/>);
    expect((await screen.findByRole('option',{name:/evaluation gate not met/})).disabled).toBe(true);
  });
  it('reads the actual nested growth error and distinguishes one cycle from independent trials',async()=>{
    render(<ModelEvidence request={vi.fn().mockResolvedValue(evidence)} notify={vi.fn()} focus="crops"/>);
    expect(await screen.findByText(/Held-out fresh-mass MAE: 5.72 g\/plant/)).not.toBeNull();
    expect(screen.getByText(/540 measured plant\/day records across 1 independent cycle/)).not.toBeNull();
    expect(screen.getByText(/Status: awaiting_measurements/)).not.toBeNull();
    expect(screen.getByRole('button',{name:'Download blank crop-trial template'})).not.toBeNull();
  });
  it('shows failed evidence loading without inventing a ready model',async()=>{
    render(<ModelEvidence request={vi.fn().mockRejectedValue(new Error('Unavailable'))} notify={vi.fn()}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Unavailable');
    expect(screen.queryByLabelText('Plant model version')).toBeNull();
  });
});
