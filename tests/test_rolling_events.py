"""State conservation and dated requirements across repeated mission changes."""
from copy import deepcopy
from dataclasses import replace

import pytest

from astra_bio.continuation import continue_plan
from astra_bio.model import CropSpec, FoodSpec, HabitatConfig, Scenario
from astra_bio.planner import _day_conditions, run_comparison
from astra_bio.recovery import RecoveryOptions, analyze_recovery


def habitat(**changes):
    return replace(HabitatConfig(days=12, crew=1, area_m2=2,
        water_budget_l_per_day=5, power_budget_kwh_per_day=2,
        crew_water_l_per_day=1, reserve_days=0,
        initial_water_l=20, initial_energy_kwh=5,
        foods=[FoodSpec('pantry', 'Stored food', .5, {'energy':100,'protein':10,'vitamin_c':10})],
        crops=[CropSpec('leaf', 'Test leaf', 3, 1, .5, .2, {'energy':100,'protein':10,'vitamin_c':10})],
        targets_per_crew={'energy':10,'protein':1,'vitamin_c':1},
        nutrient_units={'energy':'kcal','protein':'g','vitamin_c':'mg'}), **changes)


def roster(count, protein=1):
    return [{'profile_id':f'crew-{i}', 'name':f'Crew {i}',
        'targets':{'energy':10,'protein':protein,'vitamin_c':1},
        'targets_reviewed':True} for i in range(1,count+1)]


def test_full_roster_updates_only_future_and_preserves_resource_and_food_ledgers():
    config, scenario = habitat(), Scenario('nominal','Nominal',event_day=12)
    source = run_comparison(config, scenario).adaptive
    original = deepcopy(source.as_dict())
    config2, result, detail = continue_plan(config,scenario,source,4,
        mission_change={'crew_profiles':roster(2,1.5),'reason':'New crew arrives'})
    assert result.adaptive.daily[:4] == result.baseline.daily[:4] == source.daily[:4]
    assert result.adaptive.inventories[4] == source.inventories[4]
    assert result.adaptive.consumption[4] == source.consumption[4]
    assert result.adaptive.daily[4]['crew'] == 2
    assert result.adaptive.daily[4]['protein_target'] == 3
    assert result.baseline.daily[4]['protein_target'] == 3
    assert config2.crew == 1
    assert detail['crew_profiles'][1]['name'] == 'Crew 2'
    for initial,remaining,used in ((20,'water_remaining_l','water_l'),(5,'energy_remaining_kwh','power_kwh')):
        assert detail['remaining_resource_stocks']['water_l' if used=='water_l' else 'energy_kwh'] == pytest.approx(source.daily[3][remaining])
        for plan in (result.adaptive,result.baseline):
            assert plan.daily[-1][remaining] == pytest.approx(initial-sum(r[used] for r in plan.daily),abs=1e-5)
            assert all(r[remaining]>=0 for r in plan.daily)
    assert source.as_dict() == original


def test_repeated_changes_keep_first_event_and_preserve_crop_age_and_past_rows():
    config, scenario = habitat(initial_water_l=100), Scenario('nominal','Nominal',event_day=12)
    source=run_comparison(config,scenario).adaptive
    config2, first, _=continue_plan(config,scenario,source,2,mission_change={'crew_profiles':roster(2)})
    config3, second, detail=continue_plan(config2,scenario,first.adaptive,6,
        mission_change={'crew_profiles':roster(3,2),'water_budget_l_per_day':4,'area_m2':1})
    assert second.adaptive.daily[:6] == first.adaptive.daily[:6]
    assert len(config3.planning_events)==2
    assert second.adaptive.daily[6]['crew']==3
    assert second.adaptive.daily[6]['protein_target']==6
    assert second.adaptive.daily[6]['water_available_l']==4
    assert second.adaptive.daily[6]['area_available_m2']==1
    original_cohorts={(b['crop_id'],b['day'],b['harvest_day']) for b in detail['growing_cohorts_at_boundary']}
    assert all((b['crop_id'],b['day'],b['harvest_day']) in original_cohorts
        for b in second.adaptive.planting if b['day']<=6<b['harvest_day'])
    assert detail['remaining_resource_stocks']['water_l']==pytest.approx(first.adaptive.daily[5]['water_remaining_l'])


