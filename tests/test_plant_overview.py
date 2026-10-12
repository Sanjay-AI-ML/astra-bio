from io import BytesIO
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from astra_bio import plant_overview as overview, plant_overview_routes as routes


@pytest.fixture
def client(monkeypatch):
    app=FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(overview, "gemini_config", lambda:("", "gemini-3.5-flash-lite"))
    return TestClient(app)


def leaf(condition="early blight", healthy=False):
    return {"status":"tentative","reason":"Tentative match", "predictions":[{"condition":condition,"score":.8,"healthy_label":healthy}]}


def fruit():
    return {"status":"observed","visible_count":3,"counts_by_stage":{"unripe":2,"fully ripe":1},"reason":"Visible produce only"}


def test_overview_keeps_healthy_leaf_distinct_from_whole_plant_and_food_safety():
    result=overview.build_overview("tomato",leaf("healthy",True),fruit())
    assert "does not establish whole-plant health" in result["brief_overview"]
    assert "3 visible" in result["brief_overview"]
    assert "do not certify food safety" in result["possible_use"][0]
    assert result["automatic_action"] is False
    assert result["inventory_updated"] is False


def test_unconfirmed_disease_keeps_review_and_does_not_prescribe_a_cure():
    result=overview.build_overview("tomato",leaf(),fruit())
    assert "resembles early blight" in result["brief_overview"]
    assert "cause has not been confirmed" in result["brief_overview"]
    assert any("specialist" in note for note in result["next_steps"])
    assert not any("apply" in note.lower() for note in result["next_steps"])


@pytest.mark.parametrize("status",["uncertain","rejected","unavailable"])
def test_rejected_leaf_predictions_do_not_become_findings(status):
    result=overview.build_overview("potato",{**leaf("late blight"),"status":status},None)
    assert "late blight" not in result["brief_overview"]
    assert "unresolved" in result["brief_overview"]
    assert any("does not mean there is no fruit" in text for text in result["possible_use"])


@pytest.mark.parametrize("extra_field",["file", "fruit_file", "unknown_image"])
def test_unexpected_or_duplicate_plant_photos_are_rejected_before_inference(client,monkeypatch,extra_field):
    called=[]
    monkeypatch.setattr(routes,"assess_image",lambda *args:called.append("leaf"))
    result=client.post('/api/plant-overview',data={"crop_species":"tomato"},files=[("file",('plant.jpg',b'plant','image/jpeg')),(extra_field,('another.jpg',b'another','image/jpeg'))])
    assert result.status_code==422
    assert "exactly one" in result.json()["detail"]
    assert not called


def test_routes_join_real_inference_contracts_without_external_images(client,monkeypatch):
    seen=[]
    monkeypatch.setattr(routes,"assess_image",lambda data,species:(seen.append((data,species)),leaf())[1])
    monkeypatch.setattr(routes,"assess_fruit_image",lambda data,species,model:(seen.append((data,species,model)),fruit())[1])
    response=client.post('/api/plant-overview',data={"crop_species":"tomato","plant_id":"Tray1plant2"},files={"file":('plant.jpg',b'plant','image/jpeg')})
    assert response.status_code==200,response.text
    data=response.json()
    assert seen==[(b'plant','tomato'),(b'plant','tomato','tomato-ripeness-3')]
    assert data["plant_id"]=="Tray1plant2"
    assert data["schema_version"]==3
    assert data["input_mode"]=="single_photo"
    assert data["image_sha256"]==hashlib.sha256(b'plant').hexdigest()
    assert data["leaf_image_sha256"]==data["image_sha256"]
    assert data["leaf_input_source"]==data["leaf"]["input_source"]=="plant_photo"
    assert any("does not locate individual leaves" in text for text in data["overview"]["limitations"])
    assert data["images_uploaded_to_provider"] is False
    ai=client.post('/api/plant-overview/ai',json={"evidence_id":data["evidence_id"]}).json()
    assert ai["mode"]=="local_evidence"
    assert "No Gemini API key" in ai["fallback_reason"]
    assert client.post('/api/plant-overview/ai',json={"evidence_id":"forged"}).status_code==422


@pytest.mark.parametrize(("mode", "expected"), [("leaf", "leaf"), ("fruit", "fruit")])
def test_single_purpose_modes_only_run_the_requested_analysis(client,monkeypatch,mode,expected):
    called=[]
    monkeypatch.setattr(routes,"assess_image",lambda data,species:(called.append("leaf"),leaf())[1])
    monkeypatch.setattr(routes,"assess_fruit_image",lambda data,species,model:(called.append("fruit"),fruit())[1])
    response=client.post('/api/plant-overview',data={"crop_species":"tomato","screening_mode":mode},files={
        "file":('plant.jpg',b'plant photograph','image/jpeg')})
    assert response.status_code==200,response.text
    result=response.json()
    assert called==[expected]
    assert result["screening_mode"]==mode
    assert result["overview"] is None
    assert result["leaf"]["status"]=="not_requested" if mode=="fruit" else result["leaf"]["status"]=="tentative"
    assert result["fruit"]["status"]=="not_requested" if mode=="leaf" else result["fruit"]["status"]=="observed"


