import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import fixture from './test-fixture.json';
import {App} from './main.jsx';

vi.mock('recharts',()=>({ResponsiveContainer:({children})=><div>{children}</div>,LineChart:({children})=><div>{children}</div>,
  Line:()=>null,CartesianGrid:()=>null,XAxis:()=>null,YAxis:()=>null,Tooltip:()=>null,Legend:()=>null}));
let calls;
const clone=v=>JSON.parse(JSON.stringify(v));
beforeEach(()=>{
  calls=[];location.hash='overview';
  vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
    calls.push({url,options});
    let data;
    if(url==='/api/bootstrap') data=clone(fixture);
    else if(url==='/api/snapshots/nutrition') data=[];
    else if(url==='/api/config/validate') data={config:JSON.parse(options.body).config};
    else if(url==='/api/explain') data={mode:'deterministic',narrative:'Saved model facts retained.',fallback_reason:'Local Ollama unavailable; verified explanation retained.'};
    else if(url==='/api/plans') {
      const {config,scenario}=JSON.parse(options.body);
      const daily=Array.from({length:config.days},(_,i)=>({day:i+1,crew:config.crew,nutrient_coverage_pct:100,energy_coverage_pct:100,protein_coverage_pct:100,vitamin_c_coverage_pct:100,water_l:10,power_kwh:3,harvest_kg:0,reserve_kg:10,shortfall_normalized:0,reserve_gap_days:0,capacity_gap:false}));
      const plan={status:'optimal',daily,metrics:{shortfall_days:0,total_harvest_kg:0,total_water_l:900,total_power_kwh:270},warnings:[],consumption:{1:{ration:1}},planting:[]};
      data={metadata:{created_at_utc:'2026-10-11T00:00:00Z',config,scenario,adaptive:plan,baseline:clone(plan)},explanation:{facts:[]},history_id:'saved'};
    } else throw new Error('Unexpected request: '+url);
    return {ok:true,json:async()=>data};
  }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('React planning workspace',()=>{
  it('opens the mission view and exposes every feature through navigation',async()=>{
    render(<App/>);
    await screen.findByText('Plan for the crew.');
    const navigation=screen.getByRole('navigation');
    expect(navigation.querySelectorAll('a').length).toBe(9);
    expect(screen.getByText('Actuation disabled')).toBeTruthy();
    expect(calls.filter(c=>c.url==='/api/plans')).toHaveLength(0);
  });
  it('runs only on explicit submit and retains the submitted result after form edits',async()=>{
    render(<App/>);await screen.findByText('Plan for the crew.');
    fireEvent.click(screen.getByRole('button',{name:/Open what-if simulator/}));
    await screen.findByRole('heading',{name:'What-if simulator'});
    fireEvent.change(screen.getByLabelText('Water remaining (%)'),{target:{value:'60'}});
    expect(calls.filter(c=>c.url==='/api/plans')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:/Run comparison/}));
    await screen.findByText('Model run: optimal');
    const submit=calls.find(c=>c.url==='/api/plans');
    expect(JSON.parse(submit.options.body).scenario.water_factor).toBe(.6);
    fireEvent.change(screen.getByLabelText('Water remaining (%)'),{target:{value:'40'}});
    expect(calls.filter(c=>c.url==='/api/plans')).toHaveLength(1);
    expect(screen.getByText('Model run: optimal').parentElement.textContent).toContain('water 60%');
    fireEvent.click(screen.getByLabelText('Optional local Ollama fact selection'));
    fireEvent.click(screen.getByRole('button',{name:'Explain using verified facts'}));
    await screen.findByText('Saved model facts retained.');
    expect(JSON.parse(calls.find(c=>c.url==='/api/explain').options.body).ollama).toBe(true);
  });
  it('keeps nutrition logs while switching workspaces',async()=>{
    render(<App/>);await screen.findByText('Plan for the crew.');
    fireEvent.click(screen.getByRole('link',{name:'Nutrition assessment'}));
    await screen.findByRole('heading',{name:'Nutrition assessment'});
    fireEvent.click(screen.getByRole('button',{name:'Add food to log'}));
    expect(screen.getByRole('button',{name:'Delete log entry'})).toBeTruthy();
    fireEvent.click(screen.getByRole('link',{name:'Mission overview'}));
    await screen.findByText('Plan for the crew.');
    fireEvent.click(screen.getByRole('link',{name:'Nutrition assessment'}));
    await screen.findByRole('heading',{name:'Nutrition assessment'});
    expect(screen.getByRole('button',{name:'Delete log entry'})).toBeTruthy();
  });
});