def test_announced_future_event_remains_after_review_then_absolute_override_supersedes_it():
    config=habitat(initial_water_l=100)
    scenario=Scenario('future','Announced future event',event_day=8,extra_crew=1,target_factors={'protein':1.4},water_factor=.5)
    source=run_comparison(config,scenario).adaptive
    config2, first, _=continue_plan(config,scenario,source,3,mission_change={'crew_profiles':roster(2,2),'water_budget_l_per_day':4})
    assert first.adaptive.daily[3]['protein_target']==4
    assert first.adaptive.daily[7]['crew']==3
    assert first.adaptive.daily[7]['protein_target']==pytest.approx(8.4)
    assert first.adaptive.daily[7]['water_available_l']==2
    _, second, _=continue_plan(config2,scenario,first.adaptive,8,mission_change={'crew_profiles':roster(2,1.5),'water_budget_l_per_day':5})
    assert second.adaptive.daily[8]['protein_target']==3
    assert second.adaptive.daily[8]['crew']==2
    assert second.adaptive.daily[8]['water_available_l']==5


def test_explicit_roster_replacement_supersedes_day_31_and_32_without_resetting_state():
    past = {'day':3, 'crew':2, 'crew_profiles':roster(2),
            'targets_per_crew':{'energy':10,'protein':1,'vitamin_c':1}}
    arrivals = {'day':31, 'crew':6, 'crew_profiles':roster(6,2),
                'targets_per_crew':{'energy':10,'protein':2,'vitamin_c':1},
                'water_budget_l_per_day':5, 'power_budget_kwh_per_day':1,
                'area_m2':1, 'reason':'Combined crew and resource event'}
    next_roster = {'day':32, 'crew':6, 'crew_profiles':roster(6,3),
                   'targets_per_crew':{'energy':10,'protein':3,'vitamin_c':1},
                   'reason':'Previous future roster'}
    independent_targets = {'day':34, 'targets_per_crew':{'energy':10,'protein':1.25,'vitamin_c':1}}
    count_and_targets = {'day':35, 'crew':6,
                         'targets_per_crew':{'energy':10,'protein':1.75,'vitamin_c':1}}
    config = habitat(days=36, initial_water_l=200, initial_energy_kwh=100,
                     planning_events=[past, arrivals, next_roster, independent_targets, count_and_targets])
    scenario = Scenario('nominal','Nominal',event_day=36)
    source = run_comparison(config,scenario).adaptive
    original = deepcopy(source.as_dict())
    updated, comparison, details = continue_plan(config,scenario,source,4,
        mission_change={'crew_profiles':roster(3,1.5),'replace_future_crew_changes':True})
    assert updated.planning_events[0] == past
    assert next(e for e in updated.planning_events if e['day']==31) == {
        key:value for key,value in arrivals.items() if key not in {'crew','crew_profiles','targets_per_crew'}}
    assert not any(e['day']==32 for e in updated.planning_events)
    assert next(e for e in updated.planning_events if e['day']==34) == independent_targets
    assert next(e for e in updated.planning_events if e['day']==35) == {
        key:value for key,value in count_and_targets.items() if key!='crew'}
    assert details['replace_future_crew_changes'] is True
    assert details['superseded_crew_event_days'] == [31,32,35]
    assert details['pending_scenario_crew_cancelled'] is False
    assert config.planning_events == [past,arrivals,next_roster,independent_targets,count_and_targets]
    for plan in (comparison.adaptive,comparison.baseline):
        assert plan.daily[:4] == source.daily[:4]
        assert plan.inventories[4] == source.inventories[4]
        assert plan.consumption[4] == source.consumption[4]
        assert all(row['crew']==3 for row in plan.daily[4:])
        assert plan.daily[30]['protein_target'] == 4.5
        assert plan.daily[31]['protein_target'] == 4.5
        assert plan.daily[33]['protein_target'] == 3.75
        assert plan.daily[34]['protein_target'] == 5.25
        assert plan.daily[30]['area_available_m2'] == 1
        assert plan.daily[30]['water_available_l'] == 5
        assert plan.daily[30]['power_available_kwh'] == 1
        remaining = source.inventories[4]['pantry']
        assert sum(v['pantry'] for d,v in plan.consumption.items() if d>4) <= remaining+1e-6
        for initial,remaining_key,used_key in ((200,'water_remaining_l','water_l'),(100,'energy_remaining_kwh','power_kwh')):
            assert plan.daily[-1][remaining_key] == pytest.approx(initial-sum(r[used_key] for r in plan.daily),abs=1e-5)
            assert all(r[remaining_key]>=0 for r in plan.daily)
    carried = details['growing_cohorts_at_boundary']
    assert carried
    old_dates = {(b['crop_id'],b['day'],b['harvest_day']) for b in carried}
    assert all((b['crop_id'],b['day'],b['harvest_day']) in old_dates
               for b in comparison.adaptive.planting if b['day']<=4<b['harvest_day'])
    assert source.as_dict() == original


