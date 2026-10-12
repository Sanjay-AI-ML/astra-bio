import json
from dataclasses import replace

import pytest

from astra_bio.model import default_config, Scenario
from astra_bio.planner import run_comparison
from astra_bio.workspace import configuration_json, import_configuration, list_snapshots, load_snapshot, restore_run, save_configuration, save_run


def test_versioned_config_roundtrip_and_local_history(tmp_path):
    config = replace(default_config(), planting_increment_m2=.25, nutrient_upper_per_crew={"vitamin_c": 2000})
    assert import_configuration(configuration_json(config)) == config
    database = tmp_path / "workspace.sqlite"
    identifier = save_configuration("Crew A", config, database)
    assert list_snapshots("config", database)[0]["id"] == identifier
    assert import_configuration(load_snapshot(identifier, "config", database)) == config
    with pytest.raises(ValueError, match="not found"):
        load_snapshot(identifier, "run", database)


@pytest.mark.parametrize("text", ['{"schema_version":2}', '{"schema_version":1,"config":{"injected_field":true}}', '{"schema_version":1,"config":{"area_m2":NaN}}'])
def test_untrusted_import_rejected(text):
    with pytest.raises(ValueError):
        import_configuration(text)


def test_completed_run_roundtrip_preserves_event_state(tmp_path):
    config = replace(default_config(), days=8)
    scenario = Scenario("crew", "Crew change", event_day=4, extra_crew=1)
    comparison = run_comparison(config, scenario)
    payload = json.loads(configuration_json(config))
    from dataclasses import asdict
    payload.update(scenario=asdict(scenario), baseline=comparison.baseline.as_dict(), adaptive=comparison.adaptive.as_dict())
    identifier = save_run("Crew event", payload, tmp_path / "workspace.sqlite")
    restored_config, restored_scenario, restored = restore_run(load_snapshot(identifier, "run", tmp_path / "workspace.sqlite"))
    assert restored_config == config
    assert restored_scenario == scenario
    assert restored == comparison
    payload["adaptive"]["daily"][1]["day"] = 99
    with pytest.raises(ValueError, match="horizon"):
        restore_run(payload)
