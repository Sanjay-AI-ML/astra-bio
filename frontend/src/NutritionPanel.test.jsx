import React, {useState} from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import NutritionPanel from './NutritionPanel.jsx';
import {validateCrewRoster} from './crew-roster.js';
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
  it('shares profile edits explicitly and adopts a dated active roster when used without a controlled parent',async()=>{
    const onProfilesChange=vi.fn();
    const reviewed=sample.profiles.map(p=>({...p,targets:{...p.targets,protein:120},targets_reviewed:true}));
    const run={metadata:{config:{planning_events:[{day:31,crew:4,crew_profiles:reviewed}]},adaptive:{daily:[{day:30,crew:4},{day:31,crew:4}]}}};
    const {rerender}=render(<NutritionPanel {...props} onProfilesChange={onProfilesChange} run={run} missionDay={30}/>);
    await act(async()=>{});
    expect(onProfilesChange).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal protein target'),{target:{value:'111'}});
    expect(onProfilesChange.mock.calls.at(-1)[0][0].targets.protein).toBe(111);
    rerender(<NutritionPanel {...props} onProfilesChange={onProfilesChange} run={run} missionDay={31}/>);
    await act(async()=>{});
    expect(onProfilesChange).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Shree Ram Vishal protein target').value).toBe('120');
    expect(screen.getByRole('img',{name:/Day 1 protein intake/}).getAttribute('aria-label')).toContain('Unknown g logged; target 120 g');
  });

  it('preserves shared edited names and targets through playback changes and tab remounts',async()=>{
    let latest=clone(sample.profiles);
    const onProfilesChange=vi.fn(value=>{latest=value;});
    const future=sample.profiles.map(profile=>({...profile,name:'Old scheduled name',targets:{...profile.targets,protein:160}}));
    const run={metadata:{config:{days:90,planning_events:[{day:31,crew:4,crew_profiles:future}]},adaptive:{daily:[{day:17,crew:4},{day:31,crew:6}]}}};
    const request=vi.fn(defaultRequest);
    const {rerender,unmount}=render(<NutritionPanel {...props} request={request} run={run} missionDay={17} crewProfiles={latest} onProfilesChange={onProfilesChange}/>);
    expect(onProfilesChange).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Alias 1'),{target:{value:'Vishal reviewed'}});
    rerender(<NutritionPanel {...props} request={request} run={run} missionDay={17} crewProfiles={latest} onProfilesChange={onProfilesChange}/>);
    fireEvent.change(screen.getByLabelText('Vishal reviewed protein target'),{target:{value:'123'}});
    rerender(<NutritionPanel {...props} request={request} run={run} missionDay={31} crewProfiles={latest} onProfilesChange={onProfilesChange}/>);
    await act(async()=>{});
    expect(screen.getByLabelText('Alias 1').value).toBe('Vishal reviewed');
    expect(screen.getByLabelText('Vishal reviewed protein target').value).toBe('123');
    expect(latest).toHaveLength(4);
    expect(request.mock.calls.some(([path])=>path.startsWith('/nutrition/sample?'))).toBe(false);
    unmount();
    render(<NutritionPanel {...props} run={run} missionDay={31} crewProfiles={latest} onProfilesChange={onProfilesChange}/>);
    expect(screen.getByLabelText('Alias 1').value).toBe('Vishal reviewed');
    expect(screen.getByLabelText('Vishal reviewed protein target').value).toBe('123');
    expect(latest[0].profile_id).toBe(sample.profiles[0].profile_id);
    expect(onProfilesChange).toHaveBeenCalledTimes(2);
  });

  it('applies exact edited people and individually reviewed targets from the selected mission day',async()=>{
    const onApplyCrew=vi.fn(async()=>{});
    const run={metadata:{config:{days:90},adaptive:{daily:[{day:17,crew:4,energy_target:8800,protein_target:360,vitamin_c_target:400}]}}};
    function SharedRoster(){
      const [profiles,setProfiles]=useState(clone(sample.profiles));
      return <NutritionPanel {...props} run={run} missionDay={17} crewProfiles={profiles} missionCrewProfiles={sample.profiles} onProfilesChange={setProfiles} onApplyCrew={onApplyCrew}/>;
    }
    render(<SharedRoster/>);
    fireEvent.change(screen.getByLabelText('Alias 1'),{target:{value:'Shree Ram Vishal mission'}});
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal mission protein target'),{target:{value:'125'}});
    fireEvent.click(screen.getByRole('button',{name:'Use this crew & replan from Day 18'}));
    expect(onApplyCrew).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('Review each person');
    fireEvent.click(screen.getByRole('button',{name:'Mark all planning targets reviewed'}));
    fireEvent.click(screen.getByRole('button',{name:'Use this crew & replan from Day 18'}));
    await act(async()=>{});
    expect(onApplyCrew).toHaveBeenCalledTimes(1);
    const [sent,options]=onApplyCrew.mock.calls[0];
    expect(options).toEqual({through_day:17});
    expect(sent.map(profile=>profile.name)).toEqual(['Shree Ram Vishal mission','Shamyuktha','Sanjay','Vamshika']);
    expect(sent[0]).toMatchObject({profile_id:sample.profiles[0].profile_id,targets:{protein:125},targets_reviewed:true});
    expect(sent.every(profile=>profile.targets_reviewed)).toBe(true);
    expect(screen.queryByRole('button',{name:'Apply mean reviewed targets to planner'})).toBeNull();
  });

  it('rejects invalid target values and lets the shared crew count differ from the starting mission count',async()=>{
    const onApplyCrew=vi.fn(async()=>{});
    const run={metadata:{config:{days:90},adaptive:{daily:[{day:17,crew:4}]}}};
    function SharedRoster(){
      const [profiles,setProfiles]=useState(sample.profiles.map(profile=>({...clone(profile),targets_reviewed:true})));
      return <NutritionPanel {...props} run={run} missionDay={17} crewProfiles={profiles} onProfilesChange={setProfiles} onApplyCrew={onApplyCrew}/>;
    }
    render(<SharedRoster/>);
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal protein target'),{target:{value:'0'}});
    fireEvent.click(screen.getByRole('button',{name:'Use this crew & replan from Day 18'}));
    expect(screen.getByRole('alert').textContent).toContain('positive energy, protein and vitamin C');
    expect(onApplyCrew).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Shree Ram Vishal protein target'),{target:{value:'100'}});
    fireEvent.click(screen.getByRole('button',{name:'Add crew profile'}));
    fireEvent.click(screen.getByRole('button',{name:'Mark all planning targets reviewed'}));
    fireEvent.click(screen.getByRole('button',{name:'Use this crew & replan from Day 18'}));
    await act(async()=>{});
    expect(onApplyCrew.mock.calls[0][0]).toHaveLength(5);
    expect(onApplyCrew.mock.calls[0][0][4].name).toBeTruthy();
    expect(onApplyCrew.mock.calls[0][0][4].name).not.toBe('Sample Crew 5');
    expect(sample.profiles.some(profile=>profile.name===onApplyCrew.mock.calls[0][0][4].name)).toBe(false);
    expect(onApplyCrew.mock.calls[0][0][4].targets.protein).toBe(87.5);
  });

  it('keeps every roster input fixed while its reviewed plan is being saved',async()=>{
    const onProfilesChange=vi.fn(),onApplyCrew=vi.fn();
    const run={metadata:{config:{days:90},adaptive:{daily:[{day:17,crew:4}]}}};
    render(<NutritionPanel {...props} run={run} missionDay={17} crewProfiles={sample.profiles} onProfilesChange={onProfilesChange} onApplyCrew={onApplyCrew} crewPlanningBusy/>);
    await act(async()=>{});
    for(const label of ['Alias 1','Shree Ram Vishal protein target','Shree Ram Vishal age','Shree Ram Vishal reference sex','Shree Ram Vishal reviewed targets'])expect(screen.getByLabelText(label).disabled).toBe(true);
    for(const label of ['Load named sample crew','Add crew profile','Remove Shree Ram Vishal','Mark all planning targets reviewed','Replanning…'])expect(screen.getByRole('button',{name:label}).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Add crew profile'}));
    fireEvent.click(screen.getByRole('button',{name:'Remove Shree Ram Vishal'}));
    expect(onProfilesChange).not.toHaveBeenCalled();
    expect(onApplyCrew).not.toHaveBeenCalled();
  });

  it('enforces 1–12 crew and preserves retained identities when someone leaves',async()=>{
    let latest;
    function SharedRoster(){
      const [profiles,setProfiles]=useState(Array.from({length:12},(_,index)=>({...clone(sample.profiles[index%4]),profile_id:'person-'+index,name:'Member '+(index+1)})));
      latest=profiles;
      return <NutritionPanel {...props} crewProfiles={profiles} onProfilesChange={setProfiles}/>;
    }
    render(<SharedRoster/>);
    await act(async()=>{});
    expect(screen.getByRole('button',{name:'Add crew profile'}).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Remove Member 6'}));
    expect(latest).toHaveLength(11);
    expect(latest.map(profile=>profile.profile_id)).toEqual(Array.from({length:12},(_,index)=>'person-'+index).filter(id=>id!=='person-5'));
    expect(screen.getByRole('button',{name:'Add crew profile'}).disabled).toBe(false);
    for(const profile of latest.slice(1))fireEvent.click(screen.getByRole('button',{name:'Remove '+profile.name}));
    expect(latest).toHaveLength(1);
    expect(screen.getByRole('button',{name:'Remove Member 1'}).disabled).toBe(true);
  });

  it('only applies future needs within the unfinished mission interval',async()=>{
    const onApplyCrew=vi.fn();
    const run={metadata:{config:{days:90},continuation:{through_day:30},adaptive:{daily:[{day:29,crew:4},{day:30,crew:4},{day:90,crew:4}]}}};
    const reviewed=sample.profiles.map(profile=>({...clone(profile),targets_reviewed:true}));
    const {rerender}=render(<NutritionPanel {...props} run={run} missionDay={29} crewProfiles={reviewed} onApplyCrew={onApplyCrew}/>);
    expect(screen.getByRole('button',{name:'Use this crew & replan from Day 30'}).disabled).toBe(true);
    rerender(<NutritionPanel {...props} run={run} missionDay={30} crewProfiles={reviewed} onApplyCrew={onApplyCrew}/>);
    expect(screen.getByRole('button',{name:'Use this crew & replan from Day 31'}).disabled).toBe(false);
    rerender(<NutritionPanel {...props} run={run} missionDay={90} crewProfiles={reviewed} onApplyCrew={onApplyCrew}/>);
    expect(screen.getByRole('button',{name:'Use this crew & replan from Day 91'}).disabled).toBe(true);
    expect(onApplyCrew).not.toHaveBeenCalled();
    await act(async()=>{});
  });

  it('validates the exact roster structure accepted by reviewed planning',()=>{
    const reviewed=sample.profiles.map(profile=>({...clone(profile),targets_reviewed:true}));
    expect(validateCrewRoster(reviewed)).toBe('');
    for(const badId of [null,7,'   ',reviewed[1].profile_id])expect(validateCrewRoster([{...reviewed[0],profile_id:badId},...reviewed.slice(1)])).toContain('unique stable ID');
    for(const badTarget of ['',true,'100',Infinity,NaN,-1,0])expect(validateCrewRoster([{...reviewed[0],targets:{...reviewed[0].targets,protein:badTarget}}])).toContain('positive energy, protein and vitamin C');
    expect(validateCrewRoster([{...reviewed[0],name:'  '}])).toContain('name');
    expect(validateCrewRoster([{...reviewed[0],age:1.5}])).toContain('Age');
    expect(validateCrewRoster([{...reviewed[0],targets_reviewed:'true'}])).toContain('Review each person');
    expect(validateCrewRoster([{...reviewed[0],targets_reviewed:false}],false)).toBe('');
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

  it('adds a distinctly named sample person when mission crew increases without inventing new blood results',async()=>{
    const expanded=clone(sample);
    const extra={profile_id:'crew-5',name:'Sample Crew 5',age:22,sex:'unspecified',targets:{energy:2200,protein:85,vitamin_c:100},targets_reviewed:false};
    expanded.profiles.push(extra);expanded.crew_count=5;
    expanded.assessments.push(...sample.assessments.filter(r=>r.profile_id==='crew-1').map(r=>({...r,profile_id:'crew-5',person:extra.name})));
    const request=vi.fn(async(path,body)=>path==='/nutrition/sample?count=5'?expanded:path==='/nutrition/assess'?{rows:expanded.assessments.filter(r=>r.day===body.day),contributions:[]}:defaultRequest(path,body));
    const {rerender}=render(<NutritionPanel {...props} request={request}/>);
    rerender(<NutritionPanel {...props} request={request} run={{metadata:{adaptive:{daily:[{day:30,crew:5}]}}}} missionDay={30}/>);
    await act(async()=>{});
    expect(request).toHaveBeenCalledWith('/nutrition/sample?count=5');
    const intakeLabel=screen.getByRole('img',{name:/Day 1 protein intake/}).getAttribute('aria-label');
    const intakeDetails=intakeLabel.split(' intake in g. ')[1]?.split('. All comparison')[0]||'';
    const intakePeople=[...intakeDetails.matchAll(/(?:^|; )([^:;]+): [^;]+ logged; target \d+ g;/g)].map(match=>match[1]);
    const addedName=intakePeople.find(name=>!sample.profiles.some(profile=>profile.name===name));
    expect(addedName).toBeTruthy();
    expect(addedName).not.toBe('Sample Crew 5');
    expect(screen.getByRole('img',{name:/Fictional hemoglobin results/}).getAttribute('aria-label')).toContain(`${addedName}: Unknown`);
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
