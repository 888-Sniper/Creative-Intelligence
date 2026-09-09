"""Video preprocessing: ffmpeg-backed audio + frame extraction.

Upload MP4 -> Run Pipeline becomes end-to-end: the audio track feeds
live STT and sampled JPEG frames feed live vision. ffmpeg is an
optional system dependency (not a repo dependency): when present,
extraction runs and results are cached next to the upload by content
hash; when absent, callers get a clear ProviderUnavailable telling
the operator to install ffmpeg or upload audio/frames separately.
Nothing is invented either way. All subprocess calls use argument
lists (never a shell) with timeouts.
"""

import hashlib
import os
import shutil
import subprocess

SAMPLE_RATE = 16000
EVERY_S = 3.0
MAX_FRAMES = 12
MAX_DURATION_S = 600.0
RUN_TIMEOUT_S = 120


def have_ffmpeg():
    return bool(shutil.which("ffmpeg"))


def _run(argv):
    try:
        out = subprocess.run(argv, capture_output=True, timeout=RUN_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        raise _unavailable("ffmpeg failed to start: %s" % e)
    if out.returncode != 0:
        detail = (out.stderr or b"").decode("utf-8", "replace")[-300:]
        raise _unavailable("ffmpeg exited %d: %s" % (out.returncode, detail))
    return out


def _unavailable(reason):
    from .providers import ProviderUnavailable
    return ProviderUnavailable(reason)


def probe_duration_s(path):
    """Media duration via ffprobe; None when unknown (caller falls back)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        value = float((out.stdout or b"").decode().strip())
    except ValueError:
        return None
    if value <= 0 or value > MAX_DURATION_S:
        return None
    return value


def extract_audio(src_path, dst_wav):
    _run(["ffmpeg", "-y", "-v", "error", "-i", src_path,
          "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
          dst_wav])
    with open(dst_wav, "rb") as fh:
        blob = fh.read()
    if not blob.startswith(b"RIFF"):
        raise _unavailable("ffmpeg produced no audio track for %s" %
                           os.path.basename(src_path))
    return blob


def extract_frames(src_path, out_pattern, every_s=EVERY_S, max_frames=MAX_FRAMES):
    if every_s <= 0:
        raise _unavailable("bad frame interval")
    _run(["ffmpeg", "-y", "-v", "error", "-i", src_path,
          "-vf", "fps=1/%s" % (every_s,), out_pattern])
    frames = []
    for i in range(1, max_frames + 1):
        path = out_pattern % i
        if not os.path.isfile(path):
            break
        with open(path, "rb") as fh:
            blob = fh.read()
        if blob.startswith(b"\xff\xd8\xff"):
            frames.append(blob)
    if not frames:
        raise _unavailable("ffmpeg extracted no frames from %s" %
                           os.path.basename(src_path))
    return frames


def prepare(src_path, cache_dir, every_s=EVERY_S, duration_s=None):
    """Decompose one video file -> {"audio": (bytes, mime)|None,
    "images": [jpeg]}. Results cached by content hash."""
    if not have_ffmpeg():
        raise _unavailable(
            "ffmpeg not found: install ffmpeg for automatic video "
            "decomposition, or upload audio (.wav/.mp3) and frame "
            "images (.jpg/.png) separately")
    with open(src_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    os.makedirs(cache_dir, exist_ok=True)
    wav_path = os.path.join(cache_dir, "%s_audio.wav" % digest[:16])
    images = []
    if os.path.isfile(wav_path):
        with open(wav_path, "rb") as fh:
            audio = fh.read()
    else:
        try:
            audio = extract_audio(src_path, wav_path)
        except Exception:
            audio = None  # stills-only clip: vision can proceed
    for i in range(1, MAX_FRAMES + 1):
        path = os.path.join(cache_dir, "%s_frame_%03d.jpg" % (digest[:16], i))
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                images.append(fh.read())
    if not images:
        pattern = os.path.join(cache_dir, "%s_frame_%%03d.jpg" % digest[:16])
        try:
            images = extract_frames(src_path, pattern, every_s)
        except Exception:
            images = []
    if audio is None and not images:
        raise _unavailable("could not decompose %s" %
                           os.path.basename(src_path))
    out = {"images": images, "has_video": True}
    out["audio"] = (audio, "audio/wav") if audio else None
    _ = duration_s  # reserved: per-clip intervals when annotations set duration
    return out
