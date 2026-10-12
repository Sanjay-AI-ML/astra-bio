import React,{useState} from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import MissionExplorer,{missionEvents,PlanComparison} from './MissionExplorer.jsx';

afterEach(cleanup);
const scenario={event_day:2,name:'Water remaining 60%'};
const plan={daily:[1,2,3].map(day=>({day,crew:day===3?6:4,energy_coverage_pct:100,protein_coverage_pct:day===2?80:100,vitamin_c_coverage_pct:100,reserve_days_available:7-day,reserve_kg:30-day,harvest_kg:day===3?2:0,water_l:10+day,water_available_l:day>=2?30:50,power_kwh:3,shortfall_normalized:day===2?.2:0})),planting:[{day:1,harvest_day:3,predicted_harvest_kg:9}]};
function Harness({data=plan,navigate=vi.fn()}){const [day,setDay]=useState(1);return <MissionExplorer plan={data} scenario={scenario} policy="baseline" selectedDay={day} onSelectDay={setDay} navigate={navigate}/>;}

describe('saved mission-day exploration',()=>{
  it('changes the daily context with milestones and preserves actual yield separately from nominal batches',()=>{
    render(<Harness/>);
    expect(screen.getByLabelText('Previous mission day').disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:/Day 2.*Scenario begins/}));
    const day2=screen.getByRole('group',{name:'Modeled ecosystem on day 2'});
    expect(within(day2).getByText('Lowest tracked coverage: 80%')).toBeTruthy();
    expect(within(day2).getByText('12 L')).toBeTruthy();
    expect(within(day2).getByText(/budget 30 L/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:/Day 3.*1 planned harvest/}));
    expect(within(screen.getByRole('group',{name:'Modeled ecosystem on day 3'})).getByText('2 kg')).toBeTruthy();
    expect(screen.queryByText('9 kg')).toBeNull();
    expect(screen.getByLabelText('Next mission day').disabled).toBe(true);
    expect(screen.getByText('Fixed baseline · simulated mission day')).toBeTruthy();
  });
  it('supports day input, previous and next, and contextual workflow navigation',()=>{
    const navigate=vi.fn();render(<Harness navigate={navigate}/>);
    fireEvent.change(screen.getByLabelText('Explore mission day'),{target:{value:'3'}});
    fireEvent.click(screen.getByLabelText('Previous mission day'));
    expect(screen.getByRole('group',{name:'Modeled ecosystem on day 2'})).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Next mission day'));
    fireEvent.click(screen.getByRole('button',{name:/FOOD RESERVE/}));
    expect(navigate).toHaveBeenCalledWith('pantry');
    expect(screen.getByLabelText('Explore mission day').getAttribute('aria-valuetext')).toBe('Simulated day 3');
  });
  it('leaves missing daily data unknown and does not render an explorer without results',()=>{
    const data={daily:[{day:1}],planting:[]};const {rerender}=render(<Harness data={data}/>);
    const ecosystem=screen.getByRole('group',{name:'Modeled ecosystem on day 1'});
    expect(within(ecosystem).getAllByText('—')).toHaveLength(4);
    expect(within(ecosystem).getByText('Lowest tracked coverage: —')).toBeTruthy();
    expect(within(ecosystem).queryByText('0 kg')).toBeNull();
    rerender(<MissionExplorer plan={{daily:[]}}/>);
    expect(screen.queryByRole('region',{name:'Mission day explorer'})).toBeNull();
  });
  it('excludes out-of-horizon batch dates and finds actual first modeled target gap',()=>{
    const events=missionEvents({...plan,planting:[...plan.planting,{day:2,harvest_day:10}]},scenario);
    expect(events.some(e=>e.day===10)).toBe(false);
    expect(events.find(e=>e.type==='gap').day).toBe(2);
    expect(events.find(e=>e.type==='harvest').day).toBe(3);
  });
  it('compares saved policies with absolute units without interpreting lower use as measured benefit',()=>{
    render(<PlanComparison metadata={{config:{days:3},baseline:{metrics:{shortfall_days:1,total_harvest_kg:2,total_water_l:40}},adaptive:{metrics:{shortfall_days:0,total_harvest_kg:3,total_water_l:35}}}}/>);
    expect(screen.getByText('-1 days difference')).toBeTruthy();
    expect(screen.getByText('+1 kg difference')).toBeTruthy();
    expect(screen.getByText('-5 L difference')).toBeTruthy();
    expect(screen.getByText(/not measured savings/)).toBeTruthy();
  });
  it('does not turn missing comparison metrics into zero differences',()=>{
    render(<PlanComparison metadata={{config:{days:3},baseline:{metrics:{}},adaptive:{metrics:{}}}}/>);
    expect(screen.getAllByText('Difference unavailable')).toHaveLength(3);
    expect(screen.getAllByText('—')).toHaveLength(6);
    expect(screen.queryByText('0 days difference')).toBeNull();
  });
});
