import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import MissionCropSuggestions from './MissionCropSuggestions.jsx';
afterEach(cleanup);
const run={history_id:'named-run',metadata:{created_at_utc:'now',config:{days:60}}};
it('uses the saved named plan from the next day and updates advice when its deadline changes',async()=>{
  const request=vi.fn(async(path,body)=>({day:body.day,deadline_day:body.deadline_day,recommendations:[],planned_crop_actions:[{crop_id:'quick',name:'Quick crop',day:18,harvest_day:32,predicted_harvest_kg:2,nutrients_at_harvest:{protein:20,vitamin_c:40},fits_deadline:body.deadline_day>=32},{crop_id:'slow',name:'Slow crop',day:18,harvest_day:58,predicted_harvest_kg:5, fits_deadline:body.deadline_day>=58}],forecast:{nutrients:[]}}));
  render(<MissionCropSuggestions run={run} day={17} request={request} navigate={vi.fn()}/>);
  await screen.findByRole('table',{name:'Timely planned crops and modeled nutrients for crew needs'});
  expect(request).toHaveBeenCalledWith('/crop-advisor',{run_id:'named-run',day:18,deadline_day:60,priority:'balanced',area_m2:1});
  fireEvent.change(screen.getByLabelText('Harvest needed by Day'),{target:{value:'40'}});
  await waitFor(()=>expect(request.mock.calls.at(-1)[1].deadline_day).toBe(40));
  await screen.findByText('Quick crop');
  expect(screen.queryByText('Slow crop')).toBeNull();
});
it('does not request future crops after the mission horizon',()=>{
  const request=vi.fn();render(<MissionCropSuggestions run={run} day={60} request={request} navigate={vi.fn()}/>);
  expect(screen.getByText(/no remaining growing window/)).toBeTruthy();expect(request).not.toHaveBeenCalled();
});
