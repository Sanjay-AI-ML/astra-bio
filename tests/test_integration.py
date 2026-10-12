"""Behavioral checks for Node-RED validation and the shared SQLite boundary.

These execute the actual flow's JavaScript functions with Node, then use its
prepared INSERT against a database initialized by the application's storage API.
They do not start MQTT, install Node-RED, flash firmware or exercise actuators.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

from astra_bio.storage import init_db, latest_observation


ROOT = Path(__file__).resolve().parents[1]
FLOW = json.loads((ROOT / "integration" / "node-red-flow.json").read_text(encoding="utf-8"))
NODES = {node["id"]: node for node in FLOW}
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is needed to execute the actual Node-RED validator")
class TelemetryIntegrationTests(unittest.TestCase):
    def run_flow(self, payload: dict, *, collector: bool = False, topic: str | None = None,
                 retain: bool = False) -> dict:
        harness = """
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const errors = [];
const node = {error: (text) => errors.push(text)};
let msg = {payload: input.payload, topic:input.topic, retain:input.retain};
if (input.collector) {
    msg = new Function('msg', 'node', input.stamper)(msg, node);
}
const result = msg ? new Function('msg', 'node', input.validator)(msg, node) : null;
process.stdout.write(JSON.stringify({result, errors}));
"""
        completed = subprocess.run(
            [NODE, "-e", harness],
            input=json.dumps(
                {
                    "payload": payload,
                    "collector": collector,
                    "topic": topic or f"astra-bio/devices/{payload.get('device_id')}/telemetry",
                    "retain": retain,
                    "stamper": NODES["astra-stamp-hardware"]["func"],
                    "validator": NODES["astra-normalize"]["func"],
                },
                allow_nan=False,
            ),
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        return json.loads(completed.stdout)

    @staticmethod
    def sample(**changes: object) -> dict:
        row = json.loads(
            (ROOT / "integration" / "telemetry.example.json").read_text(encoding="utf-8")
        )
        row.update(changes)
        return row

    def test_prepared_insert_is_readable_by_product_storage(self) -> None:
        payload = self.sample(note="'; DROP TABLE observations; --")
        response = self.run_flow(payload)
        self.assertEqual(response["errors"], [])
        prepared = response["result"]["params"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite"
            init_db(path)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute(
                    NODES["astra-insert"]["sql"],
                    {key.lstrip("$"): value for key, value in prepared.items()},
                )
            row = latest_observation(path)
            self.assertIsNotNone(row)
            self.assertEqual(row["source"], "synthetic")
            self.assertEqual(row["air_temp_c"], 23.4)
            self.assertEqual(row["low_water"], 0)
            self.assertEqual(json.loads(row["raw_json"])["note"], payload["note"])

    def test_missing_sensor_is_unknown_not_zero(self) -> None:
        payload = self.sample()
        del payload["solution_temp_c"]
        payload["low_water"] = None
        result = self.run_flow(payload)["result"]["payload"]
        self.assertIsNone(result["solution_temp_c"])
        self.assertIsNone(result["low_water"])

    def test_bad_messages_never_reach_sqlite(self) -> None:
        invalid = [
            self.sample(source="replay"),
            self.sample(source=None),
            self.sample(device_id="../tray"),
            self.sample(ts_utc="2026-02-31T10:00:00Z"),
            self.sample(ts_utc="2026-10-10T10:00:00"),
            self.sample(air_temp_c="23.4"),
            self.sample(relative_humidity_pct=101),
            self.sample(low_water="false"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.run_flow(payload)
                self.assertIsNone(response["result"])
                self.assertTrue(response["errors"])

    def test_hardware_receipt_preserves_device_clock(self) -> None:
        hardware = self.sample(source="hardware", ts_utc=None, clock_synced=False)
        response = self.run_flow(hardware, collector=True)
        raw = json.loads(response["result"]["payload"]["raw_json"])
        self.assertEqual(raw["timestamp_origin"], "collector")
        self.assertFalse(raw["clock_synced"])
        instant = datetime.fromisoformat(raw["ts_utc"].replace("Z", "+00:00"))
        self.assertLess(abs((datetime.now(timezone.utc) - instant).total_seconds()), 10)
        future = self.sample(source="hardware", ts_utc="2099-01-01T00:00:00Z")
        result = self.run_flow(future, collector=True)["result"]["payload"]
        raw = json.loads(result["raw_json"])
        self.assertEqual(raw["device_ts_utc"], "2099-01-01T00:00:00Z")
        self.assertNotEqual(result["ts_utc"], raw["device_ts_utc"])
        self.assertEqual(raw["transport"], "mqtt")
        synthetic = self.sample(device_id="demo-tray-01", ts_utc=None)
        self.assertIsNone(self.run_flow(synthetic, collector=True)["result"])

    def test_old_replay_timestamp_is_preserved(self) -> None:
        payload = self.sample(device_id="demo-tray-01", ts_utc="2025-01-01T00:00:00Z")
        result = self.run_flow(payload, collector=True)["result"]["payload"]
        self.assertEqual(result["source"], "synthetic")
        self.assertEqual(result["ts_utc"], "2025-01-01T00:00:00.000Z")

    def test_topic_identity_source_and_retained_packets_are_enforced(self) -> None:
        packets = [
            (self.sample(device_id="demo-tray-01"), "astra-bio/devices/other/telemetry", False),
            (self.sample(device_id="demo-tray-01", source="hardware"), None, False),
            (self.sample(device_id="tray-01", source="synthetic"), None, False),
            (self.sample(device_id="tray-01", source="hardware"), None, True),
            (self.sample(device_id="demo-tray-01"), None, True),
        ]
        for payload, topic, retain in packets:
            with self.subTest(device=payload["device_id"], topic=topic, retained=retain):
                result = self.run_flow(payload, collector=True, topic=topic, retain=retain)
                self.assertIsNone(result["result"])
                self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
