from fastapi.testclient import TestClient
import numpy as np

from astra_bio import api
from astra_bio.crop_trials import CSV_FIELDS, _inside_support
from astra_bio.model import HabitatConfig, FoodSpec, Scenario
from astra_bio.planner import run_comparison


def test_model_status_exposes_evidence_without_training_or_actuation(monkeypatch):
    monkeypatch.setattr(api,'registry_status',lambda:{'active_id':'base','candidates':[]})
    monkeypatch.setattr(api,'current_measured_growth_status',lambda:{'status':'experimental_fitted','independent_cycle_count':1})
    monkeypatch.setattr(api,'current_crop_response_status',lambda:{'status':'awaiting_measurements'})
    client=TestClient(api.app,base_url='http://127.0.0.1')
    data=client.get('/api/models').json()
    assert data['automatic_action'] is False
    assert data['growth']['independent_cycle_count']==1
    assert data['crop_response']['status']=='awaiting_measurements'
    template=client.get('/api/models/crop-trial-template')
    assert template.status_code==200
    assert template.text.splitlines()==[','.join(CSV_FIELDS)]


def test_model_selection_is_explicit_and_passes_the_recorded_id(monkeypatch):
    calls=[]
    monkeypatch.setattr(api,'select_model',lambda identifier:calls.append(identifier))
    monkeypatch.setattr(api,'model_status',lambda:{'ready':True,'kind':'pretrained'})
    monkeypatch.setattr(api,'registry_status',lambda:{'active_id':'base'})
    client=TestClient(api.app,base_url='http://127.0.0.1')
    assert calls==[]
    response=client.post('/api/models/plant/select',json={'candidate_id':'base'})
    assert response.status_code==200 and calls==['base']
    assert response.json()['plant_model']['kind']=='pretrained'


def test_support_checks_do_not_poison_the_existing_planner_scheduler():
    assert _inside_support(np.asarray([[0.],[1.]]),np.asarray([.5]))
    config=HabitatConfig(days=3,crew=1,area_m2=0,water_budget_l_per_day=10,
        power_budget_kwh_per_day=1,crew_water_l_per_day=1,targets_per_crew={'n':1},
        nutrient_units={'n':'unit'},foods=[FoodSpec('ration','Ration',10,{'n':1})],crops=[],reserve_days=0)
    result=run_comparison(config,Scenario('none','No event',event_day=99))
    assert result.adaptive.status not in {'solver_error','solver_unavailable'}
