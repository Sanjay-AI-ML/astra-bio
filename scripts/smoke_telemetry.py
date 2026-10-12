"""Exercise the running local Node-RED inject -> SQLite -> Python read path."""

from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import time
from urllib.request import Request, urlopen

from astra_bio.storage import DEFAULT_DB, init_db, latest_observation


def main():
    init_db()
    with closing(sqlite3.connect(DEFAULT_DB)) as db:
        before_id = db.execute("SELECT COALESCE(MAX(id),0) FROM observations").fetchone()[0]
    # This official core route triggers the named manual synthetic Inject node.
    request = Request("http://127.0.0.1:1880/inject/astra-inject", data=b"", method="POST")
    with urlopen(request, timeout=10) as response:
        assert response.status == 200
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = latest_observation()
        if row and row["id"] > before_id:
            assert row["source"] == "synthetic", row
            assert row["device_id"] == "tray-replay", row
            assert row["air_temp_c"] == 23.4, row
            instant = datetime.fromisoformat(row["ts_utc"].replace("Z", "+00:00"))
            assert abs((datetime.now(timezone.utc) - instant).total_seconds()) < 15
            print(f"PASS: Node-RED synthetic inject -> shared SQLite -> product read; row {row['id']}.")
            return
        time.sleep(0.1)
    raise RuntimeError("Node-RED acknowledged the inject but no current observation was saved.")


if __name__ == "__main__":
    main()
