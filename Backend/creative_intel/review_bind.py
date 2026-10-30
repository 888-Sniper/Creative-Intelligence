"""Pure comparison for a stored analysis snapshot.

The review route asks this module which mode to rebind and which
fields must still match. It does not open a route, a provider, or
a draft row.
"""

SNAPSHOT_KEYS = (
    "video_id",
    "media_id",
    "video_sha256",
    "dataset_version",
    "match_confirmed_at",
    "client",
    "campaign",
    "video_only",
)


def stored_video_only(snapshot):
    """True only when the saved snapshot says the analysis was video-only."""
    return bool((snapshot or {}).get("video_only"))


def _same(left, right):
    return (left or "") == (right or "")


def inputs_unchanged(live, stored):
    """False when the live rebind differs from the stored snapshot.

    A missing video_only flag compares equal to an explicit False, so
    an older combined snapshot is not treated as a mode change. An
    explicit True does not compare equal to False.
    """
    live = live or {}
    stored = stored or {}
    return all(_same(live.get(key), stored.get(key)) for key in SNAPSHOT_KEYS)
