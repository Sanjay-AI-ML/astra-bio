import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import NutritionPanel from './NutritionPanel.jsx';
import fixture from './test-fixture.json';
import sample from './crew-sample.fixture.json';

const clone=value=>structuredClone(value);
const bootstrap={...fixture,crew_sample:sample};
const defaultRequest=async(path,body)=>{
  if(path==='/snapshots/nutrition')return [];
  if(path==='/nutrition/assess')return {rows:sample.assessments.filter(row=>row.day===body.day),contributions:[],scope:sample.scope};
  throw new Error('Unexpected request: '+path);
};
const props={config:{...fixture.config,crew:4},bootstrap,request:defaultRequest,notify:vi.fn(),setConfig:vi.fn()};
afterEach(cleanup);

describe('Named sample crew in nutrition workspace',()=>{
  it('shares profile edits with the mission editor and adopts only a dated active roster',async()=>{
    const onProfilesChange=vi.fn();
    const reviewed=sample.profiles.map(p=>({...p,targets:{...p.targets,protein:120},targets_reviewed:true}));
    const run={metadata:{config:{planning_events:[{day:31,crew:4,crew_profiles:reviewed}]},adaptive:{daily:[{day:30,crew:4},{day:31,crew:4}]}}};
    const {rerender}=render(<NutritionPanel {...props} onProfilesChange={onProfilesChange} run={run} missionDay={30}/>);
    await act(async()=>{});
    expect(onProfilesChange).toHaveBeenLastCalledWith(sample.profiles);
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal protein target'),{target:{value:'111'}});
    expect(onProfilesChange.mock.calls.at(-1)[0][0].targets.protein).toBe(111);
    rerender(<NutritionPanel {...props} onProfilesChange={onProfilesChange} run={run} missionDay={31}/>);
    await act(async()=>{});
    expect(onProfilesChange.mock.calls.at(-1)[0][0].targets.protein).toBe(120);
    expect(screen.getByRole('img',{name:/Day 1 protein intake/}).getAttribute('aria-label')).toContain('Unknown g logged; target 120 g');
  });
  it('opens directly with named crew graphs and obtains day changes from the actual assessment endpoint',async()=>{
    const request=vi.fn(defaultRequest);
    render(<NutritionPanel {...props} request={request}/>);
    const chart=screen.getByRole('img',{name:/Day 1 protein intake/});
    for(const name of ['Shree Ram Vishal','Shamyuktha','Sanjay','Vamshika'])expect(chart.getAttribute('aria-label')).toContain(name);
    expect(screen.getByText('Fictional low-iron scenario')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox',{name:'Sample food-log day'}),{target:{value:'3'}});
    await act(async()=>{});
    expect(request).toHaveBeenCalledWith('/nutrition/assess',expect.objectContaining({day:3,profiles:sample.profiles,entries:sample.entries}));
    expect(screen.getByRole('img',{name:/Day 3 protein intake/}).getAttribute('aria-label')).not.toContain('Unknown g logged');
  });

  it('invalidates the graph after a profile edit rather than showing the old sample intake',async()=>{
    render(<NutritionPanel {...props}/>);
    fireEvent.click(screen.getByText('Crew profiles and daily targets'));
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal protein target'),{target:{value:'110'}});
    expect(screen.getByRole('img',{name:/Day 1 protein intake/}).getAttribute('aria-label')).toContain('Unknown g logged; target 110 g');
    expect(screen.getByText(/Food logs or targets changed/)).toBeTruthy();
  });

  it('adds numbered sample people when mission crew increases without inventing new blood results',async()=>{
    const expanded=clone(sample);
    const extra={profile_id:'crew-5',name:'Sample Crew 5',age:22,sex:'unspecified',targets:{energy:2200,protein:85,vitamin_c:100},targets_reviewed:false};
    expanded.profiles.push(extra);expanded.crew_count=5;
    expanded.assessments.push(...sample.assessments.filter(r=>r.profile_id==='crew-1').map(r=>({...r,profile_id:'crew-5',person:extra.name})));
    const request=vi.fn(async(path,body)=>path==='/nutrition/sample?count=5'?expanded:path==='/nutrition/assess'?{rows:expanded.assessments.filter(r=>r.day===body.day),contributions:[]}:defaultRequest(path,body));
    const {rerender}=render(<NutritionPanel {...props} request={request}/>);
    rerender(<NutritionPanel {...props} request={request} run={{metadata:{adaptive:{daily:[{day:30,crew:5}]}}}} missionDay={30}/>);
    await act(async()=>{});
    expect(request).toHaveBeenCalledWith('/nutrition/sample?count=5');
    expect(screen.getByRole('img',{name:/Day 1 protein intake/}).getAttribute('aria-label')).toContain('Sample Crew 5');
    expect(screen.getByRole('img',{name:/Fictional hemoglobin results/}).getAttribute('aria-label')).toContain('Sample Crew 5: Unknown');
    expect(props.setConfig).not.toHaveBeenCalled();
  });

  it('never attaches fictional blood values when restoring an ordinary intake snapshot',async()=>{
    const manual={schema_version:1,profiles:[{...sample.profiles[0],name:'Manual alias'}],entries:[],complete_days:{}};
    const request=vi.fn(async(path,body)=>path==='/snapshots/nutrition'?[{id:'manual',name:'Manual log',created_at_utc:'2026-10-12T00:00:00Z'}]:path==='/snapshots/nutrition/manual'?manual:path==='/nutrition/assess'?{rows:[],contributions:[]}:defaultRequest(path,body));
    render(<NutritionPanel {...props} request={request}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Restore intake snapshot'}));
    await act(async()=>{});
    expect(screen.queryByRole('img',{name:/Fictional hemoglobin results/})).toBeNull();
    expect(request.mock.calls.some(([path])=>path.startsWith('/nutrition/sample?'))).toBe(false);
  });
});