def test_optional_leaf_closeup_uses_separate_model_inputs_and_evidence_hashes(client,monkeypatch):
    seen=[]
    monkeypatch.setattr(routes,"assess_image",lambda data,species:(seen.append(('leaf',data,species)),leaf())[1])
    monkeypatch.setattr(routes,"assess_fruit_image",lambda data,species,model:(seen.append(('fruit',data,species,model)),fruit())[1])
    response=client.post('/api/plant-overview',data={"crop_species":"tomato"},files={
        "file":('plant.jpg',b'wide plant image','image/jpeg'),
        "leaf_file":('closeup.jpg',b'leaf detail','image/jpeg')})
    assert response.status_code==200,response.text
    result=response.json()
    assert seen==[('leaf',b'leaf detail','tomato'),('fruit',b'wide plant image','tomato','tomato-ripeness-3')]
    assert result["schema_version"]==3
    assert result["input_mode"]=="plant_photo_with_leaf_closeup"
    assert result["leaf_input_source"]==result["leaf"]["input_source"]=="leaf_closeup"
    assert result["image_sha256"]==hashlib.sha256(b'wide plant image').hexdigest()
    assert result["leaf_image_sha256"]==hashlib.sha256(b'leaf detail').hexdigest()
    assert "resembles early blight" in result["overview"]["brief_overview"]
    assert any("Neither model verifies" in text for text in result["overview"]["limitations"])
    assert result["images_uploaded_to_provider"] is False
    assert result["automatic_action"] is False


def test_duplicate_leaf_closeups_are_rejected_before_inference(client,monkeypatch):
    called=[]
    monkeypatch.setattr(routes,"assess_image",lambda *args:called.append('leaf'))
    monkeypatch.setattr(routes,"assess_fruit_image",lambda *args:called.append('fruit'))
    response=client.post('/api/plant-overview',files=[
        ('file',('plant.jpg',b'plant','image/jpeg')),
        ('leaf_file',('leaf.jpg',b'leaf','image/jpeg')),
        ('leaf_file',('other.jpg',b'other','image/jpeg'))])
    assert response.status_code==422
    assert "at most one optional leaf" in response.json()["detail"]
    assert not called


@pytest.mark.parametrize("payload,status",[(b'',422),(b'123456789',413)])
def test_empty_or_oversized_leaf_closeup_stops_both_models(client,monkeypatch,payload,status):
    called=[]
    monkeypatch.setattr(routes,"MAX_IMAGE_BYTES",8)
    monkeypatch.setattr(routes,"assess_image",lambda *args:called.append('leaf'))
    monkeypatch.setattr(routes,"assess_fruit_image",lambda *args:called.append('fruit'))
    response=client.post('/api/plant-overview',files={
        "file":('plant.jpg',b'plant','image/jpeg'),
        "leaf_file":('leaf.jpg',payload,'image/jpeg')})
    assert response.status_code==status
    assert "leaf close-up" in response.json()["detail"]
    assert not called


@pytest.mark.parametrize("leaf_status",["uncertain","rejected","unavailable"])
def test_unresolved_leaf_closeup_never_claims_condition_or_discards_fruit(client,monkeypatch,leaf_status):
    monkeypatch.setattr(routes,"assess_image",lambda *args:{**leaf('late blight'),"status":leaf_status})
    monkeypatch.setattr(routes,"assess_fruit_image",lambda *args:fruit())
    response=client.post('/api/plant-overview',files={
        "file":('plant.jpg',b'plant','image/jpeg'),"leaf_file":('leaf.jpg',b'leaf','image/jpeg')})
    assert response.status_code==200
    result=response.json()
    assert result["leaf"]["status"]==leaf_status
    assert "unresolved in the supplied close-up" in result["overview"]["brief_overview"]
    assert "late blight" not in result["overview"]["brief_overview"]
    assert result["fruit"]["visible_count"]==3


def test_status_exposes_leaf_installation_state_without_loading_photos(client,monkeypatch):
    monkeypatch.setattr(routes,"model_status",lambda:{"ready":False,"reason":"Model file missing"})
    result=client.get('/api/plant-overview/status')
    assert result.status_code==200
    assert result.json()["leaf_model"]=={"ready":False,"reason":"Model file missing"}
    assert result.json()["local_summary_available"] is True


