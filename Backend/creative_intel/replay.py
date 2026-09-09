"""Fixture load + ordered replay log."""

import datetime
import json


def log(conn, action, payload):
    conn.execute(
        "INSERT INTO replay_log (ts, action, payload_json) VALUES (?, ?, ?)",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),
         action, json.dumps(payload)))
    conn.commit()


def history(conn):
    return [{"id": r[0], "ts": r[1], "action": r[2],
             "payload": json.loads(r[3])}
            for r in conn.execute(
                "SELECT id, ts, action, payload_json FROM replay_log ORDER BY id")]
