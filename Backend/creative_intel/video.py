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
MAX_FRAMES = 16
MAX_DURATION_S = 600.0
RUN_TIMEOUT_S = 120
# First seconds sampled densely: hooks land here and cheap frames
# buy hook-modality evidence.
DENSE_S = 3.0
DENSE_STEP_S = 1.0


def sample_times(duration_s, every_s=EVERY_S, dense_s=DENSE_S,
                 max_frames=MAX_FRAMES):
    """Full-video sample plan: dense first seconds, even coverage of
    the middle, and a guaranteed end-frame sample.

    A fixed every-N-seconds grid from zero concentrates analysis on
    the opening and can miss a CTA/logo/end-frame at 20-30s
    entirely; this plan always reaches (duration - 0.5s). When the
    plan exceeds max_frames the dense head and the end sample are
    kept and the middle is thinned evenly. Returns sorted unique
    seconds, capped at max_frames (at least the 0s and end frames).
    """
    try:
        duration = float(duration_s)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        duration = 30.0
    duration = min(duration, MAX_DURATION_S)
    times = [round(t, 2) for t in _frange(0.0, min(dense_s, duration),
                                          DENSE_STEP_S)]
    t = dense_s + every_s
    while t < duration - 0.5:
        times.append(round(t, 2))
        t += every_s
    end = round(max(0.0, duration - 0.5), 2)
    if end not in times:
        times.append(end)
    times = sorted(set(times))
    if len(times) > max_frames:
        head = [x for x in times if x <= dense_s]
        tail = [times[-1]]
        middle = [x for x in times if x > dense_s and x != times[-1]]
        keep = max(0, max_frames - len(head) - len(tail))
        if keep and middle:
            step = len(middle) / keep
            middle = [middle[min(len(middle) - 1, int(i * step))]
                      for i in range(keep)]
        else:
            middle = []
        times = sorted(set(head + middle + tail))
    return times


def _frange(start, stop, step):
    out = []
    t = start
    while t <= stop + 1e-9:
        out.append(round(t, 2))
        t += step
    return out


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
    # format=yuvj420p: phone/desktop clips are usually limited-range
    # yuv420p, which recent ffmpeg mjpeg encoders reject ("Non
    # full-range YUV is non-standard"). Full-range 420 keeps the
    # encoder happy on old and new builds alike. The fps value is an
    # integer fraction or a plain float rate: "fps=1/3.0" carries a
    # non-integer denominator, which ffmpeg reads as 0 fps and
    # silently writes nothing.
    if float(every_s).is_integer():
        fps = "fps=1/%d" % int(every_s)
    else:
        fps = "fps=%.6f" % (1.0 / float(every_s))
    _run(["ffmpeg", "-y", "-v", "error", "-i", src_path,
          "-vf", "%s,format=yuvj420p" % fps, out_pattern])
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


def extract_frame_at(src_path, t_sec, dst_path):
    """One JPEG still at exactly t_sec. Per-timestamp grabs keep a
    1:1 frame<->time mapping (fps grids silently drop frames on
    short clips and blur exact coverage), so the vision model can
    be told precisely which second each image shows."""
    _run(["ffmpeg", "-y", "-v", "error", "-ss", str(max(0.0, t_sec)),
          "-i", src_path, "-frames:v", "1",
          "-vf", "format=yuvj420p", dst_path])
    with open(dst_path, "rb") as fh:
        blob = fh.read()
    if not blob.startswith(b"\xff\xd8\xff"):
        raise _unavailable("ffmpeg produced no JPEG at %ss" % t_sec)
    return blob


def prepare(src_path, cache_dir, every_s=EVERY_S, duration_s=None):
    """Decompose one video file -> {"audio": (bytes, mime)|None,
    "images": [jpeg], "image_times": [seconds], "duration_s": float}.

    Frames follow sample_times(): dense first seconds, even middle
    coverage, guaranteed end-frame sample — the whole video, never
    just the opening. Frame cache files embed the timestamp, so a
    plan change cannot silently reuse a differently-timed still.
    """
    if not have_ffmpeg():
        raise _unavailable(
            "ffmpeg not found: install ffmpeg for automatic video "
            "decomposition, or upload audio (.wav/.mp3) and frame "
            "images (.jpg/.png) separately")
    with open(src_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    os.makedirs(cache_dir, exist_ok=True)
    wav_path = os.path.join(cache_dir, "%s_audio.wav" % digest[:16])
    if os.path.isfile(wav_path):
        with open(wav_path, "rb") as fh:
            audio = fh.read()
    else:
        try:
            audio = extract_audio(src_path, wav_path)
        except Exception:
            audio = None  # stills-only clip: vision can proceed
    probed = None
    if duration_s is None:
        probed = probe_duration_s(src_path)
    duration = duration_s if duration_s else (probed or 30.0)
    images, image_times = [], []
    for t in sample_times(duration, every_s):
        path = os.path.join(
            cache_dir, "%s_t%07d.jpg" % (digest[:16], int(round(t * 1000))))
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                blob = fh.read()
            if blob.startswith(b"\xff\xd8\xff"):
                images.append(blob)
                image_times.append(t)
            continue
        try:
            images.append(extract_frame_at(src_path, t, path))
            image_times.append(t)
        except Exception:
            continue
    if audio is None and not images:
        raise _unavailable("could not decompose %s" %
                           os.path.basename(src_path))
    return {"images": images, "image_times": image_times,
            "duration_s": duration, "has_video": True,
            "audio": (audio, "audio/wav") if audio else None}
