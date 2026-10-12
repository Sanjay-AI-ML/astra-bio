import {describe,it,expect} from 'vitest';
import {missionCrewContext,initialNutritionRoster} from './mission-crew.js';
const profile=(id,name,protein)=>({profile_id:id,name,targets:{energy:2200,protein,vitamin_c:100},targets_reviewed:true});
const config={crew:2,targets_per_crew:{energy:2200,protein:90,vitamin_c:100},crew_profiles:[profile('a','Vishal',100),profile('b','Sanjay',80)],planning_events:[]};
describe('dated mission identities',()=>{
  it('keeps historical people and matches their nutrient totals after a future roster change',()=>{
    const run={metadata:{config:{...config,planning_events:[{day:18,crew:1,crew_profiles:[profile('b','Sanjay',120)],targets_per_crew:{energy:2200,protein:120,vitamin_c:100}}]},adaptive:{daily:[{day:17,crew:2,protein_target:180},{day:18,crew:1,protein_target:120}]}}};
    expect(missionCrewContext(run,config,17).members.map(p=>p.name)).toEqual(['Vishal','Sanjay']);
    expect(missionCrewContext(run,config,18).members[0].targets.protein).toBe(120);
    expect(config.crew_profiles[0].targets.protein).toBe(100);
  });
  it('retains individual proportions under independent target changes with or without saved rows',()=>{
    const run={metadata:{config:{...config,planning_events:[{day:8,targets_per_crew:{energy:2200,protein:135,vitamin_c:100}}]},scenario:{event_day:12,extra_crew:0,target_factors:{protein:2}}}};
    const result=missionCrewContext(run,config,12);
    expect(result.aggregate_daily_targets.protein).toBe(540);
    expect(result.members.map(p=>p.targets.protein)).toEqual([300,240]);
  });
  it('leaves unknown arrival identities unassigned and resolves nutrition bootstrap from stored people',()=>{
    const run={metadata:{config,scenario:{event_day:3,extra_crew:1}}};
    expect(missionCrewContext(run,config,3).unnamed_count).toBe(1);
    expect(missionCrewContext(run,config,3).members.map(p=>p.name)).toEqual(['Vishal','Sanjay']);
    expect(initialNutritionRoster({last_run:run,config,crew_sample:{profiles:[profile('x','Wrong sample',1)]}})[0].name).toBe('Vishal');
  });
});
