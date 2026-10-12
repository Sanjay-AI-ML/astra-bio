import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import PlantOverview from './PlantOverview.jsx';

const summary={mode:'local_evidence',brief_overview:'Leaf evidence is tentative. Three visible tomatoes were detected.',next_steps:['Review the leaf underside.'],possible_use:['Inspect maturity before harvest.'],limitations:['Not a food-safety test.'],references:[]};
const report={plant_id:'Plant 01',crop_species:'tomato',input_mode:'single_photo',evidence_id:'evidence-token',overview:summary,ai:{configured:false},leaf:{status:'tentative',reason:'Tentative leaf match',predictions:[{condition:'early blight',score:.8}]},fruit:{status:'observed',reason:'Visible produce only',visible_count:3,counts_by_stage:{unripe:2,'fully ripe':1}}};
const clone=value=>structuredClone(value);
const upload=(label,name)=>fireEvent.change(screen.getByLabelText(label),{target:{files:[new File(['image'],name,{type:'image/jpeg'})]}});
beforeEach(()=>{vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:preview'),revokeObjectURL:vi.fn()});});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('combined plant screening',()=>{
  it('accepts one photo without pairing confirmation and displays both model observations',async()=>{
    const request=vi.fn(async path=>path==='/plant-overview/status'?{ai:{configured:false}}:clone(report));
    render(<PlantOverview request={request}/>);
    expect(document.querySelectorAll('input[type=file]')).toHaveLength(1);
    expect(screen.queryByRole('checkbox')).toBeNull();
    upload('Plant photograph','plant.jpg');
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    await screen.findByRole('region',{name:'Combined plant overview'});
    const form=request.mock.calls.find(([path])=>path==='/plant-overview')[1];
    expect(form.get('file').name).toBe('plant.jpg');
    expect([...form.values()].filter(value=>value instanceof File)).toHaveLength(1);
    expect(form.has('leaf_file')).toBe(false);
    expect(form.has('fruit_file')).toBe(false);
    expect(form.has('same_plant_confirmed')).toBe(false);
    expect(screen.getByText(summary.brief_overview)).toBeTruthy();
    expect(screen.getByText('3 visible detections')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Create brief Gemini overview'}).disabled).toBe(true);
  });
  it('a changed photograph clears the previous combined result',async()=>{
    const request=vi.fn(async path=>path==='/plant-overview/status'?{ai:{configured:false}}:clone(report));
    render(<PlantOverview request={request}/>);
    upload('Plant photograph','plant.jpg');
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    await screen.findByRole('region',{name:'Combined plant overview'});
    upload('Plant photograph','another-plant.jpg');
    expect(screen.queryByRole('region',{name:'Combined plant overview'})).toBeNull();
    expect(screen.getByRole('button',{name:'Analyze plant'}).disabled).toBe(false);
  });
  it('sends only an evidence identifier to Gemini on explicit click',async()=>{
    const enabled={...report,ai:{configured:true}};
    const request=vi.fn(async path=>path==='/plant-overview/status'?{ai:{configured:true}}:path==='/plant-overview/ai'?{...summary,mode:'gemini_fact_selection'}:clone(enabled));
    render(<PlantOverview request={request}/>);
    upload('Plant photograph','plant.jpg');
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    await screen.findByRole('region',{name:'Combined plant overview'});
    expect(request.mock.calls.some(([path])=>path==='/plant-overview/ai')).toBe(false);
    fireEvent.click(screen.getByRole('button',{name:'Create brief Gemini overview'}));
    await screen.findByText('AI-curated evidence');
    expect(request).toHaveBeenCalledWith('/plant-overview/ai',{evidence_id:'evidence-token'});
  });
  it('rejects an unsupported file without requesting inference',async()=>{
    const request=vi.fn(async()=>({ai:{configured:false}}));
    render(<PlantOverview request={request}/>);
    fireEvent.change(screen.getByLabelText('Plant photograph'),{target:{files:[new File(['bad'],'bad.pdf',{type:'application/pdf'})]}});
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Analyze plant'}).disabled).toBe(true);
    expect(request.mock.calls.some(([path])=>path==='/plant-overview')).toBe(false);
  });
  it('never applies an older screening result after inputs change',async()=>{
    let finish;
    const request=vi.fn(path=>path==='/plant-overview/status'?Promise.resolve({ai:{configured:false}}):new Promise(resolve=>{finish=resolve;}));
    render(<PlantOverview request={request}/>);
    upload('Plant photograph','plant.jpg');
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    fireEvent.change(screen.getByLabelText('Plant species'),{target:{value:'potato'}});
    await act(async()=>finish(clone(report)));
    expect(screen.queryByRole('region',{name:'Combined plant overview'})).toBeNull();
    expect(screen.getByLabelText('Fruit observation model').value).toBe('produce-detection');
  });
  it('rejects multiple photographs instead of silently analyzing the first',async()=>{
    const request=vi.fn(async()=>({ai:{configured:false}}));
    render(<PlantOverview request={request}/>);
    fireEvent.change(screen.getByLabelText('Plant photograph'),{target:{files:[new File(['a'],'a.jpg',{type:'image/jpeg'}),new File(['b'],'b.jpg',{type:'image/jpeg'})]}});
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','Choose one plant photograph.');
    expect(screen.getByRole('button',{name:'Analyze plant'}).disabled).toBe(true);
    expect(request.mock.calls.some(([path])=>path==='/plant-overview')).toBe(false);
  });
  it('withholds rejected leaf predictions while retaining visible fruit counts',async()=>{
    const rejected={...report,leaf:{status:'rejected',reason:'Species evidence conflicts',predictions:[{condition:'late blight',score:.99}]}};
    const request=vi.fn(async path=>path==='/plant-overview/status'?{ai:{configured:false}}:clone(rejected));
    render(<PlantOverview request={request}/>);
    upload('Plant photograph','plant.jpg');
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    await screen.findByRole('region',{name:'Combined plant overview'});
    expect(screen.queryByText('late blight')).toBeNull();
    expect(screen.getByText('3 visible detections')).toBeTruthy();
  });
  it('draws valid fruit markers in the original photograph and clears them when the photo changes',async()=>{
    const marked={...report,fruit:{...report.fruit,detections:[{box:[.1,.2,.4,.6],stage:'unripe',score:.8},{box:[.7,.6,.5,.9],stage:'fully ripe',score:.7}]}};
    const request=vi.fn(async path=>path==='/plant-overview/status'?{ai:{configured:false}}:clone(marked));
    render(<PlantOverview request={request}/>);
    upload('Plant photograph','plant.jpg');
    const image=screen.getByAltText('One photograph used for leaf and fruit analysis');
    Object.defineProperties(image,{naturalWidth:{value:1000},naturalHeight:{value:600}});
    fireEvent.load(image);
    fireEvent.click(screen.getByRole('button',{name:'Analyze plant'}));
    await screen.findByRole('region',{name:'Combined plant overview'});
    const boxes=screen.getAllByTestId('plant-fruit-box');
    expect(boxes).toHaveLength(1);
    expect(boxes[0].getAttribute('x')).toBe('100');
    expect(boxes[0].getAttribute('y')).toBe('120');
    expect(Number(boxes[0].getAttribute('width'))).toBeCloseTo(300);
    expect(screen.getByRole('table',{name:'Fruit markers in the plant photograph',hidden:true})).toBeTruthy();
    upload('Plant photograph','replacement.jpg');
    expect(screen.queryByTestId('plant-fruit-box')).toBeNull();
  });
});