def test_explicit_count_replacement_cancels_only_pending_relative_arrivals():
    config = habitat(initial_water_l=100, initial_energy_kwh=20)
    scenario = Scenario('future','Combined future event',event_day=8,extra_crew=2,
                        target_factors={'protein':1.4}, water_factor=.5, power_factor=.5,
                        crop_yield_factors={'leaf':.5})
    source = run_comparison(config,scenario).adaptive
    updated, first, details = continue_plan(config,scenario,source,3,
        mission_change={'crew_count':2,'replace_future_crew_changes':True})
    assert details['mission_change']['cancel_scenario_crew'] is True
    assert details['pending_scenario_crew_cancelled'] is True
    assert first.adaptive.daily[:3] == source.daily[:3]
    assert scenario.extra_crew == 2
    assert _day_conditions(updated,scenario,7) == (2,{'energy':20,'protein':2,'vitamin_c':2},5,2)
    assert _day_conditions(updated,scenario,8) == (2,{'energy':20,'protein':2.8,'vitamin_c':2},2.5,1)
    affected = [b for b in first.adaptive.planting if b['day']<8<=b['harvest_day']]
    assert affected
    assert all(b['predicted_harvest_kg']==pytest.approx(b['area_m2']*.5) for b in affected)
    # The saved cancellation persists through later continuation without a new
    # roster edit, and a subsequent explicit edit preserves elapsed conditions.
    later, second, _ = continue_plan(updated,scenario,first.adaptive,6)
    assert all(row['crew']==2 for row in second.adaptive.daily[6:])
    _, third, _ = continue_plan(later,scenario,second.adaptive,8,
        mission_change={'crew_count':1,'replace_future_crew_changes':True})
    assert third.adaptive.daily[:8] == second.adaptive.daily[:8]
    assert third.adaptive.daily[8]['crew'] == 1


def test_roster_reset_after_relative_arrival_keeps_that_completed_event():
    config = habitat(initial_water_l=100)
    scenario = Scenario('crew','Earlier arrival',event_day=3,extra_crew=1)
    source = run_comparison(config,scenario).adaptive
    updated, comparison, details = continue_plan(config,scenario,source,6,
        mission_change={'crew_count':3,'replace_future_crew_changes':True})
    assert 'cancel_scenario_crew' not in details['mission_change']
    assert _day_conditions(updated,scenario,3)[0] == 2
    assert comparison.adaptive.daily[:6] == source.daily[:6]
    assert comparison.adaptive.daily[6]['crew'] == 3


def test_count_reset_target_multiplier_does_not_inherit_superseded_roster_targets():
    pending = {'day':4,'crew':6,'crew_profiles':roster(6,3),
               'targets_per_crew':{'energy':10,'protein':3,'vitamin_c':1}}
    config = habitat(initial_water_l=100,planning_events=[pending])
    scenario = Scenario('nominal','Nominal',event_day=12)
    source = run_comparison(config,scenario).adaptive
    _, comparison, _ = continue_plan(config,scenario,source,3,{'protein':1.5},
        mission_change={'crew_count':2,'replace_future_crew_changes':True})
    assert comparison.adaptive.daily[3]['crew']==2
    assert comparison.adaptive.daily[3]['protein_target']==3


