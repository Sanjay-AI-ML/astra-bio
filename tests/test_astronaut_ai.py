from io import BytesIO
import json

import pytest

from astra_bio import astronaut_ai as ai


def report():
    return {"sample_only": True, "members": [{"profile_id": "private-crew-id", "name": "Private Name",
        "targets_reviewed": True, "log_status": "complete", "focus_nutrient": "protein",
        "nutrients": [{"nutrient": "protein", "target": 80, "intake": 60, "gap": 20}],
        "health_alerts": [{"message": "private lab details", "evidence": {"hemoglobin_g_dl": 11}}],
        "food_options": [{"food_key": "lentils", "name": "untrusted display name", "reference_grams": 100,
            "nutrients": {"protein": 24.63}}]}]}


def test_no_key_has_local_numerical_explanation_without_request(monkeypatch):
    monkeypatch.setattr(ai,"gemini_config",lambda:("","unused"))
    monkeypatch.setattr(ai,"urlopen",lambda *a,**k:pytest.fail("No network expected"))
    token=ai.remember_guidance(report())
    response=ai.explain_guidance(token,"private-crew-id")
    assert response['mode']=='local_evidence' and response['submitted_to_provider'] is False
    assert any('20.00 g' in s for s in response['summary'])


def test_provider_selects_verified_anonymous_facts_and_cannot_hide_boundaries(monkeypatch):
    monkeypatch.setattr(ai,"gemini_config",lambda:("fake-key","gemini-test"))
    captured=[]
    class Reply(BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):return False
    def send(request,**kwargs):
        captured.append(json.loads(request.data))
        return Reply(json.dumps({'output_text':'{"selected_fact_ids":["nutrient.protein"]}'}).encode())
    monkeypatch.setattr(ai,"urlopen",send)
    result=ai.explain_guidance(ai.remember_guidance(report()),"private-crew-id")
    assert result['mode']=='gemini_fact_selection'
    assert {'scope','logs','targets','sample','health_review'} <= set(result['selected_fact_ids'])
    sent=json.dumps(captured)
    assert not any(private in sent for private in ['Private Name','private-crew-id','hemoglobin','private lab details','untrusted display name'])
    assert captured[0]['store'] is False


def test_interactions_model_output_steps_ignore_thought_signatures(monkeypatch):
    monkeypatch.setattr(ai,'gemini_config',lambda:('fake-key','gemini-test'))
    response={'status':'completed','steps':[{'type':'thought','signature':'private-thought'},
        {'type':'model_output','content':[{'type':'text','text':'{"selected_fact_ids":["nutrient.protein"]}'}]}]}
    monkeypatch.setattr(ai,'urlopen',lambda *a,**k:BytesIO(json.dumps(response).encode()))
    result=ai.explain_guidance(ai.remember_guidance(report()),'private-crew-id')
    assert result['mode']=='gemini_fact_selection'
    assert 'private-thought' not in json.dumps(result)


def test_provider_invented_treatment_is_discarded_and_failures_are_sanitized(monkeypatch):
    monkeypatch.setattr(ai,"gemini_config",lambda:("fake-secret","gemini-test"))
    monkeypatch.setattr(ai,"urlopen",lambda *a,**k:BytesIO(json.dumps({'output_text':'{"selected_fact_ids":["take_iron_100mg"]}'}).encode()))
    result=ai.explain_guidance(ai.remember_guidance(report()),"private-crew-id")
    assert result['mode']=='local_evidence'
    assert '100mg' not in json.dumps(result)
    def fail(*a,**k):raise RuntimeError('fake-secret provider billing response')
    monkeypatch.setattr(ai,"urlopen",fail)
    result=ai.explain_guidance(ai.remember_guidance(report()),"private-crew-id")
    assert 'fake-secret' not in json.dumps(result)


def test_profile_membership_expiry_and_server_generated_evidence(monkeypatch):
    token=ai.remember_guidance(report())
    with pytest.raises(ValueError,match='does not belong'):
        ai.explain_guidance(token,'another-profile')
    monkeypatch.setattr(ai.time,'monotonic',lambda:1e20)
    with pytest.raises(ValueError,match='expired'):
        ai.explain_guidance(token,'private-crew-id')
