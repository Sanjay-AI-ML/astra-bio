r"""Reproduce a fictional 4-to-6 crew change after Day 30 through the local API.

Run from the app root: .venv\Scripts\python.exe scripts/run-rolling-crew-demo.py
No hardware measurements or MongoDB camera records are changed.
"""
from dataclasses import asdict, replace
from pathlib import Path
import json
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from astra_bio.crew_samples import crew_sample


def main():
    helpers=runpy.run_path(str(ROOT/'scripts/run-sample-mission.py'))
    config,scenario=helpers['sample_inputs']()
    post=helpers['post']
    provenance=dict(config.input_provenance)
    provenance['rolling_demo']='Fictional 4-to-6 crew arrival from Day 31; 4200 L total usable water and 3000 kWh cumulative electricity allowance are assumptions. No regeneration or automatic resupply.'
    config=replace(config,initial_water_l=4200,initial_energy_kwh=3000,input_provenance=provenance)
    source=post('/plans',{'config':asdict(config),'scenario':asdict(scenario)})
    profiles=crew_sample(6)['profiles']
    at_boundary=source['metadata']['adaptive']['daily'][29]
    # Preserve the existing aggregate needs across the four original fictional
    # profiles; two arrivals add explicit illustrative targets. No blood values
    # are used to obtain dietary targets.
    for nutrient in config.targets_per_crew:
        scale=at_boundary[nutrient+'_target']/sum(p['targets'][nutrient] for p in profiles[:4])
        for profile in profiles[:4]:profile['targets'][nutrient]*=scale
    for profile in profiles[4:]:profile['targets']={'energy':2200,'protein':100,'vitamin_c':100}
    for profile in profiles:profile['targets_reviewed']=True
    change={'crew_profiles':profiles,'reason':'SAMPLE · Two crew arrivals tomorrow; illustrative reviewed targets'}
    continued=post('/plans/continue',{'run_id':source['history_id'],'through_day':30,'mission_change':change})
    source_plan=source['metadata']['adaptive']
    plan=continued['metadata']['adaptive']
    detail=continued['metadata']['continuation']
    assert plan['daily'][:30]==source_plan['daily'][:30]
    assert plan['inventories']['30']==source_plan['inventories']['30']
    assert plan['daily'][30]['crew']==6
    checks={'history_days_1_to_30_unchanged':True,'boundary_food_inventory_unchanged':True,
        'crew_before':plan['daily'][29]['crew'],'crew_after':plan['daily'][30]['crew'],
        'daily_targets_before':{n:plan['daily'][29][n+'_target'] for n in config.targets_per_crew},
        'daily_targets_after':{n:plan['daily'][30][n+'_target'] for n in config.targets_per_crew},
        'remaining_at_checkpoint':detail['remaining_resource_stocks'],
        'remaining_at_mission_end':{key:plan['daily'][-1][key] for key in ('water_remaining_l','energy_remaining_kwh')},
        'growing_batches_at_checkpoint':len(detail['growing_cohorts_at_boundary']),
        'future_gap_days_previous_schedule':sum(r['shortfall_normalized']>1e-5 for r in continued['metadata']['baseline']['daily'][30:]),
        'future_gap_days_replanned':sum(r['shortfall_normalized']>1e-5 for r in plan['daily'][30:]),
        'planned_crop_actions':continued['planning_advice']['planned_crop_actions'],
        'additional_crop_selection_reason':continued['planning_advice']['selection_reason'],
        'source_run_id':source['history_id'],'continued_run_id':continued['history_id'],
        'scope':'Software simulation using terrestrial references and fictional mission/crew inputs; not clinical or tray validation'}
    for initial,remaining,used in ((4200,'water_remaining_l','water_l'),(3000,'energy_remaining_kwh','power_kwh')):
        error=abs(initial-sum(row[used] for row in plan['daily'])-plan['daily'][-1][remaining])
        assert error<1e-4
        checks[used+'_conservation_error']=error
    output=ROOT/'data/samples/rolling-crew-change'
    output.mkdir(parents=True,exist_ok=True)
    for name,value in (('source-run.json',source),('continued-run.json',continued),('summary.json',checks)):
        (output/name).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:value for key,value in checks.items() if key!='planned_crop_actions'},indent=2))
    print('Future selected crop batches:',len(checks['planned_crop_actions']))
    print('Reports:',output)


if __name__=='__main__':main()