@pytest.mark.parametrize('change',[
    {'crew_count':2,'replace_future_crew_changes':1},
    {'crew_count':2,'replace_future_crew_changes':'true'},
    {'replace_future_crew_changes':True},
    {'water_budget_l_per_day':4,'replace_future_crew_changes':False},
])
def test_pending_roster_replacement_requires_boolean_and_crew(change):
    config,scenario = habitat(),Scenario('nominal','Nominal')
    source = run_comparison(config,scenario).adaptive
    with pytest.raises(ValueError):
        continue_plan(config,scenario,source,3,mission_change=change)


@pytest.mark.parametrize('invalid',[1,'true',None])
def test_scenario_crew_cancellation_marker_is_strict_boolean(invalid):
    config = habitat(planning_events=[{'day':4,'crew':2,'cancel_scenario_crew':invalid}])
    with pytest.raises(ValueError,match='cancellation'):
        config.validate()


def test_zero_remaining_water_has_visible_gap_without_refill_or_negative_stock():
    config,scenario=habitat(initial_water_l=2,initial_energy_kwh=0),Scenario('nominal','Nominal',event_day=12)
    source=run_comparison(config,scenario).adaptive
    assert source.daily and sum(r['water_l'] for r in source.daily)<=2+1e-6
    _,result,details=continue_plan(config,scenario,source,6,mission_change={'crew_count':2,'water_budget_l_per_day':100})
    remaining=details['remaining_resource_stocks']['water_l']
    assert sum(r['water_l'] for r in result.adaptive.daily[6:])<=remaining+1e-6
    assert any(r['capacity_gap'] for r in result.adaptive.daily[6:])
    assert all(r['water_remaining_l']>=0 for r in result.adaptive.daily)


def test_loss_in_a_carried_batch_is_not_applied_twice():
    config,scenario=habitat(initial_water_l=100),Scenario('loss','Crop loss',event_day=3,crop_yield_factors={'leaf':.5})
    source=run_comparison(config,scenario).adaptive
    config2, first, _=continue_plan(config,scenario,source,3)
    _,second,_=continue_plan(config2,scenario,first.adaptive,3)
    carried={(b['crop_id'],b['day']):b for b in first.adaptive.planting if b['day']<=3<b['harvest_day']}
    for batch in second.adaptive.planting:
        key=(batch['crop_id'],batch['day'])
        if key in carried:
            old=carried[key]
            assert batch['predicted_harvest_kg']/batch['area_m2']==pytest.approx(old['predicted_harvest_kg']/old['area_m2'])


@pytest.mark.parametrize('change',[
    {'crew_count':13},{'crew_count':True}, {'crew_profiles':[{**roster(1)[0],'targets_reviewed':False}]},
    {'crew_profiles':roster(2),'crew_count':2}, {'water_budget_l_per_day':-1}, {'refill_water_l':100}])
def test_invalid_or_unreviewed_mission_change_is_rejected(change):
    config,scenario=habitat(),Scenario('nominal','Nominal')
    source=run_comparison(config,scenario).adaptive
    with pytest.raises(ValueError):continue_plan(config,scenario,source,3,mission_change=change)


def test_recovery_candidates_use_boundary_water_stock_not_initial_tank():
    config,scenario=habitat(initial_water_l=12),Scenario('nominal','Nominal',event_day=12)
    source=run_comparison(config,scenario).adaptive
    updated,comparison,_=continue_plan(config,scenario,source,6,mission_change={'crew_count':2})
    report=analyze_recovery(updated,scenario,RecoveryOptions(food_limit_kg=10,water_limit_l_per_day=10,power_limit_kwh_per_day=10),comparison,start_day=7)
    remaining=comparison.adaptive.daily[5]['water_remaining_l']
    candidates={item['id']:item for item in report['candidates']}
    assert not candidates['food']['summary']['meets_targets']
    assert not candidates['power']['summary']['meets_targets']
    for candidate in report['candidates']:
        plan=candidate.get('plan') or {}
        if candidate['id']!='water' and plan.get('daily'):
            assert sum(r['water_l'] for r in plan['daily'] if r['day']>=7)<=remaining+1e-5
