from dataclasses import replace

from astra_bio.crew_response import build_response_plan
from astra_bio.crew_samples import crew_sample
from astra_bio.crop_advisor import recommend_crops
from astra_bio.model import default_config
from astra_bio.nutrition import apply_profile_targets, CrewProfile


def setup():
    state = crew_sample()
    config = apply_profile_targets(replace(default_config(), planning_events=[]),
        [CrewProfile(**p) for p in state['profiles']])
    return config, state


def test_sample_lab_review_and_complete_intake_are_not_prescriptions():
    config, state = setup()
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    assert {a['kind'] for a in response['health_alerts']} == {'low_hemoglobin','low_ferritin'}
    assert all(a['sample_only'] and a['name']=='Vamshika' for a in response['health_alerts'])
    assert len(response['crew_intake']) == 12
    assert all(r['usable_for_response'] for r in response['crew_intake'])
    assert not any(s['kind']=='approved_supplement' for s in response['immediate_support'])
    assert all(o['status']=='needs_review' and o['protein_g'] is None for o in response['production_options'])
    assert response['scope']['matched_crew_count']==4
    assert not response['scope']['unmatched_crew_names']


def test_count_only_mission_explains_why_named_health_records_cannot_be_used():
    config=replace(default_config(),planning_events=[],crew_profiles=[])
    response=build_response_plan(config,None,recommend_crops(config,automatic=True),crew_sample(),None)
    assert response['scope']['matched_crew_count']==0
    assert response['scope']['unmatched_crew_names']==['Shree Ram Vishal','Shamyuktha','Sanjay','Vamshika']
    assert not response['health_alerts']


def test_current_urgent_symptoms_immediate_not_future_microbe_treatment():
    config,state = setup()
    state = {'health_observations':[{'profile_id':'crew-1','day':1,'symptoms':['chest_pain','breathlessness']}]}
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    assert response['health_alerts'][0]['severity']=='urgent'
    assert any(s['kind']=='crew_medical' for s in response['immediate_support'])
    state['health_observations'][0]['day']=2
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    assert not response['health_alerts']


def test_draft_target_edits_and_partial_logs_do_not_rewrite_accepted_targets():
    config,state = setup()
    state['profiles'][0]['targets']['protein']=500
    state['complete_days']['crew-1:1']=False
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    row=next(r for r in response['crew_intake'] if r['profile_id']=='crew-1' and r['nutrient']=='protein')
    assert row['target']==100 and not row['usable_for_response']
    assert response['scope']['pending_target_profile_ids']==['crew-1']


def test_reviewed_microbe_projection_waits_for_startup_and_shows_real_units():
    config,state = setup()
    scenario={'reviewed_inputs':True,'start_day':1,'horizon_days':5,
        'focus_nutrient':'protein','daily_media_budget_l':100,
        'modules':[{'id':'reactor','profile_id':'limnospira_pc8005','size':1,'size_unit':'L',
            'startup_days':2,'water_l_per_unit_day':.6,'power_kwh_per_unit_day':.1,
            'commissioning_power_kwh':0}]}
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,scenario)
    option=response['production_options'][0]
    assert option['first_harvest_day']==3
    assert option['first_harvest_protein_g']==.492*.42
    assert option['food_qualified'] is False
    assert option['protein_target_share']<1


def test_supplement_requires_person_order_inventory_and_valid_date():
    config,state = setup()
    state['approved_supplements']=[{'profile_id':'crew-4','nutrient':'iron','name':'Existing order',
        'clinician_approved':True,'available':True,'quantity_remaining':2,'start_day':1}]
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    assert any(s['kind']=='approved_supplement' for s in response['immediate_support'])
    state['approved_supplements'][0]['quantity_remaining']=0
    response = build_response_plan(config,None,recommend_crops(config,automatic=True),state,None)
    assert not any(s['kind']=='approved_supplement' for s in response['immediate_support'])