def test_unresolved_leaves_do_not_discard_fruit_observations(client,monkeypatch):
    monkeypatch.setattr(routes,"assess_image",lambda data,species:{"status":"uncertain","reason":"Leaf detail insufficient","predictions":[]})
    monkeypatch.setattr(routes,"assess_fruit_image",lambda *args:fruit())
    response=client.post('/api/plant-overview',files={"file":('plant.jpg',b'plant','image/jpeg')})
    assert response.status_code==200
    assert response.json()["fruit"]["visible_count"]==3
    assert "Leaf condition could not be resolved from this photograph" in response.json()["overview"]["brief_overview"]
    assert "image is missing" not in response.json()["overview"]["brief_overview"]
    assert client.post('/api/plant-overview').status_code==422


@pytest.mark.parametrize("species",["potato", "bell pepper"])
def test_non_tomato_photo_defaults_to_compatible_produce_model(client,monkeypatch,species):
    seen=[]
    monkeypatch.setattr(routes,"assess_image",lambda *args:leaf())
    monkeypatch.setattr(routes,"assess_fruit_image",lambda data,crop,model:(seen.append((data,crop,model)),fruit())[1])
    response=client.post('/api/plant-overview',data={"crop_species":species},files={"file":('plant.jpg',b'plant','image/jpeg')})
    assert response.status_code==200
    assert seen==[(b'plant',species,'produce-detection')]


@pytest.mark.parametrize("payload,status",[(b'',422),(b'123456789',413)])
def test_empty_or_oversized_photo_does_not_run_models(client,monkeypatch,payload,status):
    called=[]
    monkeypatch.setattr(routes,"MAX_IMAGE_BYTES",8)
    monkeypatch.setattr(routes,"assess_image",lambda *args:called.append('leaf'))
    monkeypatch.setattr(routes,"assess_fruit_image",lambda *args:called.append('fruit'))
    response=client.post('/api/plant-overview',files={"file":('plant.jpg',payload,'image/jpeg')})
    assert response.status_code==status
    assert not called


def test_expired_evidence_cannot_be_sent_to_provider(monkeypatch):
    token=overview.remember(overview.build_overview("tomato",leaf(),fruit()))
    monkeypatch.setattr(overview.time,"monotonic",lambda:1e20)
    with pytest.raises(ValueError,match="expired"):
        overview.recalled(token)


def test_provider_uses_schema_bound_facts_not_images_and_rejects_invented_advice(monkeypatch):
    monkeypatch.setattr(overview,"gemini_config",lambda:("fake-test-key", "gemini-3.5-flash-lite"))
    captured=[]
    class Reply(BytesIO):
        pass
    def send(request,timeout):
        payload=json.loads(request.data)
        captured.append(payload)
        assert timeout==20
        assert request.full_url.endswith('gemini-3.5-flash-lite:generateContent')
        assert 'fake-test-key' not in request.full_url
        assert payload["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
        assert payload["generationConfig"]["responseFormat"]["text"]["schema"]["additionalProperties"] is False
        return Reply(json.dumps({"candidates":[{"content":{"parts":[{"text":json.dumps({"selected_fact_ids":["care.monitor","fruit.stages"]})}]}}]}).encode())
    monkeypatch.setattr(overview,"urlopen",send)
    result=overview.curate_with_gemini(overview.build_overview("tomato",leaf(),fruit()))
    assert result["mode"]=="gemini_fact_selection"
    assert "leaf.match" in result["selected_fact_ids"]
    assert "fruit.count" in result["selected_fact_ids"]
    assert "image" not in captured[0]["contents"][0]["parts"][0]["text"]
    monkeypatch.setattr(overview,"urlopen",lambda *args,**kwargs:Reply(json.dumps({"candidates":[{"content":{"parts":[{"text":'{"selected_fact_ids":["confirmed_safe_to_eat"]}'}]}}]}).encode()))
    invalid=overview.curate_with_gemini(overview.build_overview("tomato",leaf(),fruit()))
    assert invalid["mode"]=="local_evidence"
    assert "failed evidence validation" in invalid["fallback_reason"]


def test_provider_errors_never_reveal_key_or_upstream_messages(monkeypatch):
    monkeypatch.setattr(overview,"gemini_config",lambda:("FAKE-SECRET", "gemini-3.5-flash-lite"))
    def fail(*args,**kwargs):
        raise RuntimeError("FAKE-SECRET billing error")
    monkeypatch.setattr(overview,"urlopen",fail)
    result=overview.curate_with_gemini(overview.build_overview("tomato",leaf(),fruit()))
    assert "FAKE-SECRET" not in json.dumps(result)
    assert result["mode"]=="local_evidence"
