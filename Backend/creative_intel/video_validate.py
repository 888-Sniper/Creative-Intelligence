"""Server-side video validation for the guided upload flow.

Frontend checks are convenience only: this module revalidates the
stored bytes (extension, size, file signature is enforced by the
media store, decoder compatibility, duration, dimensions) via
ffprobe before a video row is recorded. ffprobe is invoked with a
safe argv list (never a shell string) and a hard timeout.

Verdict shape (also persisted as videos.validation_json):
    {"status": "valid" | "invalid", "reason": <code>,
     "duration_s": float, "width": int, "height": int,
     "video_codec": str, "has_audio": bool, "rotation": int, ...}
Reason codes: empty, oversize, probe_unavailable, corrupt,
no_video_stream, unsupported_codec, too_long, bad_dimensions.
"""

import json
import os
import shutil
import subprocess

#: Accepted upload containers (extension gate; the media store's
#: magic check already rejected mismatched signatures).
CONTAINERS = (".mp4", ".mov")

#: Decoders the analysis path (ffmpeg frame/audio extraction) can
#: actually read. Anything else is an honest "unsupported", never a
#: silent transcode promise.
VIDEO_CODECS = frozenset({"h264", "hevc", "mpeg4", "vp9", "av1"})

#: Configured caps, surfaced to Stage A and enforced here.
MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION_S = 600.0
MAX_DIMENSION = 7680

PROBE_TIMEOUT_S = 30


def limits():
    """Configured limits for the Stage A UI (server is the source)."""
    return {"containers": list(CONTAINERS),
            "max_bytes": MAX_BYTES,
            "max_duration_s": MAX_DURATION_S,
            "note": "MP4/MOV only; validated server-side with ffprobe."}


def _invalid(reason, **fields):
    verdict = {"status": "invalid", "reason": reason,
               "duration_s": 0.0, "width": 0, "height": 0,
               "video_codec": "", "has_audio": False, "rotation": 0}
    verdict.update(fields)
    return verdict


def validate(path, filename="", max_bytes=MAX_BYTES,
             max_duration_s=MAX_DURATION_S):
    """Validate stored video bytes; never raises on bad input."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return _invalid("empty")
    if size <= 0:
        return _invalid("empty")
    if size > max_bytes:
        return _invalid("oversize", bytes=size)
    ext = os.path.splitext(filename or "")[1].lower()
    if ext and ext not in CONTAINERS:
        return _invalid("unsupported_container", container=ext)
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return _invalid("probe_unavailable", bytes=size)
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams",
             "-of", "json", path],
            capture_output=True, timeout=PROBE_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return _invalid("probe_unavailable", bytes=size)
    if out.returncode != 0:
        return _invalid("corrupt", bytes=size)
    try:
        probe = json.loads((out.stdout or b"").decode("utf-8", "replace"))
    except ValueError:
        return _invalid("corrupt", bytes=size)
    streams = [s for s in probe.get("streams", [])
               if isinstance(s, dict)]
    video = next((s for s in streams
                  if s.get("codec_type") == "video"), None)
    if video is None:
        return _invalid("no_video_stream", bytes=size)
    codec = str(video.get("codec_name") or "").lower()
    if codec not in VIDEO_CODECS:
        return _invalid("unsupported_codec", video_codec=codec,
                        bytes=size)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0 or max(width, height) > MAX_DIMENSION:
        return _invalid("bad_dimensions", width=width, height=height)
    duration = _duration(video, probe.get("format") or {})
    if duration is None:
        return _invalid("corrupt", width=width, height=height,
                        video_codec=codec)
    if duration > max_duration_s:
        return _invalid("too_long", duration_s=duration, width=width,
                        height=height, video_codec=codec)
    rotation = 0
    tags = video.get("tags") or {}
    try:
        rotation = int(tags.get("rotate", 0) or 0)
    except (TypeError, ValueError):
        rotation = 0
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {"status": "valid", "reason": "",
            "duration_s": duration, "width": width, "height": height,
            "video_codec": codec, "has_audio": has_audio,
            "rotation": rotation, "bytes": size}


def _duration(video, fmt):
    for raw in (video.get("duration"), fmt.get("duration")):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if 0 < value < 10 ** 9:
            return value
    return None
