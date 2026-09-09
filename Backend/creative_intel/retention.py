"""Retention drop-off joined to annotation timestamps."""


def join_segments(conn, creative_key):
    """Per-structure-segment retention drop: first vs last curve point inside."""
    import json
    row = conn.execute("SELECT annotation_json FROM annotations WHERE creative_key=?",
                       (creative_key,)).fetchone()
    if not row:
        raise ValueError("no annotation for %r" % creative_key)
    structure = json.loads(row[0]).get("structure", {})
    curve = conn.execute(
        "SELECT t_sec, retention_pct FROM retention WHERE creative_key=?"
        " ORDER BY t_sec", (creative_key,)).fetchall()
    if not curve:
        raise ValueError("no retention curve for %r" % creative_key)
    out = []
    for slot, seg in structure.items():
        pts = [(t, p) for t, p in curve if seg["start_s"] <= t <= seg["end_s"]]
        if not pts:
            out.append({"segment": slot, "drop_pts": 0.0, "n_points": 0})
        else:
            out.append({"segment": slot,
                        "drop_pts": round(pts[0][1] - pts[-1][1], 2),
                        "n_points": len(pts)})
    return out
